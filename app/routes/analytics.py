"""Spending analytics for the signed-in user's subscriptions."""
from decimal import Decimal

from flask import Blueprint, render_template, request
from flask_login import current_user, login_required

from ..constants import CATEGORIES
from ..models import Subscription
from ..services.billing import active_paid_subscriptions, annual_spending_by_category

bp = Blueprint("analytics", __name__, url_prefix="/analytics")


@bp.get("/")
@login_required
def index():
    subscriptions = Subscription.list_for_user(current_user.id)
    paid = active_paid_subscriptions(subscriptions)
    totals = annual_spending_by_category(subscription for subscription in paid if subscription.price > 0)
    currencies = sorted(totals)

    currency = request.args.get("currency")
    if currency not in totals:
        currency = "USD" if "USD" in totals else next(iter(currencies), None)

    category_totals = totals.get(currency, {})
    categories = [
        {"key": key, "label": CATEGORIES[key][0], "monthly": annual / 12, "annual": annual}
        for key, annual in sorted(category_totals.items(), key=lambda item: (-item[1], item[0]))
    ]
    annual_total = sum(category_totals.values(), Decimal(0))

    page = render_template(
        "analytics/index.html",
        categories=categories,
        currencies=currencies,
        currency=currency,
        monthly_total=annual_total / 12,
        annual_total=annual_total,
    )
    return page, {"Cache-Control": "private, no-store"}
