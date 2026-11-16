"""Small formatting helpers available inside every Jinja template.

Filters are used with a pipe:   {{ sub.price | money(sub.currency) }}
"""
from decimal import Decimal

from .constants import (
    BILLING_CYCLES,
    CATEGORIES,
    CURRENCIES,
    STATUSES,
    ZERO_DECIMAL_CURRENCIES,
)


def money(amount, currency="USD"):
    """12.5, "EUR" -> "€12.50"   1234, "USD" -> "$1,234.00" """
    symbol = CURRENCIES.get(currency, f"{currency} ")
    places = 0 if currency in ZERO_DECIMAL_CURRENCIES else 2
    return f"{symbol}{Decimal(amount):,.{places}f}"


def money_totals(totals):
    """{"USD": 20, "EUR": 5} -> "$20.00 + €5.00"  (no exchange-rate conversion)."""
    if not totals:
        return money(0)
    return " + ".join(money(amount, cur) for cur, amount in totals.items())


def nice_date(value):
    """date(2026, 11, 19) -> "19 Nov 2026" (works on Windows, unlike %-d)."""
    return f"{value.day} {value:%b %Y}" if value else ""


def relative_days(days):
    """3 -> "In 3 days", 1 -> "Tomorrow", 0 -> "Today", -2 -> "2 days ago"."""
    if days == 0:
        return "Today"
    if days == 1:
        return "Tomorrow"
    if days == -1:
        return "Yesterday"
    return f"In {days} days" if days > 0 else f"{-days} days ago"


def urgency(days):
    """Bootstrap colour for how soon something happens: red ≤ 2 days, amber ≤ 7."""
    if days <= 2:
        return "danger"
    if days <= 7:
        return "warning"
    return "secondary"


def cycle_suffix(cycle):
    return BILLING_CYCLES.get(cycle, ("", ""))[1]


def register_template_helpers(app):
    for func in (money, money_totals, nice_date, relative_days, urgency, cycle_suffix):
        app.add_template_filter(func)

    # Globals are visible everywhere, including inside imported macros.
    app.jinja_env.globals.update(
        CATEGORIES=CATEGORIES,
        BILLING_CYCLES=BILLING_CYCLES,
        STATUSES=STATUSES,
    )
