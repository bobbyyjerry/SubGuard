"""Manage preferences for the signed-in account."""
from flask import Blueprint, flash, redirect, render_template, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError

from ..extensions import db
from ..forms import PreferencesForm
from ..models import UserPreferences
from ..services.timezones import DEFAULT_TIME_ZONE, time_zone_names

bp = Blueprint("settings", __name__, url_prefix="/settings")


def _save_preferences(preferences):
    try:
        db.session.merge(preferences)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        # Another request can create the preference row during the first save.
        if db.session.get(UserPreferences, preferences.user_id) is None:
            raise
        db.session.merge(preferences)
        db.session.commit()


@bp.route("/", methods=["GET", "POST"])
@login_required
def index():
    preferences = current_user.preferences
    reminder_days = preferences.reminder_days if preferences else None
    form = PreferencesForm(
        time_zone=preferences.time_zone if preferences else DEFAULT_TIME_ZONE,
        reminder_days="default" if reminder_days is None else str(reminder_days),
    )
    if form.validate_on_submit():
        selected_days = form.reminder_days.data
        _save_preferences(UserPreferences(
            user_id=current_user.id,
            time_zone=form.time_zone.data,
            reminder_days=None if selected_days == "default" else int(selected_days),
        ))
        flash("Settings saved.", "success")
        return redirect(url_for("settings.index"))

    page = render_template("settings/index.html", form=form, time_zones=time_zone_names())
    return page, {"Cache-Control": "private, no-store"}
