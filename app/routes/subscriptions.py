"""Manage subscriptions owned by the signed-in user."""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from ..extensions import db
from ..forms import SubscriptionForm
from ..models import Subscription
from ..services.renewals import advance_renewals_for_user
from ..services.timezones import today_for_user

bp = Blueprint("subscriptions", __name__, url_prefix="/subscriptions")


def _owned_record(subscription_id):
    return (Subscription.id == subscription_id, Subscription.user_id == current_user.id)


def _form_values(form):
    return {
        "name": form.name.data,
        "price": form.price.data,
        "currency": form.currency.data,
        "billing_cycle": form.billing_cycle.data,
        "next_renewal_date": form.next_renewal_date.data,
        "category": form.category.data,
        "subscription_type": form.subscription_type.data,
        "cancellation_url": form.cancellation_url.data or None,
    }


def _save_changes(message):
    db.session.commit()
    flash(message, "success")
    return redirect(url_for("subscriptions.index"))


def _apply_change(statement, subscription_id, message):
    result = db.session.execute(statement.where(*_owned_record(subscription_id)))
    if result.rowcount == 0:
        abort(404)
    return _save_changes(message)


@bp.get("/")
@login_required
def index():
    today = today_for_user(current_user)
    advance_renewals_for_user(current_user.id, today)
    subscriptions = Subscription.list_for_user(current_user.id)
    return render_template("subscriptions/index.html", subscriptions=subscriptions, is_preview=False, today=today)


@bp.route("/new", methods=["GET", "POST"])
@login_required
def add():
    form = SubscriptionForm(currency=current_user.preferred_currency)
    if form.validate_on_submit():
        values = _form_values(form)
        db.session.add(Subscription(
            user_id=current_user.id, billing_anchor_date=values["next_renewal_date"], **values,
        ))
        return _save_changes("Subscription added.")
    return render_template("subscriptions/form.html", form=form, subscription=None)


@bp.route("/<int:subscription_id>/edit", methods=["GET", "POST"])
@login_required
def edit(subscription_id):
    subscription = db.first_or_404(db.select(Subscription).where(*_owned_record(subscription_id)))
    form = SubscriptionForm(obj=subscription)
    if form.validate_on_submit():
        values = _form_values(form)
        if values["next_renewal_date"] != subscription.next_renewal_date:
            # A date the user typed becomes the new starting point for future renewals.
            values["billing_anchor_date"] = values["next_renewal_date"]
        statement = db.update(Subscription).values(**values)
        return _apply_change(statement, subscription_id, "Subscription updated.")
    return render_template("subscriptions/form.html", form=form, subscription=subscription)


@bp.post("/<int:subscription_id>/status")
@login_required
def set_status(subscription_id):
    messages = {
        "paused": "Subscription paused.",
        "active": "Subscription resumed.",
        "cancelled": "Marked as cancelled in SubGuard. Remember to cancel with the provider too.",
    }
    status = request.form.get("status")
    if status not in messages:
        abort(400)
    if status == "cancelled":
        # Bring the date up to date first: it becomes the first charge this cancellation avoids.
        advance_renewals_for_user(current_user.id, today_for_user(current_user))
    return _apply_change(db.update(Subscription).values(status=status), subscription_id, messages[status])


@bp.post("/<int:subscription_id>/delete")
@login_required
def delete(subscription_id):
    return _apply_change(db.delete(Subscription), subscription_id, "Subscription deleted.")
