import sqlite3
import os
from datetime import datetime
from database.connection import get_db_connection, DATABASE_NAME
from services.auth_service import hash_password


# ===========================
# DATABASE INITIALIZATION
# ===========================

def init_database():
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # ===========================
        # TEACHERS TABLE (UPDATED)
        # ===========================
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS teachers (
                teacher_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                department TEXT NOT NULL,
                subject TEXT,
                experience_years INTEGER,
                attendance_percentage REAL,
                student_rating REAL,
                workload_hours INTEGER,
                sentiment_score REAL DEFAULT 0
            )
        ''')

        # ===========================
        # ATTENDANCE TABLE
        # ===========================
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS attendance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                department TEXT NOT NULL,
                date TEXT NOT NULL,
                checkin_time TEXT,
                latitude REAL,
                longitude REAL,
                status TEXT NOT NULL,
                distance_km REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (teacher_id) REFERENCES teachers (teacher_id),
                UNIQUE(teacher_id, date)
            )
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_attendance_teacher_date
            ON attendance(teacher_id, date)
        ''')

        # ===========================
        # FEEDBACK TABLE (NEW)
        # ===========================
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_id INTEGER NOT NULL,
                feedback_text TEXT NOT NULL,
                sentiment_score REAL,
                student_name TEXT DEFAULT 'Anonymous',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (teacher_id) REFERENCES teachers (teacher_id)
            )
        ''')

        # ===========================
        # USERS TABLE (LOGIN SYSTEM)
        # ===========================
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_id TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('teacher', 'admin')),
                must_change_password INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Create default admin
        hashed_admin = hash_password("Admin@123")
        cursor.execute("""
            INSERT OR IGNORE INTO users (teacher_id, password, role, must_change_password)
            VALUES ('admin', ?, 'admin', 0)
        """, (hashed_admin,))

        # ===========================
        # LEAVE REQUESTS TABLE
        # ===========================
        cursor.execute('''\
            CREATE TABLE IF NOT EXISTS leave_requests (\
                id INTEGER PRIMARY KEY AUTOINCREMENT,\
                teacher_id TEXT NOT NULL,\
                leave_type TEXT NOT NULL,\
                from_date TEXT NOT NULL,\
                to_date TEXT NOT NULL,\
                days_requested INTEGER NOT NULL,\
                reason TEXT,\
                status TEXT DEFAULT "Pending" CHECK(status IN ("Pending","Approved","Rejected","Cancelled")),\
                admin_note TEXT DEFAULT "",\
                reviewed_at TIMESTAMP,\
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,\
                FOREIGN KEY (teacher_id) REFERENCES teachers (teacher_id)\
            )\
        ''')

        # ===========================
        # LEAVE BALANCE TABLE
        # ===========================
        cursor.execute('''\
            CREATE TABLE IF NOT EXISTS leave_balance (\
                id INTEGER PRIMARY KEY AUTOINCREMENT,\
                teacher_id TEXT NOT NULL,\
                leave_type TEXT NOT NULL,\
                total_days INTEGER NOT NULL,\
                used_days INTEGER DEFAULT 0,\
                UNIQUE(teacher_id, leave_type)\
            )\
        ''')

        # ===========================
        # NOTIFICATIONS TABLE
        # ===========================
        cursor.execute('''\
            CREATE TABLE IF NOT EXISTS notifications (\
                id INTEGER PRIMARY KEY AUTOINCREMENT,\
                recipient_id TEXT NOT NULL,\
                title TEXT NOT NULL,\
                message TEXT NOT NULL,\
                type TEXT DEFAULT "info",\
                is_read INTEGER DEFAULT 0,\
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP\
            )\
        ''')

        cursor.execute('''\
            CREATE INDEX IF NOT EXISTS idx_notifications_recipient\
            ON notifications(recipient_id, is_read)\
        ''')

        # ===========================
        # ANNOUNCEMENTS TABLE
        # ===========================
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS announcements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                body TEXT NOT NULL,
                posted_by TEXT DEFAULT 'admin',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # ===========================
        # SUBJECT PREFERENCES TABLE
        # ===========================
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

        # ===========================
        # SUBJECT ALLOCATIONS TABLE
        # ===========================
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
        print("✅ Database initialized successfully")

# ===========================
# FEEDBACK SYSTEM
# ===========================

def add_feedback(teacher_id, feedback_text, sentiment_score):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO feedback (teacher_id, feedback_text, sentiment_score)
            VALUES (?, ?, ?)
        """, (teacher_id, feedback_text, sentiment_score))
        conn.commit()

    # After inserting feedback → update teacher sentiment
    update_teacher_sentiment(teacher_id)

def update_teacher_sentiment(teacher_id):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT AVG(sentiment_score)
            FROM feedback
            WHERE teacher_id = ?
        """, (teacher_id,))
        avg = cursor.fetchone()[0]

        if avg is None:
            avg = 0

        cursor.execute("""
            UPDATE teachers
            SET sentiment_score = ?
            WHERE teacher_id = ?
        """, (avg, teacher_id))
        conn.commit()



# ===========================
# MAIN
# ===========================

if __name__ == "__main__":
    print("🔄 Initializing database...")
    init_database()
    print("✅ Setup complete!")