"""Spending estimates for recurring subscriptions."""
from decimal import Decimal


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


def spending_totals(paid_subscriptions):
    """Return monthly and annual totals by currency for display."""
    by_currency = annual_spending_by_category(paid_subscriptions)
    annual = {currency: sum(categories.values()) for currency, categories in by_currency.items()}

    monthly = {currency: total / 12 for currency, total in annual.items()}
    return monthly, annual
