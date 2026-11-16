"""Personal dashboard for signed-in users and a public sample dashboard."""
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

from flask import Blueprint, render_template
from flask_login import current_user

from ..models import Subscription
from ..services.billing import spending_totals

bp = Blueprint("dashboard", __name__, url_prefix="/dashboard")


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


@bp.get("/")
def index():
    today = date.today()
    is_preview = not current_user.is_authenticated
    if is_preview:
        subscriptions = _sample_subscriptions(today)
    else:
        subscriptions = Subscription.list_for_user(current_user.id)

    active = [s for s in subscriptions if s.status == "active"]
    paid = [s for s in active if not s.is_trial]
    monthly, annual = spending_totals(paid)
    trials = sorted(
        (s for s in active if s.is_trial and s.trial_end_date >= today),
        key=lambda s: s.trial_end_date,
    )
    upcoming_payments = paid + [s for s in trials if s.converts_to_paid]
    upcoming_cutoff = today + timedelta(days=30)
    upcoming = sorted(
        (s for s in upcoming_payments if today <= s.next_renewal_date <= upcoming_cutoff),
        key=lambda s: s.next_renewal_date,
    )
    trial_cutoff = today + timedelta(days=7)
    trials_ending_soon = sum(s.trial_end_date <= trial_cutoff for s in trials)

    page = render_template(
        "dashboard/index.html",
        subscriptions=subscriptions,
        monthly=monthly,
        annual=annual,
        active_count=len(paid),
        trials=trials,
        trials_ending_soon=trials_ending_soon,
        upcoming=upcoming,
        is_preview=is_preview,
        today=today,
    )
    if is_preview:
        return page
    return page, {"Cache-Control": "private, no-store"}
