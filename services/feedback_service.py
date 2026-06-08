"""
services/feedback_service.py
All feedback-related database operations for EDUSYNC
"""

import pandas as pd
from database.connection import get_db_connection


# ===========================
# ADD FEEDBACK
# ===========================

def add_feedback(teacher_id, feedback_text, sentiment_score, student_name="Anonymous"):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO feedback (teacher_id, feedback_text, sentiment_score, student_name)
            VALUES (?, ?, ?, ?)
        """, (teacher_id, feedback_text, sentiment_score, student_name))
        conn.commit()

    # Immediately update teacher's average sentiment
    update_teacher_sentiment(teacher_id)


# ===========================
# UPDATE TEACHER SENTIMENT
# ===========================

def update_teacher_sentiment(teacher_id):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT AVG(sentiment_score)
            FROM feedback
            WHERE teacher_id = ?
        """, (teacher_id,))
        avg = cursor.fetchone()[0]
        avg = round(avg, 4) if avg is not None else 0.0

        cursor.execute("""
            UPDATE teachers
            SET sentiment_score = ?
            WHERE teacher_id = ?
        """, (avg, teacher_id))
        conn.commit()


# ===========================
# GET FEEDBACK FOR A TEACHER
# ===========================

def get_feedback_by_teacher(teacher_id):
    with get_db_connection() as conn:
        return pd.read_sql_query("""
            SELECT id, feedback_text, sentiment_score, student_name, created_at
            FROM feedback
            WHERE teacher_id = ?
            ORDER BY created_at DESC
        """, conn, params=(str(teacher_id),))


# ===========================
# GET ALL FEEDBACK (ADMIN)
# ===========================

def get_all_feedback():
    with get_db_connection() as conn:
        return pd.read_sql_query("""
            SELECT f.id, t.name AS teacher_name, t.department,
                   f.feedback_text, f.sentiment_score, f.student_name, f.created_at
            FROM feedback f
            JOIN teachers t ON f.teacher_id = t.teacher_id
            ORDER BY f.created_at DESC
        """, conn)


# ===========================
# GET SENTIMENT SUMMARY PER TEACHER
# ===========================

def get_sentiment_summary():
    with get_db_connection() as conn:
        return pd.read_sql_query("""
            SELECT
                t.teacher_id,
                t.name,
                t.department,
                COUNT(f.id)         AS total_feedback,
                ROUND(AVG(f.sentiment_score), 3) AS avg_sentiment,
                SUM(CASE WHEN f.sentiment_score >  0.2 THEN 1 ELSE 0 END) AS positive_count,
                SUM(CASE WHEN f.sentiment_score < -0.2 THEN 1 ELSE 0 END) AS negative_count,
                SUM(CASE WHEN f.sentiment_score BETWEEN -0.2 AND 0.2 THEN 1 ELSE 0 END) AS neutral_count
            FROM teachers t
            LEFT JOIN feedback f ON t.teacher_id = f.teacher_id
            GROUP BY t.teacher_id
            ORDER BY avg_sentiment DESC
        """, conn)


# ===========================
# DELETE A FEEDBACK ENTRY (ADMIN)
# ===========================

def delete_feedback(feedback_id):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        # Find teacher first so we can refresh sentiment after delete
        cursor.execute("SELECT teacher_id FROM feedback WHERE id = ?", (feedback_id,))
        row = cursor.fetchone()
        if not row:
            return False, "Feedback not found"
        teacher_id = row[0]

        cursor.execute("DELETE FROM feedback WHERE id = ?", (feedback_id,))
        conn.commit()

    update_teacher_sentiment(teacher_id)
    return True, "Feedback deleted"


# ===========================
# SEED FROM CSV (one-time import)
# ===========================

def seed_feedback_from_csv(csv_path="data/feedback.csv"):
    """Import existing feedback.csv into the DB (run once)."""
    import os
    from textblob import TextBlob

    if not os.path.exists(csv_path):
        return 0

    df = pd.read_csv(csv_path)
    count = 0

    with get_db_connection() as conn:
        cursor = conn.cursor()
        for _, row in df.iterrows():
            try:
                score = TextBlob(str(row['feedback_text'])).sentiment.polarity
                cursor.execute("""
                    INSERT INTO feedback (teacher_id, feedback_text, sentiment_score, student_name)
                    VALUES (?, ?, ?, 'Imported')
                """, (int(row['teacher_id']), row['feedback_text'], score))
                count += 1
            except Exception:
                pass
        conn.commit()

    # Refresh all teacher sentiments
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT teacher_id FROM feedback")
        ids = [r[0] for r in cursor.fetchall()]

    for tid in ids:
        update_teacher_sentiment(tid)

    return count