from flask import Blueprint, render_template, request, session, redirect, url_for, flash, jsonify
from functools import wraps
from datetime import datetime

admin_bp = Blueprint("admin", __name__)

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session or session.get("role") != "admin":
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated

def get_semester():
    now = datetime.now()
    return f"{'ODD' if now.month >= 6 else 'EVEN'}-{now.year}"

# ── OVERVIEW ─────────────────────────────────────────────────
@admin_bp.route("/overview")
@admin_required
def overview():
    from services.attendance_service import get_todays_attendance_summary, get_department_stats
    from services.leave_service      import get_leave_summary
    from services.feedback_service   import get_all_feedback

    att        = get_todays_attendance_summary()
    lv         = get_leave_summary()
    all_fb     = get_all_feedback()
    pos_fb     = len(all_fb[all_fb['sentiment_score'] >  0.2]) if len(all_fb) > 0 else 0
    neg_fb     = len(all_fb[all_fb['sentiment_score'] < -0.2]) if len(all_fb) > 0 else 0
    dept_stats = get_department_stats()

    dept_labels = dept_stats['department'].tolist() if len(dept_stats) > 0 else []
    dept_values = [round(float(v), 1) for v in dept_stats['avg_attendance'].tolist()] if len(dept_stats) > 0 else []

    return render_template("admin/overview.html",
        att=att, lv=lv,
        total_feedback=len(all_fb),
        pos_feedback=pos_fb, neg_feedback=neg_fb,
        dept_stats=dept_stats.to_dict('records') if len(dept_stats) > 0 else [],
        dept_labels=dept_labels, dept_values=dept_values,
        semester=get_semester()
    )

# ── MANAGE TEACHERS ──────────────────────────────────────────
@admin_bp.route("/teachers")
@admin_required
def teachers():
    from services.teacher_service import get_all_teachers
    df = get_all_teachers()
    return render_template("admin/teachers.html",
        teachers=df.to_dict('records'), active='teachers')

@admin_bp.route("/teachers/add", methods=["POST"])
@admin_required
def add_teacher():
    from services.teacher_service import add_new_teacher
    ok, msg = add_new_teacher(
        request.form['teacher_id'], request.form['name'],
        request.form['department'], request.form['subject'],
        int(request.form['experience_years']), 100,
        float(request.form['student_rating']),
        int(request.form['workload_hours'])
    )
    flash(msg, "success" if ok else "error")
    return redirect(url_for("admin.teachers"))

@admin_bp.route("/teachers/delete/<teacher_id>", methods=["POST"])
@admin_required
def delete_teacher(teacher_id):
    from services.teacher_service import delete_teacher as svc_delete
    ok, msg = svc_delete(teacher_id)
    flash(msg, "success" if ok else "error")
    return redirect(url_for("admin.teachers"))

@admin_bp.route("/teachers/reset/<teacher_id>", methods=["POST"])
@admin_required
def reset_password(teacher_id):
    from services.auth_service import reset_teacher_password
    ok, msg = reset_teacher_password(teacher_id)
    flash(msg, "success" if ok else "error")
    return redirect(url_for("admin.teachers"))

# ── ATTENDANCE ───────────────────────────────────────────────
@admin_bp.route("/attendance")
@admin_required
def attendance():
    from services.attendance_service import get_all_attendance, get_department_stats, get_todays_attendance_summary
    records    = get_all_attendance()
    dept_stats = get_department_stats()
    summary    = get_todays_attendance_summary()
    dept_f     = request.args.get('dept', 'All')
    status_f   = request.args.get('status', 'All')
    date_f     = request.args.get('date', '')

    filtered = records.copy()
    if dept_f   != 'All': filtered = filtered[filtered['department'] == dept_f]
    if status_f != 'All': filtered = filtered[filtered['status'] == status_f]
    if date_f.strip():    filtered = filtered[filtered['date'] == date_f.strip()]

    depts = ['All'] + sorted(records['department'].unique().tolist()) if len(records) > 0 else ['All']
    return render_template("admin/attendance.html",
        records=filtered.to_dict('records'),
        total=len(records), filtered=len(filtered),
        dept_stats=dept_stats.to_dict('records') if len(dept_stats) > 0 else [],
        summary=summary, depts=depts,
        dept_f=dept_f, status_f=status_f, date_f=date_f,
        active='attendance'
    )

@admin_bp.route("/attendance/export")
@admin_required
def export_attendance():
    import csv, io
    from flask import Response
    from services.attendance_service import get_all_attendance
    records  = get_all_attendance()
    dept_f   = request.args.get('dept', 'All')
    status_f = request.args.get('status', 'All')
    date_f   = request.args.get('date', '')
    if dept_f   != 'All': records = records[records['department'] == dept_f]
    if status_f != 'All': records = records[records['status'] == status_f]
    if date_f.strip():    records = records[records['date'] == date_f.strip()]

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Name', 'Department', 'Date', 'Status', 'Check-in Time'])
    for _, r in records.iterrows():
        writer.writerow([r['name'], r['department'], r['date'], r['status'], r.get('checkin_time') or ''])
    output.seek(0)
    filename = f"attendance_{date_f or 'all'}.csv"
    return Response(output, mimetype='text/csv',
        headers={"Content-Disposition": f"attachment; filename={filename}"})

# ── ANNOUNCEMENTS ────────────────────────────────────────────
@admin_bp.route("/announcements")
@admin_required
def announcements():
    from database.connection import get_db_connection
    import pandas as pd
    with get_db_connection() as conn:
        ann = pd.read_sql_query("SELECT * FROM announcements ORDER BY created_at DESC", conn)
    return render_template("admin/announcements.html",
        announcements=ann.to_dict('records'),
        active='announcements'
    )

@admin_bp.route("/announcements/post", methods=["POST"])
@admin_required
def post_announcement():
    from database.connection import get_db_connection
    title = request.form.get('title', '').strip()
    body  = request.form.get('body', '').strip()
    if not title or not body:
        flash("Title and message are required.", "error")
        return redirect(url_for("admin.announcements"))
    with get_db_connection() as conn:
        conn.execute("INSERT INTO announcements (title, body) VALUES (?, ?)", (title, body))
        conn.commit()
    flash("✅ Announcement posted!", "success")
    return redirect(url_for("admin.announcements"))

@admin_bp.route("/announcements/delete/<int:ann_id>", methods=["POST"])
@admin_required
def delete_announcement(ann_id):
    from database.connection import get_db_connection
    with get_db_connection() as conn:
        conn.execute("DELETE FROM announcements WHERE id = ?", (ann_id,))
        conn.commit()
    flash("Announcement deleted.", "success")
    return redirect(url_for("admin.announcements"))

# ── LEAVE ────────────────────────────────────────────────────
@admin_bp.route("/leave")
@admin_required
def leave():
    from services.leave_service import get_all_leave_requests, get_leave_summary, get_all_leave_balances
    summary  = get_leave_summary()
    pending  = get_all_leave_requests("Pending")
    all_req  = get_all_leave_requests(request.args.get('filter', 'All'))
    balances = get_all_leave_balances()
    return render_template("admin/leave.html",
        summary=summary,
        pending=pending.to_dict('records'),
        all_req=all_req.to_dict('records'),
        balances=balances.to_dict('records'),
        status_filter=request.args.get('filter', 'All'),
        active='leave'
    )

@admin_bp.route("/leave/<int:leave_id>/action", methods=["POST"])
@admin_required
def leave_action(leave_id):
    from services.leave_service import update_leave_status, get_all_leave_requests
    from services.notification_service import notify_leave_action
    action = request.form.get('action')
    note   = request.form.get('note', '')
    ok, msg = update_leave_status(leave_id, action, note)
    if ok:
        # Find teacher info for notification
        from database.connection import get_db_connection
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT lr.teacher_id, t.name, lr.leave_type
                FROM leave_requests lr
                JOIN teachers t ON lr.teacher_id = t.teacher_id
                WHERE lr.id = ?
            """, (leave_id,))
            row = cursor.fetchone()
            if row:
                notify_leave_action(row[0], row[1], row[2], action, note)
    flash(msg, "success" if ok else "error")
    return redirect(url_for("admin.leave"))

# ── FEEDBACK ─────────────────────────────────────────────────
@admin_bp.route("/feedback")
@admin_required
def feedback():
    from services.feedback_service import get_all_feedback, get_sentiment_summary
    all_fb  = get_all_feedback()
    summary = get_sentiment_summary()
    pos = len(all_fb[all_fb['sentiment_score'] >  0.2]) if len(all_fb) > 0 else 0
    neg = len(all_fb[all_fb['sentiment_score'] < -0.2]) if len(all_fb) > 0 else 0
    neu = len(all_fb) - pos - neg

    dept_f = request.args.get('dept', '')
    tone_f = request.args.get('tone', '')
    filtered = all_fb.copy()
    if dept_f: filtered = filtered[filtered['department'] == dept_f]
    if tone_f == 'Appreciative': filtered = filtered[filtered['sentiment_score'] >  0.2]
    elif tone_f == 'Mixed':      filtered = filtered[filtered['sentiment_score'] < -0.2]
    elif tone_f == 'Neutral':    filtered = filtered[(filtered['sentiment_score'] >= -0.2) & (filtered['sentiment_score'] <= 0.2)]

    depts = [''] + sorted(all_fb['department'].unique().tolist()) if len(all_fb) > 0 else ['']
    return render_template("admin/feedback.html",
        feedback=filtered.to_dict('records'),
        summary=summary.to_dict('records') if len(summary) > 0 else [],
        total=len(all_fb), pos=pos, neg=neg, neu=neu,
        depts=depts, dept_f=dept_f, tone_f=tone_f,
        active='feedback'
    )

@admin_bp.route("/feedback/delete/<int:fb_id>", methods=["POST"])
@admin_required
def delete_feedback(fb_id):
    from services.feedback_service import delete_feedback as svc_del
    ok, msg = svc_del(fb_id)
    flash(msg, "success" if ok else "error")
    return redirect(url_for("admin.feedback"))

# ── SUBJECT ALLOCATION ───────────────────────────────────────
@admin_bp.route("/allocation")
@admin_required
def allocation():
    from services.allocation_service import (
        get_all_semesters, current_semester, get_submission_status,
        get_all_preferences, get_draft_allocations, get_finalized_allocations,
        allocation_is_drafted, allocation_is_finalized, get_subjects_for_dept
    )
    sem        = request.args.get('sem', current_semester())
    semesters  = get_all_semesters()
    if sem not in semesters: semesters = [sem] + semesters

    sub_status = get_submission_status(sem)
    prefs_df   = get_all_preferences(sem)
    draft_df   = get_draft_allocations(sem)
    final_df   = get_finalized_allocations(sem)
    is_drafted   = allocation_is_drafted(sem)
    is_finalized = allocation_is_finalized(sem)

    # subjects per dept for override dropdowns
    dept_subjects = {}
    for _, row in draft_df.iterrows():
        dept = row['department']
        if dept not in dept_subjects:
            dept_subjects[dept] = get_subjects_for_dept(dept)

    # detect subject preference conflicts (rank-1 clashes)
    pref_conflicts = []
    if len(prefs_df) > 0 and 'rank' in prefs_df.columns and 'subject' in prefs_df.columns:
        top_prefs = prefs_df[prefs_df['rank'] == 1]
        counts = top_prefs.groupby('subject')['teacher_id'].apply(list).reset_index()
        for _, row in counts.iterrows():
            if len(row['teacher_id']) > 1:
                pref_conflicts.append({
                    'subject': row['subject'],
                    'count': len(row['teacher_id'])
                })

    return render_template("admin/allocation.html",
        sem=sem, semesters=semesters,
        sub_status=sub_status.to_dict('records'),
        submitted=int(sub_status['submitted'].sum()) if len(sub_status) > 0 and 'submitted' in sub_status.columns else 0,
        pending=int((~sub_status['submitted']).sum()) if len(sub_status) > 0 and 'submitted' in sub_status.columns else 0,
        prefs=prefs_df.to_dict('records') if len(prefs_df) > 0 else [],
        draft=draft_df.to_dict('records') if len(draft_df) > 0 else [],
        final=final_df.to_dict('records') if len(final_df) > 0 else [],
        is_drafted=is_drafted, is_finalized=is_finalized,
        dept_subjects=dept_subjects,
        pref_conflicts=pref_conflicts,
        active='allocation'
    )

@admin_bp.route("/allocation/run", methods=["POST"])
@admin_required
def run_allocation():
    from services.allocation_service import run_allocation as svc_run
    sem = request.form['sem']
    results = svc_run(sem)
    flash(f"✅ Draft allocation created for {len(results)} teachers.", "success")
    return redirect(url_for("admin.allocation", sem=sem))

@admin_bp.route("/allocation/override", methods=["POST"])
@admin_required
def override_allocation():
    from services.allocation_service import override_allocation as svc_override
    sem = request.form['sem']
    ok, msg = svc_override(request.form['teacher_id'], sem, request.form['new_subject'])
    flash(msg, "success" if ok else "error")
    return redirect(url_for("admin.allocation", sem=sem))

@admin_bp.route("/allocation/finalize", methods=["POST"])
@admin_required
def finalize_allocation():
    from services.allocation_service import finalize_allocation as svc_finalize
    from services.notification_service import notify_allocation_finalized
    sem = request.form['sem']
    ok, msg = svc_finalize(sem)
    if ok:
        notify_allocation_finalized(sem)
    flash(msg, "success" if ok else "error")
    return redirect(url_for("admin.allocation", sem=sem))

# ── REPORTS ──────────────────────────────────────────────────
@admin_bp.route("/reports")
@admin_required
def reports():
    from services.teacher_service    import get_all_teachers
    from services.attendance_service import get_attendance_stats
    from services.feedback_service   import get_all_feedback

    teachers = get_all_teachers()
    all_fb   = get_all_feedback()
    report   = []

    for _, t in teachers.iterrows():
        tid   = str(t['teacher_id'])
        stats = get_attendance_stats(tid)
        t_fb  = all_fb[all_fb['teacher_name'] == t['name']] if len(all_fb) > 0 else all_fb.head(0)
        pos   = len(t_fb[t_fb['sentiment_score'] >  0.2]) if len(t_fb) > 0 else 0
        neg   = len(t_fb[t_fb['sentiment_score'] < -0.2]) if len(t_fb) > 0 else 0
        att_s = min(float(stats['attendance_percent']), 100)
        rat_s = (float(t['student_rating']) / 5.0) * 100
        sent_s= ((float(t['sentiment_score']) + 1) / 2.0) * 100
        perf  = round(att_s * 0.4 + rat_s * 0.4 + sent_s * 0.2, 1)

        if   perf >= 80: label = "Outstanding"
        elif perf >= 65: label = "Proficient"
        elif perf >= 50: label = "Developing"
        else:            label = "Needs Support"

        report.append({
            'teacher_id':    t['teacher_id'],
            'name':          t['name'],
            'department':    t['department'],
            'subject':       t['subject'],
            'experience':    int(t['experience_years']),
            'rating':        float(t['student_rating']),
            'sentiment':     round(float(t['sentiment_score']), 3),
            'attendance':    stats['attendance_percent'],
            'present_days':  stats['present_days'],
            'feedback_count':len(t_fb),
            'pos_feedback':  pos,
            'neg_feedback':  neg,
            'perf_score':    perf,
            'perf_label':    label,
        })

    sort_by = request.args.get('sort', 'perf_score')
    dept_f  = request.args.get('dept', '')
    if dept_f: report = [r for r in report if r['department'] == dept_f]
    report.sort(key=lambda x: x.get(sort_by, 0), reverse=True)

    depts = [''] + sorted(set(r['department'] for r in report))
    return render_template("admin/reports.html",
        report=report, depts=depts,
        dept_f=dept_f, sort_by=sort_by,
        active='reports'
    )