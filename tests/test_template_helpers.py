"""Unit tests for the formatting helpers (no web requests needed)."""
from datetime import date
from decimal import Decimal

from app.template_helpers import money, money_totals, nice_date, relative_days, urgency


def test_money_formats_symbols_and_decimals():
    assert money(Decimal("12.5"), "EUR") == "€12.50"
    assert money(1234, "USD") == "$1,234.00"
    assert money(1500, "JPY") == "¥1,500"
    assert money(5, "CHF") == "CHF 5.00"  # unknown currency falls back to its code


def test_money_totals_joins_currencies():
    assert money_totals({"USD": Decimal("20"), "EUR": Decimal("5")}) == "$20.00 + €5.00"
    assert money_totals({}) == "$0.00"


def test_nice_date():
    assert nice_date(date(2026, 11, 9)) == "9 Nov 2026"
    assert nice_date(None) == ""


def test_relative_days():
    assert relative_days(0) == "Today"
    assert relative_days(1) == "Tomorrow"
    assert relative_days(5) == "In 5 days"
    assert relative_days(-1) == "Yesterday"
    assert relative_days(-3) == "3 days ago"


def test_urgency_thresholds():
    assert urgency(0) == "danger"
    assert urgency(2) == "danger"
    assert urgency(3) == "warning"
    assert urgency(7) == "warning"
    assert urgency(8) == "secondary"
