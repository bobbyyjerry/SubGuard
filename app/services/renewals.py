"""Keep each subscription's next renewal date in the future.

A renewal date that has passed means the charge happened and the next one
is a billing cycle later. Dates are always counted from the *anchor*: the
date the user entered. Counting from the anchor (not from the previous
renewal) stops month-end dates drifting: 31 Jan -> 28 Feb -> 31 Mar,
never 31 Jan -> 28 Feb -> 28 Mar.
"""
from datetime import timedelta, timezone

from dateutil.relativedelta import relativedelta

from ..extensions import db
from ..models import Subscription, UserPreferences
from .timezones import local_date, utc_now

MONTHS_PER_CYCLE = {"monthly": 1, "quarterly": 3, "yearly": 12}

# Free trials that end without a charge have nothing to renew.
RENEWING_TYPES = ("paid", "trial_converts")


def next_renewal_on_or_after(anchor, billing_cycle, today):
    """Return the first billing date on or after `today`, counted from `anchor`."""
    if anchor >= today:
        return anchor
    if billing_cycle == "weekly":
        weeks = -(-(today - anchor).days // 7)  # round up
        return anchor + timedelta(weeks=weeks)

    step = MONTHS_PER_CYCLE[billing_cycle]
    months_apart = (today.year - anchor.year) * 12 + today.month - anchor.month
    cycles = months_apart // step
    # relativedelta clamps to the month's last day: 31 Jan + 1 month = 28 Feb.
    candidate = anchor + relativedelta(months=cycles * step)
    if candidate < today:
        candidate = anchor + relativedelta(months=(cycles + 1) * step)
    return candidate


def _advance(subscription, today):
    if subscription.subscription_type == "trial_converts":
        # The trial ended and the first charge happened on that date.
        subscription.subscription_type = "paid"
        anchor = subscription.next_renewal_date
    else:
        anchor = subscription.billing_anchor_date or subscription.next_renewal_date
    subscription.billing_anchor_date = anchor
    subscription.next_renewal_date = next_renewal_on_or_after(anchor, subscription.billing_cycle, today)


def _overdue(before):
    return (
        Subscription.status == "active",
        Subscription.subscription_type.in_(RENEWING_TYPES),
        Subscription.next_renewal_date < before,
    )


def advance_renewals_for_user(user_id, today):
    """Move one account's passed renewal dates forward. Paused ones are left alone."""
    overdue = db.session.scalars(
        db.select(Subscription).where(Subscription.user_id == user_id, *_overdue(today))
    ).all()
    for subscription in overdue:
        _advance(subscription, today)
    if overdue:
        db.session.commit()
    return len(overdue)


def advance_all_renewals(now=None):
    """Move every account's passed renewal dates forward, using each account's local date."""
    now = utc_now() if now is None else now
    # An account's local date can be one day ahead of UTC.
    latest_local_date = now.astimezone(timezone.utc).date() + timedelta(days=1)
    candidates = db.session.execute(
        db.select(Subscription, UserPreferences.time_zone)
        .outerjoin(UserPreferences, UserPreferences.user_id == Subscription.user_id)
        .where(*_overdue(latest_local_date))
    ).all()
    advanced = 0
    for subscription, time_zone in candidates:
        today = local_date(time_zone, now=now)
        if subscription.next_renewal_date < today:
            _advance(subscription, today)
            advanced += 1
    if advanced:
        db.session.commit()
    return advanced
