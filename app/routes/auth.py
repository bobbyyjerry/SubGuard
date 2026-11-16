"""Account registration and session routes."""
from flask import Blueprint, flash, redirect, render_template, session, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy.exc import IntegrityError

from ..extensions import db
from ..forms import LoginForm, RegistrationForm
from ..models import User

bp = Blueprint("auth", __name__)


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
        user = _find_user(form.email.data)
        if user is not None and user.check_password(form.password.data):
            session.clear()
            login_user(user)
            return redirect(url_for("dashboard.index"))
        flash("The email address or password is incorrect.", "error")

    return render_template("auth/form.html", form=form, is_registration=False)


@bp.post("/logout")
@login_required
def logout():
    logout_user()
    flash("You’ve logged out.", "success")
    return redirect(url_for("main.index"))
