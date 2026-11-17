"""A web address that sends due reminders, for hosts with no scheduler.

Some free hosts cannot run `flask reminders` on a timer. An outside
scheduler (for example a daily GitHub Actions job) can call this address
instead. It only works when REMINDER_TRIGGER_TOKEN is set, and only for a
caller that sends the same token.
"""
import hmac

from flask import Blueprint, abort, current_app, jsonify, request

from ..extensions import csrf
from ..services.mail import MailSettings
from ..services.reminders import send_due_reminders

bp = Blueprint("tasks", __name__, url_prefix="/tasks")

# Shorter tokens are too easy to guess, so they switch the address off.
MIN_TOKEN_LENGTH = 32


@bp.route("/reminders", methods=["POST"])
@csrf.exempt  # called by a scheduler, not a browser form; the token is the protection
def run_reminders():
    expected = (current_app.config.get("REMINDER_TRIGGER_TOKEN") or "").strip()
    if len(expected) < MIN_TOKEN_LENGTH:
        abort(404)  # switched off: behave as if the address does not exist
    supplied = request.headers.get("Authorization", "")
    if not hmac.compare_digest(supplied.encode(), f"Bearer {expected}".encode()):
        abort(403)

    try:
        settings = MailSettings.from_config(current_app.config)
        lead_days = int(current_app.config["REMINDER_DAYS"])
        if not 1 <= lead_days <= 30:
            raise ValueError
    except (ValueError, TypeError):
        return jsonify(error="Email reminders are not set up on the server."), 503

    sent, failed = send_due_reminders(settings, lead_days)
    # A failure status makes the scheduler show the run as failed.
    return jsonify(sent=sent, failed=failed), (502 if failed else 200)
