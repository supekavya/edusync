from flask import Blueprint, render_template, request, session, redirect, url_for, flash
from services.auth_service import verify_user, change_password

auth_bp = Blueprint("auth", __name__)

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("admin.overview") if session.get("role") == "admin" else url_for("teacher.home"))

    if request.method == "POST":
        uid = request.form.get("user_id", "").strip()
        pwd = request.form.get("password", "").strip()
        valid, role, must_change = verify_user(uid, pwd)

        if valid:
            session["user_id"] = uid
            session["role"]    = role
            if must_change:
                session["must_change"] = True
                return redirect(url_for("auth.change_pwd"))
            if role == "admin":
                return redirect(url_for("admin.overview"))
            else:
                session["teacher_id"] = uid
                return redirect(url_for("teacher.home"))
        else:
            flash("Invalid credentials. Please try again.", "error")

    return render_template("login.html")


@auth_bp.route("/change-password", methods=["GET", "POST"])
def change_pwd():
    if "user_id" not in session:
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        new_pwd  = request.form.get("new_password", "")
        conf_pwd = request.form.get("confirm_password", "")
        if new_pwd != conf_pwd:
            flash("Passwords do not match.", "error")
        elif len(new_pwd) < 6:
            flash("Password must be at least 6 characters.", "error")
        else:
            ok, msg = change_password(session["user_id"], new_pwd)
            if ok:
                session.pop("must_change", None)
                flash("Password updated successfully!", "success")
                role = session.get("role")
                return redirect(url_for("admin.overview") if role == "admin" else url_for("teacher.home"))
            else:
                flash(msg, "error")

    return render_template("change_password.html")


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))