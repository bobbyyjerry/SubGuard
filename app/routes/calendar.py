"""Month view of each user's upcoming subscription dates."""
from calendar import Calendar, monthrange
from datetime import date, timedelta

from flask import Blueprint, render_template, request
from flask_login import current_user, login_required

from ..extensions import db
from ..models import Subscription
from ..services.timezones import today_for_user

bp = Blueprint("calendar", __name__, url_prefix="/calendar")


def _requested_month(value, current_month):
    if not value:
        return current_month
    try:
        return max(current_month, date.fromisoformat(f"{value}-01"))
    except ValueError:
        return current_month


@bp.get("/")
@login_required
def index():
    today = today_for_user(current_user)
    current_month = today.replace(day=1)
    month = _requested_month(request.args.get("month"), current_month)
    month_end = month.replace(day=monthrange(month.year, month.month)[1])
    previous_month = (month - timedelta(days=1)).replace(day=1) if month > current_month else None
    next_month = month_end + timedelta(days=1) if month_end < date.max else None
    weeks = [
        [month.replace(day=day) if day else None for day in week]
        for week in Calendar().monthdayscalendar(month.year, month.month)
    ]

    # The saved next date is the trial end date for trial subscriptions.
    statement = Subscription.for_user(current_user.id).where(
        Subscription.status == "active",
        Subscription.next_renewal_date.between(max(today, month), month_end),
    )
    events_by_date = {}
    for subscription in db.session.scalars(statement):
        events_by_date.setdefault(subscription.next_renewal_date, []).append(subscription)

    page = render_template(
        "calendar/index.html",
        today=today,
        month=month,
        previous_month=previous_month,
        next_month=next_month,
        weeks=weeks,
        events_by_date=events_by_date,
    )
    return page, {"Cache-Control": "private, no-store"}
