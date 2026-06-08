from database.connection import get_db_connection
import hashlib


def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


def create_user(teacher_id, password="Teacher@123", role="teacher"):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        try:
            hashed = hash_password(password)
            must_change = 0 if role == "admin" else 1

            cursor.execute("""
                INSERT INTO users (teacher_id, password, role, must_change_password)
                VALUES (?, ?, ?, ?)
            """, (teacher_id, hashed, role, must_change))

            conn.commit()
            return True, "User created"
        except Exception:
            return False, "User already exists"

from database.connection import get_db_connection
#from services.auth_service import hash_password  # if already exists ignore

# ===========================
# CHANGE PASSWORD
# ===========================

def change_password(teacher_id, new_password):
    try:
        hashed = hash_password(new_password)

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE users
                SET password = ?, must_change_password = 0
                WHERE teacher_id = ?
            """, (hashed, teacher_id))

            conn.commit()

        return True, "Password updated successfully"

    except Exception as e:
        return False, str(e)

def verify_user(teacher_id, password):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        hashed = hash_password(password)

        cursor.execute("""
            SELECT role, must_change_password
            FROM users
            WHERE teacher_id = ? AND password = ?
        """, (teacher_id, hashed))

        result = cursor.fetchone()

        if result:
            return True, result[0], result[1]

        return False, None, None
    
    


def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


def reset_teacher_password(teacher_id):
    """
    Reset teacher password back to default and force change on next login
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        try:
            default_password = "Teacher@123"
            hashed = hash_password(default_password)

            cursor.execute("""
                UPDATE users
                SET password = ?, must_change_password = 1
                WHERE teacher_id = ?
            """, (hashed, str(teacher_id)))

            conn.commit()

            if cursor.rowcount > 0:
                return True, "Password reset to Teacher@123 successfully"
            else:
                return False, "User not found"

        except Exception as e:
            conn.rollback()
            return False, str(e)