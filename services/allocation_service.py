"""
services/allocation_service.py
EDUSYNC – Subject Preference & Allocation Service

Flow:
  1. Teacher submits ranked preferences (submit_preferences)
  2. Admin runs allocation (run_allocation)       → status = Draft
  3. Admin reviews / overrides (override_allocation)
  4. Admin finalizes (finalize_allocation)        → status = Finalized
  5. Teacher sees result (get_teacher_allocation) → only if Finalized
"""

import pandas as pd
from datetime import datetime
from database.connection import get_db_connection
from services.teacher_service import get_all_teachers, get_teacher_by_id


# ─────────────────────────────────────────────────────────────
# SEMESTER HELPERS
# ─────────────────────────────────────────────────────────────

def current_semester():
    """Returns e.g. 'ODD-2025' or 'EVEN-2026'."""
    now = datetime.now()
    term = "ODD" if now.month >= 6 else "EVEN"
    return f"{term}-{now.year}"


def get_all_semesters():
    """Return distinct semesters that have any preference submissions."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT DISTINCT semester FROM subject_preferences ORDER BY semester DESC"
        )
        rows = cursor.fetchall()
        return [r[0] for r in rows] or [current_semester()]


# ─────────────────────────────────────────────────────────────
# SUBJECT POOL (same as before, per department)
# ─────────────────────────────────────────────────────────────

def _ensure_tables():
    """Create allocation tables if they don't exist yet."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS subject_preferences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_id TEXT NOT NULL,
                semester TEXT NOT NULL,
                rank INTEGER NOT NULL,
                subject TEXT NOT NULL,
                submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(teacher_id, semester, rank)
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS subject_allocations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_id TEXT NOT NULL,
                semester TEXT NOT NULL,
                allocated_subject TEXT NOT NULL,
                preference_rank INTEGER,
                status TEXT DEFAULT 'Draft'
                    CHECK(status IN ('Draft', 'Finalized')),
                overridden_by_admin INTEGER DEFAULT 0,
                finalized_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(teacher_id, semester)
            )
        ''')
        conn.commit()

_ensure_tables()


DEPT_SUBJECTS = {
    "Computer Science and Engineering":          ["Data Structures", "Operating Systems",
                                                  "Database Systems", "Algorithms", "Computer Networks"],
    "Information Technology":                    ["Web Technologies", "Software Engineering",
                                                  "Cloud Computing", "Cybersecurity"],
    "Electronics and Communication Engineering": ["Digital Electronics", "Microprocessors",
                                                  "VLSI Design", "Signal Processing", "Analog Circuits"],
    "Electrical and Electronics Engineering":    ["Power Electronics", "Electrical Machines",
                                                  "Control Systems", "Power Systems", "Circuit Theory"],
    "Mechanical Engineering":                    ["Thermodynamics", "Machine Design",
                                                  "Fluid Mechanics", "Manufacturing", "Heat Transfer"],
    "Civil Engineering":                         ["Structural Engineering", "Surveying",
                                                  "Transportation Eng.", "Geotechnical Engineering"],
    "Artificial Intelligence & ML":              ["Machine Learning", "Deep Learning",
                                                  "Computer Vision", "Natural Language Processing",
                                                  "Reinforcement Learning"],
    "Mathematics":                               ["Linear Algebra", "Probability", "Calculus",
                                                  "Discrete Math", "Statistics", "Numerical Methods"],
    "Physics":                                   ["Engineering Physics", "Quantum Mechanics",
                                                  "Electromagnetism", "Optics"],
    "Chemistry":                                 ["Engineering Chemistry", "Organic Chemistry",
                                                  "Physical Chemistry", "Analytical Chemistry"],
    "Humanities & Sciences":                     ["Technical Writing", "Professional Ethics",
                                                  "Economics", "Sociology", "Psychology", "English"],
    # Legacy fallbacks
    "Basic Sciences":   ["Engineering Mathematics", "Engineering Physics", "Engineering Chemistry"],
    "AI & ML":          ["Machine Learning", "Deep Learning", "Computer Vision"],
    "Humanities":       ["Technical Writing", "Professional Ethics"],
}


def get_subjects_for_dept(department):
    return DEPT_SUBJECTS.get(department, [])


# ─────────────────────────────────────────────────────────────
# PREFERENCES
# ─────────────────────────────────────────────────────────────

def submit_preferences(teacher_id, semester, ranked_subjects):
    """
    Save a teacher's ranked preference list.
    ranked_subjects = ["Data Structures", "Algorithms", "OS"]  (index 0 = rank 1)
    Replaces any existing submission for this teacher/semester.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        # Clear old submission first
        cursor.execute(
            "DELETE FROM subject_preferences WHERE teacher_id=? AND semester=?",
            (str(teacher_id), semester)
        )
        for rank, subject in enumerate(ranked_subjects, start=1):
            if subject:
                cursor.execute("""
                    INSERT INTO subject_preferences
                        (teacher_id, semester, rank, subject)
                    VALUES (?, ?, ?, ?)
                """, (str(teacher_id), semester, rank, subject))
        conn.commit()
    return True, "Preferences submitted successfully"


def get_teacher_preferences(teacher_id, semester):
    """Returns list of subjects in rank order for a teacher."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT subject FROM subject_preferences
            WHERE teacher_id=? AND semester=?
            ORDER BY rank ASC
        """, (str(teacher_id), semester))
        return [r[0] for r in cursor.fetchall()]


def get_all_preferences(semester):
    """Returns DataFrame of all preferences for a semester."""
    with get_db_connection() as conn:
        return pd.read_sql_query("""
            SELECT sp.teacher_id, t.name, t.department,
                   t.experience_years, t.student_rating,
                   sp.rank, sp.subject, sp.submitted_at
            FROM subject_preferences sp
            JOIN teachers t ON sp.teacher_id = t.teacher_id
            WHERE sp.semester = ?
            ORDER BY t.name, sp.rank
        """, conn, params=(semester,))


def get_submission_status(semester):
    """
    Returns DataFrame showing which teachers have/haven't submitted.
    """
    teachers = get_all_teachers()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTINCT teacher_id FROM subject_preferences
            WHERE semester = ?
        """, (semester,))
        submitted = {str(r[0]) for r in cursor.fetchall()}

    rows = []
    for _, t in teachers.iterrows():
        tid = str(t["teacher_id"])
        rows.append({
            "teacher_id":  tid,
            "name":        t["name"],
            "department":  t["department"],
            "submitted":   tid in submitted,
        })
    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────
# ALLOCATION ALGORITHM
# ─────────────────────────────────────────────────────────────

def run_allocation(semester):
    """
    Greedy algorithm:
      - Sort teachers by experience DESC, then student_rating DESC (seniority first)
      - For each teacher, assign their highest available preferred subject
      - If none of their preferences are available, assign the first available
        subject in their department
      - Save results as Draft allocations
    Returns list of result dicts.
    """
    teachers = get_all_teachers()

    # Sort by seniority
    teachers = teachers.sort_values(
        ["experience_years", "student_rating"],
        ascending=[False, False]
    )

    # Load all preferences for this semester
    all_prefs = {}
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT teacher_id, subject, rank
            FROM subject_preferences
            WHERE semester = ?
            ORDER BY teacher_id, rank
        """, (semester,))
        for tid, subj, rank in cursor.fetchall():
            all_prefs.setdefault(str(tid), []).append((rank, subj))

    # Sort each teacher's prefs by rank
    for tid in all_prefs:
        all_prefs[tid].sort(key=lambda x: x[0])

    assigned_subjects = set()
    results = []

    for _, teacher in teachers.iterrows():
        tid  = str(teacher["teacher_id"])
        dept = teacher["department"]
        dept_subjects = get_subjects_for_dept(dept)

        allocated_subject  = None
        preference_rank    = None

        # Try each preference in order
        prefs = all_prefs.get(tid, [])
        for rank, subject in prefs:
            if subject not in assigned_subjects:
                allocated_subject = subject
                preference_rank   = rank
                break

        # Fallback: first available subject in department
        if allocated_subject is None:
            for subj in dept_subjects:
                if subj not in assigned_subjects:
                    allocated_subject = subj
                    preference_rank   = None
                    break

        # Last resort: reuse any subject from dept (more teachers than subjects)
        if allocated_subject is None and dept_subjects:
            allocated_subject = dept_subjects[0]
            preference_rank   = None

        # Skip only if department has zero subjects configured
        if allocated_subject is None:
            continue

        assigned_subjects.add(allocated_subject)
        results.append({
            "teacher_id":        tid,
            "name":              teacher["name"],
            "department":        dept,
            "experience_years":  int(teacher["experience_years"]),
            "allocated_subject": allocated_subject,
            "preference_rank":   preference_rank,
            "had_preferences":   tid in all_prefs,
        })

    # Save Draft allocations (replace any existing draft)
    _save_allocations(results, semester)
    return results


def _save_allocations(results, semester):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        # Remove existing DRAFT allocations for this semester
        cursor.execute("""
            DELETE FROM subject_allocations
            WHERE semester=? AND status='Draft'
        """, (semester,))
        for r in results:
            cursor.execute("""
                INSERT INTO subject_allocations
                    (teacher_id, semester, allocated_subject,
                     preference_rank, status, overridden_by_admin)
                VALUES (?, ?, ?, ?, 'Draft', 0)
            """, (r["teacher_id"], semester,
                  r["allocated_subject"], r["preference_rank"]))
        conn.commit()


# ─────────────────────────────────────────────────────────────
# OVERRIDE
# ─────────────────────────────────────────────────────────────

def override_allocation(teacher_id, semester, new_subject):
    """Admin manually changes a Draft allocation."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE subject_allocations
            SET allocated_subject   = ?,
                overridden_by_admin = 1,
                preference_rank     = NULL
            WHERE teacher_id=? AND semester=? AND status='Draft'
        """, (new_subject, str(teacher_id), semester))
        conn.commit()
        if cursor.rowcount == 0:
            return False, "No draft allocation found for this teacher"
    return True, f"Allocation updated to {new_subject}"


# ─────────────────────────────────────────────────────────────
# FINALIZE
# ─────────────────────────────────────────────────────────────

def finalize_allocation(semester):
    """
    Locks all Draft allocations → Finalized.
    Also updates the teachers.subject column so it reflects everywhere.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Check there are drafts to finalize
        cursor.execute("""
            SELECT COUNT(*) FROM subject_allocations
            WHERE semester=? AND status='Draft'
        """, (semester,))
        count = cursor.fetchone()[0]
        if count == 0:
            return False, "No draft allocations to finalize. Run allocation first."

        # Finalize
        cursor.execute("""
            UPDATE subject_allocations
            SET status='Finalized', finalized_at=CURRENT_TIMESTAMP
            WHERE semester=? AND status='Draft'
        """, (semester,))

        # Update teachers.subject column
        cursor.execute("""
            SELECT teacher_id, allocated_subject
            FROM subject_allocations
            WHERE semester=? AND status='Finalized'
        """, (semester,))
        for tid, subj in cursor.fetchall():
            cursor.execute(
                "UPDATE teachers SET subject=? WHERE teacher_id=?",
                (subj, tid)
            )

        conn.commit()
    return True, f"Allocation finalized for {count} teachers"


# ─────────────────────────────────────────────────────────────
# FETCH HELPERS
# ─────────────────────────────────────────────────────────────

def get_draft_allocations(semester):
    """Returns DataFrame of current Draft allocations."""
    with get_db_connection() as conn:
        return pd.read_sql_query("""
            SELECT sa.teacher_id, t.name, t.department,
                   t.experience_years, t.student_rating,
                   sa.allocated_subject, sa.preference_rank,
                   sa.overridden_by_admin, sa.status
            FROM subject_allocations sa
            JOIN teachers t ON sa.teacher_id = t.teacher_id
            WHERE sa.semester=? AND sa.status='Draft'
            ORDER BY t.experience_years DESC, t.student_rating DESC
        """, conn, params=(semester,))


def get_finalized_allocations(semester):
    """Returns DataFrame of Finalized allocations."""
    with get_db_connection() as conn:
        return pd.read_sql_query("""
            SELECT sa.teacher_id, t.name, t.department,
                   t.experience_years,
                   sa.allocated_subject, sa.preference_rank,
                   sa.overridden_by_admin, sa.finalized_at
            FROM subject_allocations sa
            JOIN teachers t ON sa.teacher_id = t.teacher_id
            WHERE sa.semester=? AND sa.status='Finalized'
            ORDER BY t.department, t.name
        """, conn, params=(semester,))


def get_teacher_allocation(teacher_id, semester):
    """
    Returns the finalized allocation for a teacher, or None.
    Teachers only see Finalized — never Draft.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT allocated_subject, preference_rank,
                   overridden_by_admin, finalized_at
            FROM subject_allocations
            WHERE teacher_id=? AND semester=? AND status='Finalized'
        """, (str(teacher_id), semester))
        row = cursor.fetchone()
        if row:
            return {
                "allocated_subject":  row[0],
                "preference_rank":    row[1],
                "overridden_by_admin": row[2],
                "finalized_at":       row[3],
            }
        return None


def allocation_is_finalized(semester):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) FROM subject_allocations
            WHERE semester=? AND status='Finalized'
        """, (semester,))
        return cursor.fetchone()[0] > 0


def allocation_is_drafted(semester):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) FROM subject_allocations
            WHERE semester=? AND status='Draft'
        """, (semester,))
        return cursor.fetchone()[0] > 0