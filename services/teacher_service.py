import pandas as pd
from database.connection import get_db_connection
from services.auth_service import create_user


# ===========================
# BASIC QUERIES
# ===========================

def get_all_teachers():
    with get_db_connection() as conn:
        return pd.read_sql_query(
            "SELECT * FROM teachers ORDER BY name",
            conn
        )


def get_teacher_by_id(teacher_id):
    with get_db_connection() as conn:
        result = pd.read_sql_query(
            "SELECT * FROM teachers WHERE teacher_id = ?",
            conn,
            params=(str(teacher_id),)
        )
        return result.iloc[0] if len(result) > 0 else None


def teacher_exists(teacher_id):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM teachers WHERE teacher_id = ?",
            (str(teacher_id),)
        )
        return cursor.fetchone()[0] > 0


# ===========================
# CREATE
# ===========================

from database.connection import get_db_connection
from services.auth_service import hash_password
import sqlite3

def add_new_teacher(
    teacher_id,
    name,
    department,
    subject,
    experience_years,
    attendance_percentage,
    student_rating,
    workload_hours
):
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            # Insert into teachers table
            cursor.execute("""
                INSERT INTO teachers (
                    teacher_id,
                    name,
                    department,
                    subject,
                    experience_years,
                    attendance_percentage,
                    student_rating,
                    workload_hours
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                teacher_id,
                name,
                department,
                subject,
                experience_years,
                attendance_percentage,
                student_rating,
                workload_hours
            ))

            # Create login credentials
            default_password = hash_password("Teacher@123")

            cursor.execute("""
                INSERT INTO users (
                    teacher_id,
                    password,
                    role,
                    must_change_password
                )
                VALUES (?, ?, 'teacher', 1)
            """, (
                str(teacher_id),
                default_password
            ))

            conn.commit()

        return True, "Teacher added successfully"

    except sqlite3.IntegrityError:
        return False, "Teacher ID already exists"

    except Exception as e:
        return False, str(e)
# ===========================
# UPDATE
# ===========================

def update_teacher(
    teacher_id,
    name=None,
    department=None,
    subject=None,
    experience_years=None,
    student_rating=None,
    workload_hours=None
):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        try:
            updates = []
            params = []

            if name:
                updates.append("name = ?")
                params.append(name)

            if department:
                updates.append("department = ?")
                params.append(department)

            if subject:
                updates.append("subject = ?")
                params.append(subject)

            if experience_years is not None:
                updates.append("experience_years = ?")
                params.append(experience_years)

            if student_rating is not None:
                updates.append("student_rating = ?")
                params.append(student_rating)

            if workload_hours is not None:
                updates.append("workload_hours = ?")
                params.append(workload_hours)

            if not updates:
                return False, "No fields to update"

            params.append(teacher_id)

            query = f"""
                UPDATE teachers
                SET {', '.join(updates)}
                WHERE teacher_id = ?
            """

            cursor.execute(query, params)
            conn.commit()

            if cursor.rowcount > 0:
                return True, "Teacher updated successfully!"
            else:
                return False, "Teacher not found"

        except Exception as e:
            conn.rollback()
            return False, str(e)


# ===========================
# DELETE
# ===========================

def delete_teacher(teacher_id):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                "DELETE FROM attendance WHERE teacher_id = ?",
                (teacher_id,)
            )

            cursor.execute(
                "DELETE FROM users WHERE teacher_id = ?",
                (teacher_id,)
            )

            cursor.execute(
                "DELETE FROM teachers WHERE teacher_id = ?",
                (teacher_id,)
            )

            conn.commit()

            if cursor.rowcount > 0:
                return True, "Teacher deleted successfully"
            else:
                return False, "Teacher not found"

        except Exception as e:
            conn.rollback()
            return False, str(e)


# ===========================
# UTILITIES
# ===========================

def get_next_teacher_id():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT MAX(teacher_id) FROM teachers")
        max_id = cursor.fetchone()[0]
        return (max_id + 1) if max_id else 1