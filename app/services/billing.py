"""Spending and savings estimates for recurring subscriptions."""
from decimal import Decimal

from .renewals import charges_due


BILLING_PERIODS_PER_YEAR = {
    "weekly": 52,
    "monthly": 12,
    "quarterly": 4,
    "yearly": 1,
}


def active_paid_subscriptions(subscriptions):
    return [subscription for subscription in subscriptions if subscription.status == "active" and not subscription.is_trial]


def annual_spending_by_category(paid_subscriptions):
    """Return annual spending grouped by currency and category."""
    totals = {}
    for subscription in paid_subscriptions:
        categories = totals.setdefault(subscription.currency, {})
        category = subscription.category
        cost = subscription.price * BILLING_PERIODS_PER_YEAR[subscription.billing_cycle]
        categories[category] = categories.get(category, Decimal(0)) + cost
    return totals


def cancellation_savings(subscriptions, today):
    """Estimate what cancelled subscriptions have saved, grouped by currency.

    A cancelled subscription keeps the date of the first charge it avoided
    (its next renewal date when it was cancelled). "Saved so far" counts the
    charges that would have happened from that date up to today.
    Free trials that end without a charge never cost anything, so they are skipped.
    """
    savings = {}
    for subscription in subscriptions:
        if subscription.status != "cancelled" or subscription.subscription_type == "trial_ends" or subscription.price <= 0:
            continue
        charges = charges_due(subscription.next_renewal_date, subscription.billing_cycle, today)
        currency = savings.setdefault(subscription.currency, {"saved": Decimal(0), "annual": Decimal(0), "items": []})
        saved = subscription.price * charges
        currency["saved"] += saved
        currency["annual"] += subscription.price * BILLING_PERIODS_PER_YEAR[subscription.billing_cycle]
        currency["items"].append({"subscription": subscription, "charges": charges, "saved": saved})
    return savings


def spending_totals(paid_subscriptions):
    """Return monthly and annual totals by currency for display."""
    by_currency = annual_spending_by_category(paid_subscriptions)
    annual = {currency: sum(categories.values()) for currency, categories in by_currency.items()}

    monthly = {currency: total / 12 for currency, total in annual.items()}
    return monthly, annual
