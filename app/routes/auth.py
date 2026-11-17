"""Account registration and session routes."""
from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from ..extensions import db
from ..forms import LoginForm, RegistrationForm
from ..models import User

bp = Blueprint("auth", __name__)

# Checked when no account matches, so a wrong email takes as long as a wrong password.
_UNUSED_HASH = generate_password_hash("no account uses this")


def _find_user(email):
    return db.session.scalar(db.select(User).filter_by(email=email))


@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(email=form.email.data)
        user.set_password(form.password.data)
        db.session.add(user)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            if _find_user(form.email.data) is None:
                raise
            form.email.errors.append("An account already uses this email address.")
        else:
            session.clear()
            login_user(user)
            flash("Your account has been created.", "success")
            return redirect(url_for("dashboard.index"))

    return render_template("auth/form.html", form=form, is_registration=True)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    form = LoginForm()
    if form.validate_on_submit():
        throttle = current_app.extensions["login_throttle"]
        attempt = (request.remote_addr, form.email.data)
        if throttle.is_blocked(attempt):
            flash("Too many failed attempts. Wait 15 minutes and try again.", "error")
            return render_template("auth/form.html", form=form, is_registration=False), 429

        user = _find_user(form.email.data)
        password_hash = user.password_hash if user is not None else _UNUSED_HASH
        if check_password_hash(password_hash, form.password.data) and user is not None:
            throttle.reset(attempt)
            session.clear()
            login_user(user)
            return redirect(url_for("dashboard.index"))
        throttle.record_failure(attempt)
        flash("The email address or password is incorrect.", "error")

    return render_template("auth/form.html", form=form, is_registration=False)


@bp.post("/logout")
@login_required
def logout():
    logout_user()
    flash("You’ve logged out.", "success")
    return redirect(url_for("main.index"))
