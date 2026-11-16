"""Manage preferences, email address and password for the signed-in account."""
from flask import Blueprint, flash, redirect, render_template, url_for
from flask_login import current_user, login_required, login_user
from sqlalchemy.exc import IntegrityError

from ..extensions import db
from ..forms import EmailChangeForm, PasswordChangeForm, PreferencesForm
from ..models import UserPreferences
from ..services.timezones import DEFAULT_TIME_ZONE, time_zone_names

bp = Blueprint("settings", __name__, url_prefix="/settings")

DEFAULT_CURRENCY = "USD"
WRONG_PASSWORD = "The current password is incorrect."


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


def _preferences_form(**options):
    preferences = current_user.preferences
    reminder_days = preferences.reminder_days if preferences else None
    return PreferencesForm(
        time_zone=preferences.time_zone if preferences else DEFAULT_TIME_ZONE,
        reminder_days="default" if reminder_days is None else str(reminder_days),
        currency=current_user.preferred_currency or DEFAULT_CURRENCY,
        **options,
    )


def _page(preferences_form=None, email_form=None, password_form=None):
    """Render Settings. The form that was just submitted is passed in so its errors show."""
    page = render_template(
        "settings/index.html",
        # formdata=None: a form that was not submitted must not read another form's fields.
        form=preferences_form or _preferences_form(formdata=None),
        email_form=email_form or EmailChangeForm(formdata=None, email=current_user.email),
        password_form=password_form or PasswordChangeForm(formdata=None),
        time_zones=time_zone_names(),
    )
    return page, {"Cache-Control": "private, no-store"}


def _done(message):
    flash(message, "success")
    return redirect(url_for("settings.index"))


@bp.route("/", methods=["GET", "POST"])
@login_required
def index():
    form = _preferences_form()
    if form.validate_on_submit():
        selected_days = form.reminder_days.data
        _save_preferences(UserPreferences(
            user_id=current_user.id,
            time_zone=form.time_zone.data,
            reminder_days=None if selected_days == "default" else int(selected_days),
            currency=form.currency.data,
        ))
        return _done("Settings saved.")
    return _page(preferences_form=form)


@bp.post("/email")
@login_required
def change_email():
    form = EmailChangeForm()
    if form.validate_on_submit():
        if not current_user.check_password(form.password.data):
            form.password.errors.append(WRONG_PASSWORD)
        elif form.email.data == current_user.email:
            form.email.errors.append("This is already your email address.")
        else:
            current_user.email = form.email.data
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                form.email.errors.append("An account already uses this email address.")
            else:
                return _done("Email address updated.")
    return _page(email_form=form)


@bp.post("/password")
@login_required
def change_password():
    form = PasswordChangeForm()
    if form.validate_on_submit():
        if not current_user.check_password(form.current_password.data):
            form.current_password.errors.append(WRONG_PASSWORD)
        elif form.new_password.data == form.current_password.data:
            form.new_password.errors.append("Choose a password you are not already using.")
        else:
            user = current_user._get_current_object()
            user.set_password(form.new_password.data)
            db.session.commit()
            # The new password signs out every session; sign this browser back in.
            login_user(user)
            return _done("Password changed. Other devices have been signed out.")
    return _page(password_form=form)
