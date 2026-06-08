import pandas as pd
from datetime import datetime
import sqlite3
from database.connection import get_db_connection


# ===========================
# ADD ATTENDANCE
# ===========================

def add_attendance(teacher_id, name, department, date, checkin_time,
                   latitude, longitude, status, distance_km=None):

    with get_db_connection() as conn:
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO attendance
                (teacher_id, name, department, date, checkin_time,
                 latitude, longitude, status, distance_km)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                teacher_id, name, department, date, checkin_time,
                latitude, longitude, status, distance_km
            ))

            conn.commit()
            return True, "Attendance marked successfully"

        except sqlite3.IntegrityError:
            return False, "Attendance already marked for today"


# ===========================
# CHECK IF ATTENDANCE EXISTS
# ===========================

def check_attendance_exists(teacher_id, date):

    with get_db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT COUNT(*)
            FROM attendance
            WHERE teacher_id = ? AND date = ?
        """, (str(teacher_id), date))

        return cursor.fetchone()[0] > 0


# ===========================
# GET ATTENDANCE FOR SPECIFIC DATE
# ===========================

def get_attendance_for_date(teacher_id, date):

    with get_db_connection() as conn:
        result = pd.read_sql_query("""
            SELECT *
            FROM attendance
            WHERE teacher_id = ? AND date = ?
        """, conn, params=(str(teacher_id), date))

        return result.iloc[0] if len(result) > 0 else None


# ===========================
# GET TEACHER ATTENDANCE
# ===========================

def get_teacher_attendance(teacher_id, limit=None):

    with get_db_connection() as conn:

        query = """
            SELECT *
            FROM attendance
            WHERE teacher_id = ?
            ORDER BY date DESC
        """

        if limit:
            query += f" LIMIT {limit}"

        return pd.read_sql_query(
            query,
            conn,
            params=(str(teacher_id),)
        )


# ===========================
# GET ATTENDANCE STATS
# ===========================

def get_attendance_stats(teacher_id):

    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Total days
        cursor.execute("""
            SELECT COUNT(*)
            FROM attendance
            WHERE teacher_id = ?
        """, (str(teacher_id),))

        total_days = cursor.fetchone()[0]

        # Present days
        cursor.execute("""
            SELECT COUNT(*)
            FROM attendance
            WHERE teacher_id = ?
            AND status = 'Present'
        """, (str(teacher_id),))

        present_days = cursor.fetchone()[0]

        absent_days = total_days - present_days

        attendance_percent = (
            (present_days / total_days) * 100
            if total_days > 0 else 0
        )

        # Last attendance
        cursor.execute("""
            SELECT date, status
            FROM attendance
            WHERE teacher_id = ?
            ORDER BY date DESC
            LIMIT 1
        """, (str(teacher_id),))

        last_record = cursor.fetchone()

        last_date = last_record[0] if last_record else None
        last_status = last_record[1] if last_record else None

        return {
            "total_days": total_days,
            "present_days": present_days,
            "absent_days": absent_days,
            "attendance_percent": round(attendance_percent, 2),
            "last_date": last_date,
            "last_status": last_status
        }


# ===========================
# ADMIN FUNCTIONS
# ===========================

def get_all_attendance(date=None):

    with get_db_connection() as conn:

        if date:
            return pd.read_sql_query("""
                SELECT *
                FROM attendance
                WHERE date = ?
                ORDER BY name
            """, conn, params=(date,))

        return pd.read_sql_query("""
            SELECT *
            FROM attendance
            ORDER BY date DESC, name
        """, conn)


def get_todays_attendance_summary():

    today = str(datetime.now().date())

    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Total teachers
        cursor.execute("SELECT COUNT(*) FROM teachers")
        total_teachers = cursor.fetchone()[0]

        # Marked today
        cursor.execute("""
            SELECT COUNT(*)
            FROM attendance
            WHERE date = ?
        """, (today,))

        marked = cursor.fetchone()[0]

        # Present today
        cursor.execute("""
            SELECT COUNT(*)
            FROM attendance
            WHERE date = ? AND status = 'Present'
        """, (today,))

        present = cursor.fetchone()[0]

        # Absent today
        cursor.execute("""
            SELECT COUNT(*)
            FROM attendance
            WHERE date = ? AND status = 'Absent'
        """, (today,))

        absent = cursor.fetchone()[0]

        return {
            "total_teachers": total_teachers,
            "marked": marked,
            "not_marked": total_teachers - marked,
            "present": present,
            "absent": absent,
            "attendance_rate": round((present / marked) * 100, 2) if marked > 0 else 0
        }


def get_department_stats():

    with get_db_connection() as conn:

        return pd.read_sql_query("""
            SELECT
                department,
                COUNT(DISTINCT teacher_id) AS total_teachers,
                COUNT(*) AS total_records,
                SUM(CASE WHEN status = 'Present' THEN 1 ELSE 0 END) AS present_count,
                ROUND(
                    AVG(CASE WHEN status = 'Present' THEN 100.0 ELSE 0 END),
                    2
                ) AS avg_attendance
            FROM attendance
            GROUP BY department
            ORDER BY avg_attendance DESC
        """, conn)