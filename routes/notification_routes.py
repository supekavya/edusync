from flask import Blueprint, jsonify, session, redirect, url_for
from functools import wraps

notif_bp = Blueprint("notif", __name__)

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({"error": "not logged in"}), 401
        return f(*args, **kwargs)
    return decorated

@notif_bp.route("/notifications/unread")
@login_required
def unread_count():
    from services.notification_service import get_unread_count
    count = get_unread_count(session["user_id"])
    return jsonify({"count": count})

@notif_bp.route("/notifications/list")
@login_required
def list_notifications():
    from services.notification_service import get_notifications, mark_all_read
    notifs = get_notifications(session["user_id"])
    mark_all_read(session["user_id"])
    return jsonify({"notifications": notifs.to_dict('records') if len(notifs) > 0 else []})