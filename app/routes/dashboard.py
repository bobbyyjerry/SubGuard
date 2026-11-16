"""Dashboard.

DAY 2 VERSION: shows SAMPLE data so we can design the layout.
On Day 5 the sample list is replaced by the logged-in user's real
subscriptions and the calculations move to app/services/billing.py.
The objects below use the same field names as the future database model,
so the template will not need to change.
"""
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

from flask import Blueprint, render_template

bp = Blueprint("dashboard", __name__, url_prefix="/dashboard")

# How many "months" one billing period is worth (for monthly estimates).
MONTHLY_FACTOR = {
    "weekly": Decimal(52) / Decimal(12),
    "monthly": Decimal(1),
    "quarterly": Decimal(1) / Decimal(3),
    "yearly": Decimal(1) / Decimal(12),
}


def _sample_subscriptions(today):
    """Fake subscriptions, dated relative to today so the highlights always show."""

    def sub(**fields):
        defaults = dict(
            currency="USD",
            billing_cycle="monthly",
            status="active",
            is_trial=False,
            trial_end_date=None,
            converts_to_paid=False,
            cancellation_url=None,
        )
        return SimpleNamespace(**{**defaults, **fields})

    def in_days(n):
        return today + timedelta(days=n)

    return [
        sub(id=1, name="Netflix", category="streaming", price=Decimal("15.49"), next_renewal_date=in_days(2)),
        sub(id=2, name="Spotify", category="music", price=Decimal("11.99"), next_renewal_date=in_days(6)),
        sub(id=3, name="iCloud+", category="cloud", price=Decimal("2.99"), next_renewal_date=in_days(12)),
        sub(id=4, name="Xbox Game Pass", category="gaming", price=Decimal("16.99"), next_renewal_date=in_days(19)),
        sub(id=5, name="City Gym", category="fitness", price=Decimal("30.00"), currency="EUR", next_renewal_date=in_days(25)),
        sub(id=6, name="Adobe Creative Cloud", category="software", price=Decimal("239.88"),
            billing_cycle="yearly", next_renewal_date=in_days(41)),
        sub(id=7, name="Duolingo Super", category="education", price=Decimal("12.99"), is_trial=True,
            trial_end_date=in_days(3), next_renewal_date=in_days(3), converts_to_paid=True),
        sub(id=8, name="The Economist", category="news", price=Decimal("22.00"), is_trial=True,
            trial_end_date=in_days(9), next_renewal_date=in_days(9), converts_to_paid=False),
        sub(id=9, name="Disney+", category="streaming", price=Decimal("9.99"), status="paused", next_renewal_date=in_days(15)),
        sub(id=10, name="Hulu", category="streaming", price=Decimal("7.99"), status="cancelled", next_renewal_date=in_days(-20)),
    ]


def _monthly_totals(subscriptions):
    """Estimated monthly cost per currency, e.g. {"USD": Decimal("67.45"), "EUR": Decimal("30.00")}.
    Only active, paid (non-trial) subscriptions count."""
    totals = {}
    for s in subscriptions:
        if s.status == "active" and not s.is_trial:
            amount = s.price * MONTHLY_FACTOR[s.billing_cycle]
            totals[s.currency] = totals.get(s.currency, Decimal(0)) + amount
    return {cur: amount.quantize(Decimal("0.01")) for cur, amount in totals.items()}


@bp.route("/")
def index():
    today = date.today()
    subscriptions = _sample_subscriptions(today)

    monthly = _monthly_totals(subscriptions)
    annual = {cur: (amount * 12).quantize(Decimal("0.01")) for cur, amount in monthly.items()}

    active = [s for s in subscriptions if s.status == "active"]
    trials = sorted((s for s in active if s.is_trial), key=lambda s: s.trial_end_date)
    upcoming = sorted(
        (s for s in active if 0 <= (s.next_renewal_date - today).days <= 30),
        key=lambda s: s.next_renewal_date,
    )
    trials_ending_soon = [s for s in trials if (s.trial_end_date - today).days <= 7]

    return render_template(
        "dashboard/index.html",
        subscriptions=subscriptions,
        monthly=monthly,
        annual=annual,
        active_count=len([s for s in active if not s.is_trial]),
        trials=trials,
        trials_ending_soon=trials_ending_soon,
        upcoming=upcoming,
        is_preview=True,
    )
