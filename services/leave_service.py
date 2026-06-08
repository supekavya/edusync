"""
services/leave_service.py
All leave request operations for EDUSYNC
"""

import pandas as pd
import sqlite3
from datetime import datetime, date
from database.connection import get_db_connection


# ===========================
# LEAVE TYPES & BALANCE
# ===========================

LEAVE_TYPES = ["Casual Leave", "Medical Leave", "Earned Leave", "Emergency Leave"]

# Default annual leave balance per type
DEFAULT_BALANCE = {
    "Casual Leave":   12,
    "Medical Leave":  10,
    "Earned Leave":   15,
    "Emergency Leave": 5,
}


# ===========================
# INIT LEAVE BALANCE FOR A TEACHER
# ===========================

def init_leave_balance(teacher_id):
    """Create default leave balance for a new teacher if not already present."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        for leave_type, total in DEFAULT_BALANCE.items():
            cursor.execute("""
                INSERT OR IGNORE INTO leave_balance
                    (teacher_id, leave_type, total_days, used_days)
                VALUES (?, ?, ?, 0)
            """, (teacher_id, leave_type, total))
        conn.commit()


# ===========================
# APPLY FOR LEAVE
# ===========================

def apply_leave(teacher_id, leave_type, from_date, to_date, reason):
    """Submit a leave request. Returns (success, message)."""
    try:
        from_dt = datetime.strptime(from_date, "%Y-%m-%d").date()
        to_dt   = datetime.strptime(to_date,   "%Y-%m-%d").date()

        if to_dt < from_dt:
            return False, "End date cannot be before start date."

        days_requested = (to_dt - from_dt).days + 1

        # Check for overlapping pending/approved requests
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM leave_requests
                WHERE teacher_id = ?
                  AND status IN ('Pending', 'Approved')
                  AND NOT (to_date < ? OR from_date > ?)
            """, (teacher_id, from_date, to_date))
            overlap = cursor.fetchone()[0]

        if overlap > 0:
            return False, "You already have a leave request overlapping these dates."

        # Check available balance
        balance = get_leave_balance(teacher_id)
        row = balance[balance['leave_type'] == leave_type]
        if len(row) == 0:
            return False, "Invalid leave type."

        available = int(row.iloc[0]['available_days'])
        if days_requested > available:
            return False, f"Insufficient balance. You have {available} day(s) available for {leave_type}."

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO leave_requests
                    (teacher_id, leave_type, from_date, to_date, days_requested, reason, status)
                VALUES (?, ?, ?, ?, ?, ?, 'Pending')
            """, (teacher_id, leave_type, from_date, to_date, days_requested, reason))
            conn.commit()

        return True, f"Leave request submitted successfully for {days_requested} day(s)."

    except Exception as e:
        return False, str(e)


# ===========================
# GET REQUESTS FOR A TEACHER
# ===========================

def get_teacher_leave_requests(teacher_id):
    with get_db_connection() as conn:
        return pd.read_sql_query("""
            SELECT id, leave_type, from_date, to_date, days_requested,
                   reason, status, admin_note, applied_at
            FROM leave_requests
            WHERE teacher_id = ?
            ORDER BY applied_at DESC
        """, conn, params=(str(teacher_id),))


# ===========================
# GET ALL REQUESTS (ADMIN)
# ===========================

def get_all_leave_requests(status_filter=None):
    with get_db_connection() as conn:
        if status_filter and status_filter != "All":
            return pd.read_sql_query("""
                SELECT lr.id, t.name AS teacher_name, t.department,
                       lr.leave_type, lr.from_date, lr.to_date,
                       lr.days_requested, lr.reason, lr.status,
                       lr.admin_note, lr.applied_at
                FROM leave_requests lr
                JOIN teachers t ON lr.teacher_id = t.teacher_id
                WHERE lr.status = ?
                ORDER BY lr.applied_at DESC
            """, conn, params=(status_filter,))
        else:
            return pd.read_sql_query("""
                SELECT lr.id, t.name AS teacher_name, t.department,
                       lr.leave_type, lr.from_date, lr.to_date,
                       lr.days_requested, lr.reason, lr.status,
                       lr.admin_note, lr.applied_at
                FROM leave_requests lr
                JOIN teachers t ON lr.teacher_id = t.teacher_id
                ORDER BY lr.applied_at DESC
            """, conn)


# ===========================
# APPROVE / REJECT (ADMIN)
# ===========================

def update_leave_status(request_id, action, admin_note=""):
    """action: 'Approved' or 'Rejected'"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            # Fetch request details
            cursor.execute("""
                SELECT teacher_id, leave_type, days_requested, status
                FROM leave_requests WHERE id = ?
            """, (request_id,))
            row = cursor.fetchone()

            if not row:
                return False, "Request not found."

            teacher_id, leave_type, days, current_status = row

            if current_status != "Pending":
                return False, f"This request is already {current_status}."

            # Update request status
            cursor.execute("""
                UPDATE leave_requests
                SET status = ?, admin_note = ?, reviewed_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (action, admin_note, request_id))

            # Deduct balance only on approval
            if action == "Approved":
                cursor.execute("""
                    UPDATE leave_balance
                    SET used_days = used_days + ?
                    WHERE teacher_id = ? AND leave_type = ?
                """, (days, teacher_id, leave_type))

            conn.commit()

        return True, f"Leave request {action.lower()} successfully."

    except Exception as e:
        return False, str(e)


# ===========================
# CANCEL A PENDING REQUEST (TEACHER)
# ===========================

def cancel_leave_request(request_id, teacher_id):
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT status FROM leave_requests
                WHERE id = ? AND teacher_id = ?
            """, (request_id, str(teacher_id)))
            row = cursor.fetchone()

            if not row:
                return False, "Request not found."
            if row[0] != "Pending":
                return False, f"Cannot cancel a request that is already {row[0]}."

            cursor.execute("""
                UPDATE leave_requests SET status = 'Cancelled'
                WHERE id = ?
            """, (request_id,))
            conn.commit()

        return True, "Leave request cancelled."

    except Exception as e:
        return False, str(e)


# ===========================
# GET LEAVE BALANCE
# ===========================

def get_leave_balance(teacher_id):
    with get_db_connection() as conn:
        df = pd.read_sql_query("""
            SELECT leave_type, total_days, used_days,
                   (total_days - used_days) AS available_days
            FROM leave_balance
            WHERE teacher_id = ?
            ORDER BY leave_type
        """, conn, params=(str(teacher_id),))

    # If no balance rows yet, init and retry
    if len(df) == 0:
        init_leave_balance(teacher_id)
        with get_db_connection() as conn:
            df = pd.read_sql_query("""
                SELECT leave_type, total_days, used_days,
                       (total_days - used_days) AS available_days
                FROM leave_balance
                WHERE teacher_id = ?
                ORDER BY leave_type
            """, conn, params=(str(teacher_id),))

    return df


# ===========================
# ADMIN – ALL BALANCES
# ===========================

def get_all_leave_balances():
    with get_db_connection() as conn:
        return pd.read_sql_query("""
            SELECT t.name AS teacher_name, t.department,
                   lb.leave_type, lb.total_days, lb.used_days,
                   (lb.total_days - lb.used_days) AS available_days
            FROM leave_balance lb
            JOIN teachers t ON lb.teacher_id = t.teacher_id
            ORDER BY t.name, lb.leave_type
        """, conn)


# ===========================
# SUMMARY STATS (ADMIN)
# ===========================

def get_leave_summary():
    with get_db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM leave_requests WHERE status = 'Pending'")
        pending = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM leave_requests WHERE status = 'Approved'")
        approved = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM leave_requests WHERE status = 'Rejected'")
        rejected = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM leave_requests WHERE status = 'Cancelled'")
        cancelled = cursor.fetchone()[0]

        return {
            "pending": pending,
            "approved": approved,
            "rejected": rejected,
            "cancelled": cancelled,
            "total": pending + approved + rejected + cancelled
        }