"""Analytics uses the signed-in account's active paid subscriptions."""
import json
import re
from datetime import date
from decimal import Decimal

from app.extensions import db
from app.models import Subscription, User


def _register(client, email):
    password = "a sample passphrase"
    response = client.post("/register", data={"email": email, "password": password, "confirm_password": password})
    assert response.status_code == 302


def _subscription(user_id, category, price, **overrides):
    values = {"billing_cycle": "monthly", "currency": "USD", **overrides}
    return Subscription(
        user_id=user_id,
        name=category,
        category=category,
        price=Decimal(price),
        next_renewal_date=date(2026, 12, 1),
        **values,
    )


def _chart_data(html):
    match = re.search(r'<script type="application/json" id="spending-chart-data">(.*?)</script>', html, re.DOTALL)
    assert match is not None
    return json.loads(match[1])


def test_analytics_requires_login(client):
    response = client.get("/analytics/")
    assert response.status_code == 302
    assert response.location.startswith("/login?")


def test_analytics_groups_real_spending_by_category_and_currency(app, client):
    _register(client, "owner@example.com")
    other_client = app.test_client()
    _register(other_client, "other@example.com")
    with app.app_context():
        owner = db.session.scalar(db.select(User.id).filter_by(email="owner@example.com"))
        other = db.session.scalar(db.select(User.id).filter_by(email="other@example.com"))
        db.session.add_all([
            _subscription(owner, "streaming", "8.99"),
            _subscription(owner, "streaming", "12.00", billing_cycle="yearly"),
            _subscription(owner, "music", "1.23", billing_cycle="weekly"),
            _subscription(owner, "cloud", "9", currency="EUR", billing_cycle="quarterly"),
            _subscription(owner, "cloud", "0", currency="JPY"),
            _subscription(owner, "software", "500", status="paused"),
            _subscription(owner, "software", "600", status="cancelled"),
            _subscription(owner, "fitness", "100", subscription_type="trial_converts"),
            _subscription(other, "gaming", "975"),
        ])
        db.session.commit()

    response = client.get("/analytics/")
    assert response.status_code == 200
    assert response.cache_control.private and response.cache_control.no_store
    html = response.get_data(as_text=True)
    assert 'aria-current="page"' in html
    assert 'id="monthly-category-chart"' in html and 'id="annual-category-chart"' in html
    assert "$15.32" in html and "$183.84" in html
    assert 'href="/analytics/?currency=EUR"' in html

    usd = _chart_data(html)
    assert usd["currency"] == "USD"
    assert [row["label"] for row in usd["categories"]] == ["Streaming", "Music"]
    assert [Decimal(row["monthly"]) for row in usd["categories"]] == [Decimal("9.99"), Decimal("5.33")]
    assert [Decimal(row["annual"]) for row in usd["categories"]] == [Decimal("119.88"), Decimal("63.96")]

    euro_html = client.get("/analytics/?currency=EUR").get_data(as_text=True)
    euro = _chart_data(euro_html)
    assert euro["currency"] == "EUR"
    assert [row["label"] for row in euro["categories"]] == ["Cloud storage"]
    assert "€3.00" in euro_html and "€36.00" in euro_html
    assert _chart_data(client.get("/analytics/?currency=JPY").get_data(as_text=True)) == usd

    other = _chart_data(other_client.get("/analytics/").get_data(as_text=True))
    assert [row["label"] for row in other["categories"]] == ["Gaming"]


def test_analytics_with_no_spending_shows_an_empty_state(client):
    _register(client, "owner@example.com")
    response = client.get("/analytics/")
    assert response.status_code == 200
    assert b"No spending to show yet" in response.data
    assert b'href="/subscriptions/new"' in response.data
    assert b"spending-chart-data" not in response.data
    assert b"chart.umd.min.js" not in response.data
