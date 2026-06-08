import sys
import os
import pandas as pd
import sqlite3

# =====================================================
# PROJECT PATH SETUP
# =====================================================

# Add project root to Python path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

from database.connection import get_db_connection

# CSV paths (inside data folder)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEACHERS_CSV = os.path.join(BASE_DIR, "teachers.csv")
FEEDBACK_CSV = os.path.join(BASE_DIR, "feedback.csv")

# =====================================================
# SEED TEACHERS
# =====================================================

def seed_teachers():
    df = pd.read_csv(TEACHERS_CSV)

    with get_db_connection() as conn:
        cursor = conn.cursor()

        inserted = 0
        skipped = 0

        for _, row in df.iterrows():
            try:
                cursor.execute("""
                    INSERT INTO teachers (
                        teacher_id,
                        name,
                        department,
                        subject,
                        experience_years,
                        attendance_percentage,
                        student_rating,
                        workload_hours,
                        sentiment_score
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    int(row['teacher_id']),
                    row['name'],
                    row['department'],
                    row['subject'],
                    int(row['experience_years']),
                    float(row['attendance_percentage']),
                    float(row['student_rating']),
                    int(row['workload_hours']),
                    float(row['sentiment_score'])
                ))

                inserted += 1

            except sqlite3.IntegrityError:
                skipped += 1  # duplicate teacher_id

        conn.commit()

    print(f"Teachers Inserted: {inserted}")
    print(f"Teachers Skipped (duplicates): {skipped}")
    print("Teachers seeding complete.\n")


# =====================================================
# SIMPLE SENTIMENT CALCULATOR
# =====================================================

def calculate_sentiment(text):
    if pd.isna(text):
        return 0.0

    text_lower = str(text).lower()

    positive_words = [
        "good", "very", "excellent", "helpful",
        "interactive", "patient", "encourages", "clear"
    ]

    negative_words = [
        "rushed", "slow", "unclear", "not", "needs"
    ]

    score = 0

    for word in positive_words:
        if word in text_lower:
            score += 1

    for word in negative_words:
        if word in text_lower:
            score -= 1

    # Normalize score between -1 and 1 roughly
    return round(score / 5, 2)


# =====================================================
# SEED FEEDBACK
# =====================================================

def seed_feedback():
    df = pd.read_csv(FEEDBACK_CSV)

    # Remove invalid rows
    df = df.dropna(subset=['teacher_id', 'feedback_text'])

    with get_db_connection() as conn:
        cursor = conn.cursor()

        inserted = 0

        for _, row in df.iterrows():

            teacher_id = int(row['teacher_id'])
            feedback_text = str(row['feedback_text'])

            sentiment_score = calculate_sentiment(feedback_text)

            cursor.execute("""
                INSERT INTO feedback (
                    teacher_id,
                    feedback_text,
                    sentiment_score
                )
                VALUES (?, ?, ?)
            """, (
                teacher_id,
                feedback_text,
                sentiment_score
            ))

            inserted += 1

        conn.commit()

    print(f"Feedback Inserted: {inserted}")
    print("Feedback seeding complete.\n")


# =====================================================
# UPDATE TEACHER SENTIMENT AVG
# =====================================================

def update_teacher_sentiment():

    with get_db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT teacher_id, AVG(sentiment_score)
            FROM feedback
            GROUP BY teacher_id
        """)

        results = cursor.fetchall()

        for teacher_id, avg_score in results:
            cursor.execute("""
                UPDATE teachers
                SET sentiment_score = ?
                WHERE teacher_id = ?
            """, (avg_score, teacher_id))

        conn.commit()

    print("Teacher sentiment scores updated.\n")


# =====================================================
# MAIN
# =====================================================

if __name__ == "__main__":
    print("Seeding Database...\n")

    seed_teachers()
    seed_feedback()
    update_teacher_sentiment()

    print("All seeding completed successfully.")