"""Spending estimates for recurring subscriptions."""
from decimal import Decimal


BILLING_PERIODS_PER_YEAR = {
    "weekly": 52,
    "monthly": 12,
    "quarterly": 4,
    "yearly": 1,
}


def spending_totals(active_paid_subscriptions):
    """Return monthly and annual totals by currency for display."""
    annual = {}
    for subscription in active_paid_subscriptions:
        currency = subscription.currency
        cost = subscription.price * BILLING_PERIODS_PER_YEAR[subscription.billing_cycle]
        annual[currency] = annual.get(currency, Decimal(0)) + cost

    monthly = {currency: total / 12 for currency, total in annual.items()}
    return monthly, annual
