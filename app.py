"""
app.py — EDUSYNC Flask Entry Point
Run with: python app.py
"""
import os
from flask import Flask, redirect, url_for, session, render_template
from schema import init_database

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "edusync-dev-secret-change-in-prod")

# ── Register blueprints ───────────────────────────────────────
from routes.auth_routes         import auth_bp
from routes.admin_routes        import admin_bp
from routes.teacher_routes      import teacher_bp
from routes.student_routes      import student_bp
from routes.notification_routes import notif_bp

app.register_blueprint(auth_bp)
app.register_blueprint(admin_bp,   url_prefix="/admin")
app.register_blueprint(teacher_bp, url_prefix="/teacher")
app.register_blueprint(student_bp, url_prefix="/student")
app.register_blueprint(notif_bp)

@app.route("/")
def index():
    if "user_id" in session:
        if session.get("role") == "admin":
            return redirect(url_for("admin.overview"))
        else:
            return redirect(url_for("teacher.home"))
    return render_template("landing.html")

# ── Init DB on startup ────────────────────────────────────────
with app.app_context():
    init_database()

if __name__ == "__main__":
    app.run(debug=False, port=5000)
