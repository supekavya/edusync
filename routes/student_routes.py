from flask import Blueprint, render_template, request, session, redirect, url_for, flash
from textblob import TextBlob

student_bp = Blueprint("student", __name__)

@student_bp.route("/login", methods=["GET", "POST"])
def login():
    if "student_name" in session:
        return redirect(url_for("student.feedback"))

    if request.method == "POST":
        name    = request.form.get("name", "").strip()
        roll_no = request.form.get("roll_no", "").strip()
        if not name or not roll_no:
            flash("Please enter both your name and roll number.", "error")
        else:
            session["student_name"]   = name
            session["student_roll"]   = roll_no
            return redirect(url_for("student.feedback"))

    return render_template("student/login.html")


@student_bp.route("/feedback", methods=["GET", "POST"])
def feedback():
    if "student_name" not in session:
        return redirect(url_for("student.login"))

    from services.teacher_service  import get_all_teachers
    from services.feedback_service import get_all_feedback
    from schema import add_feedback

    teachers = get_all_teachers().to_dict('records')

    if request.method == "POST":
        teacher_id   = request.form.get("teacher_id")
        feedback_txt = request.form.get("feedback_text", "").strip()

        if not teacher_id or not feedback_txt:
            flash("Please select a teacher and write your feedback.", "error")
        elif len(feedback_txt) < 10:
            flash("Please write at least 10 characters of feedback.", "error")
        else:
            # Run sentiment analysis
            blob  = TextBlob(feedback_txt)
            score = round(blob.sentiment.polarity, 3)

            # Save with student name
            from database.connection import get_db_connection
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO feedback
                        (teacher_id, feedback_text, sentiment_score, student_name)
                    VALUES (?, ?, ?, ?)
                """, (teacher_id, feedback_txt, score, session["student_name"]))
                conn.commit()

            # Update teacher's average sentiment score
            from schema import update_teacher_sentiment
            update_teacher_sentiment(teacher_id)

            flash("✅ Feedback submitted successfully! Thank you.", "success")
            return redirect(url_for("student.feedback"))

    return render_template("student/feedback.html",
        teachers=teachers,
        student_name=session["student_name"],
        student_roll=session["student_roll"],
    )


@student_bp.route("/logout")
def logout():
    session.pop("student_name", None)
    session.pop("student_roll", None)
    return redirect(url_for("student.login"))