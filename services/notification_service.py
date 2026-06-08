"""
services/notification_service.py
EDUSYNC – Notification Service
"""
import pandas as pd
from database.connection import get_db_connection


def _ensure_table():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recipient_id TEXT NOT NULL,
                title TEXT NOT NULL,
                message TEXT NOT NULL,
                type TEXT DEFAULT 'info',
                is_read INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()

_ensure_table()


def create_notification(recipient_id, title, message, notif_type="info"):
    """Create a notification for a user. type: info | success | warning | danger"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO notifications (recipient_id, title, message, type)
            VALUES (?, ?, ?, ?)
        """, (str(recipient_id), title, message, notif_type))
        conn.commit()


def get_notifications(recipient_id, unread_only=False):
    """Get notifications for a user, newest first."""
    with get_db_connection() as conn:
        query = """
            SELECT * FROM notifications
            WHERE recipient_id = ?
            {}
            ORDER BY created_at DESC
            LIMIT 20
        """.format("AND is_read = 0" if unread_only else "")
        return pd.read_sql_query(query, conn, params=(str(recipient_id),))


def get_unread_count(recipient_id):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) FROM notifications
            WHERE recipient_id = ? AND is_read = 0
        """, (str(recipient_id),))
        return cursor.fetchone()[0]


def mark_all_read(recipient_id):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE notifications SET is_read = 1
            WHERE recipient_id = ?
        """, (str(recipient_id),))
        conn.commit()


def mark_read(notification_id):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE notifications SET is_read=1 WHERE id=?", (notification_id,))
        conn.commit()


# ── Trigger helpers ────────────────────────────────────────────────────────────

def notify_leave_action(teacher_id, teacher_name, leave_type, status, admin_note=""):
    """Called when admin approves or rejects a leave request."""
    if status == "Approved":
        title = "✅ Leave Approved"
        msg   = f"Your {leave_type} request has been approved."
        if admin_note:
            msg += f" Note: {admin_note}"
        ntype = "success"
    else:
        title = "❌ Leave Rejected"
        msg   = f"Your {leave_type} request was rejected."
        if admin_note:
            msg += f" Reason: {admin_note}"
        ntype = "danger"

    create_notification(str(teacher_id), title, msg, ntype)

    # Also notify admin
    create_notification("admin",
        f"Leave {status}",
        f"{teacher_name}'s {leave_type} request has been {status.lower()}.",
        "info"
    )


def notify_allocation_finalized(semester):
    """Called when admin finalizes subject allocation."""
    from database.connection import get_db_connection
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT sa.teacher_id, t.name, sa.allocated_subject
            FROM subject_allocations sa
            JOIN teachers t ON sa.teacher_id = t.teacher_id
            WHERE sa.semester = ? AND sa.status = 'Finalized'
        """, (semester,))
        for tid, name, subject in cursor.fetchall():
            create_notification(
                str(tid),
                "📚 Subject Allocated",
                f"Your subject for {semester} has been finalized: {subject}.",
                "success"
            )


