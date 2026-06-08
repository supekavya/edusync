from flask import Blueprint, render_template, request, session, redirect, url_for, flash
from functools import wraps
from datetime import datetime, date

teacher_bp = Blueprint("teacher", __name__)

def teacher_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session or session.get("role") != "teacher":
            return redirect(url_for("auth.login"))
        # Guard: if teacher record missing (e.g. stale session), force re-login
        from services.teacher_service import get_teacher_by_id
        if get_teacher_by_id(session["user_id"]) is None:
            session.clear()
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated

def get_teacher():
    from services.teacher_service import get_teacher_by_id
    teacher = get_teacher_by_id(session["user_id"])
    if teacher is None:
        return None
    # Convert pandas Series to plain dict to avoid index issues in Jinja2
    if hasattr(teacher, 'to_dict'):
        return teacher.to_dict()
    return dict(teacher)

def teacher_or_redirect():
    """Returns teacher dict, or redirects to login if not found."""
    from flask import abort
    t = get_teacher()
    if t is None:
        from flask import session as s
        s.clear()
        return None
    return t

def get_semester():
    now = datetime.now()
    return f"{'ODD' if now.month >= 6 else 'EVEN'}-{now.year}"

# ── HOME ─────────────────────────────────────────────────────
@teacher_bp.route("/home")
@teacher_required
def home():
    from services.attendance_service import get_attendance_stats, check_attendance_exists, get_attendance_for_date, get_teacher_attendance
    from services.leave_service      import get_leave_balance, get_teacher_leave_requests
    from services.feedback_service   import get_feedback_by_teacher
    from database.connection import get_db_connection
    import pandas as pd

    tid     = session["user_id"]
    teacher = get_teacher()
    today   = datetime.now().strftime("%Y-%m-%d")
    stats   = get_attendance_stats(tid)
    balance = get_leave_balance(tid)
    fb_df   = get_feedback_by_teacher(tid)
    avail   = int(balance['available_days'].sum()) if len(balance) > 0 else 0
    existing = check_attendance_exists(tid, today)
    today_record = get_attendance_for_date(tid, today) if existing else None
    pending_leaves = get_teacher_leave_requests(tid)
    pending_leaves = pending_leaves[pending_leaves['status'] == 'Pending'].to_dict('records') if len(pending_leaves) > 0 else []
    recent = get_teacher_attendance(tid, limit=14)

    hour = datetime.now().hour
    greeting = "Good morning" if hour < 12 else "Good afternoon" if hour < 17 else "Good evening"

    with get_db_connection() as conn:
        announcements = pd.read_sql_query(
            "SELECT * FROM announcements ORDER BY created_at DESC LIMIT 5", conn
        ).to_dict('records')

    return render_template("teacher/home.html",
        teacher=teacher, stats=stats, avail=avail,
        feedback_count=len(fb_df), greeting=greeting,
        today=today, existing=existing, today_record=today_record,
        pending_leaves=pending_leaves,
        recent=recent.to_dict('records') if len(recent) > 0 else [],
        announcements=announcements,
    )

# ── ATTENDANCE ───────────────────────────────────────────────
@teacher_bp.route("/attendance")
@teacher_required
def attendance():
    from services.attendance_service import get_attendance_stats, check_attendance_exists, get_teacher_attendance, get_attendance_for_date
    tid     = session["user_id"]
    teacher = get_teacher()
    today   = datetime.now().strftime("%Y-%m-%d")
    stats   = get_attendance_stats(tid)
    existing = check_attendance_exists(tid, today)
    today_record = get_attendance_for_date(tid, today) if existing else None
    records  = get_teacher_attendance(tid)
    return render_template("teacher/attendance.html",
        teacher=teacher, stats=stats, existing=existing,
        today_record=today_record, today=today,
        records=records.to_dict('records') if len(records) > 0 else [],
    )

import math

# ── Attendance constants ──────────────────────────────────────
ATTENDANCE_START   = "08:45"
ATTENDANCE_END     = "20:30"
COLLEGE_LAT        = 18.974072
COLLEGE_LON        = 79.459449
ALLOWED_RADIUS_KM  = 5.0

def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi       = math.radians(lat2 - lat1)
    dlambda    = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

@teacher_bp.route("/attendance/mark", methods=["POST"])
@teacher_required
def mark_attendance():
    from services.attendance_service import add_attendance
    from flask import jsonify
    tid     = session["user_id"]
    teacher = get_teacher()
    today   = datetime.now().strftime("%Y-%m-%d")
    now_t   = datetime.now().time()

    # Check if request is JSON (from fetch) or form
    is_ajax = request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    def respond(ok, msg):
        if is_ajax:
            return jsonify({"ok": ok, "msg": msg})
        flash(msg, "success" if ok else "error")
        return redirect(url_for("teacher.attendance"))

    # 1. Time window check
    start = datetime.strptime(ATTENDANCE_START, "%H:%M").time()
    end   = datetime.strptime(ATTENDANCE_END,   "%H:%M").time()
    if not (start <= now_t <= end):
        return respond(False,
            f"⏰ Attendance window is {ATTENDANCE_START} – {ATTENDANCE_END} only. "
            f"Current time: {now_t.strftime('%H:%M')}."
        )

    # 2. GPS check
    data = request.get_json(silent=True) or {}
    lat  = data.get("latitude")  or request.form.get("latitude")
    lon  = data.get("longitude") or request.form.get("longitude")

    if lat is None or lon is None:
        return respond(False, "📍 Location access is required to mark attendance.")

    try:
        lat, lon = float(lat), float(lon)
    except (ValueError, TypeError):
        return respond(False, "📍 Invalid location data.")

    dist_km = haversine_km(lat, lon, COLLEGE_LAT, COLLEGE_LON)
    if dist_km > ALLOWED_RADIUS_KM:
        return respond(False,
            f"📍 You are {dist_km:.1f} km away from college. "
            f"Must be within {ALLOWED_RADIUS_KM} km to mark attendance."
        )

    # 3. Mark attendance
    ok, msg = add_attendance(
        teacher_id=tid, name=teacher['name'],
        department=teacher['department'], date=today,
        checkin_time=datetime.now().strftime("%H:%M:%S"),
        latitude=lat, longitude=lon,
        status="Present", distance_km=round(dist_km, 3)
    )
    return respond(ok, msg)

# ── LEAVE ────────────────────────────────────────────────────
@teacher_bp.route("/leave")
@teacher_required
def leave():
    from services.leave_service import get_teacher_leave_requests, get_leave_balance, LEAVE_TYPES
    tid      = session["user_id"]
    teacher  = get_teacher()
    requests = get_teacher_leave_requests(tid)
    balance  = get_leave_balance(tid)
    return render_template("teacher/leave.html",
        teacher=teacher,
        requests=requests.to_dict('records') if len(requests) > 0 else [],
        balance=balance.to_dict('records') if len(balance) > 0 else [],
        leave_types=LEAVE_TYPES, today=date.today().isoformat(),
    )

@teacher_bp.route("/leave/apply", methods=["POST"])
@teacher_required
def apply_leave():
    from services.leave_service import apply_leave as svc_apply
    tid = session["user_id"]
    ok, msg = svc_apply(
        tid, request.form['leave_type'],
        request.form['from_date'], request.form['to_date'],
        request.form['reason']
    )
    flash(msg, "success" if ok else "error")
    return redirect(url_for("teacher.leave"))

@teacher_bp.route("/leave/cancel/<int:leave_id>", methods=["POST"])
@teacher_required
def cancel_leave(leave_id):
    from services.leave_service import cancel_leave_request
    ok, msg = cancel_leave_request(leave_id, session["user_id"])
    flash(msg, "success" if ok else "error")
    return redirect(url_for("teacher.leave"))

# ── SUBJECT PREFERENCE ───────────────────────────────────────
@teacher_bp.route("/preference")
@teacher_required
def preference():
    from services.allocation_service import (
        current_semester, get_subjects_for_dept,
        get_teacher_preferences, get_teacher_allocation
    )
    tid     = session["user_id"]
    teacher = get_teacher()
    sem     = current_semester()
    subjects = get_subjects_for_dept(teacher['department'])
    existing = get_teacher_preferences(tid, sem)
    allocation = get_teacher_allocation(tid, sem)
    return render_template("teacher/preference.html",
        teacher=teacher, sem=sem,
        subjects=subjects, existing=existing,
        allocation=allocation,
    )

@teacher_bp.route("/preference/submit", methods=["POST"])
@teacher_required
def submit_preference():
    from services.allocation_service import submit_preferences, current_semester
    tid  = session["user_id"]
    sem  = current_semester()
    chosen = [
        request.form.get('pref1',''),
        request.form.get('pref2',''),
        request.form.get('pref3',''),
    ]
    chosen = [s for s in chosen if s]
    if not chosen:
        flash("Please select at least one subject.", "error")
        return redirect(url_for("teacher.preference"))
    ok, msg = submit_preferences(tid, sem, chosen)
    flash(msg, "success" if ok else "error")
    return redirect(url_for("teacher.preference"))

# ── PROFILE ──────────────────────────────────────────────────
@teacher_bp.route("/profile")
@teacher_required
def profile():
    from services.feedback_service   import get_feedback_by_teacher
    from services.attendance_service import get_attendance_stats
    tid     = session["user_id"]
    teacher = get_teacher()
    fb_df   = get_feedback_by_teacher(tid)
    stats   = get_attendance_stats(tid)
    pos = len(fb_df[fb_df['sentiment_score'] >  0.2]) if len(fb_df) > 0 else 0
    neg = len(fb_df[fb_df['sentiment_score'] < -0.2]) if len(fb_df) > 0 else 0
    neu = len(fb_df) - pos - neg if len(fb_df) > 0 else 0
    att_s  = float(stats['attendance_percent'])
    rat_s  = (float(teacher['student_rating']) / 5.0) * 100
    sent_s = ((float(teacher.get('sentiment_score', 0)) + 1) / 2.0) * 100
    perf   = round(att_s * 0.4 + rat_s * 0.4 + sent_s * 0.2, 1)
    return render_template("teacher/profile.html",
        teacher=teacher, stats=stats, perf=perf,
        fb_df=fb_df.to_dict('records') if len(fb_df) > 0 else [],
        pos=pos, neg=neg, neu=neu,
        att_contrib=round(att_s * 0.4, 1),
        rat_contrib=round(rat_s * 0.4, 1),
        sent_contrib=round(sent_s * 0.2, 1),
    )