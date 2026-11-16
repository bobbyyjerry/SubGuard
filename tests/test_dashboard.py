"""Personal dashboard totals, date windows, and account isolation."""
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.extensions import db
from app.models import Subscription, User
from app.services import timezones


NOW = datetime(2026, 11, 16, 12, tzinfo=timezone.utc)


def _register(client, email):
    password = "a sample passphrase"
    response = client.post("/register", data={"email": email, "password": password, "confirm_password": password})
    assert response.status_code == 302


def _subscription(user_id, name, price, days, **overrides):
    values = {
        "currency": "USD",
        "billing_cycle": "monthly",
        "category": "other",
        **overrides,
    }
    return Subscription(
        user_id=user_id,
        name=name,
        price=Decimal(price),
        next_renewal_date=NOW.date() + timedelta(days=days),
        **values,
    )


def _section(html, heading_id):
    return html.split(f'id="{heading_id}"', 1)[1].split("</section>", 1)[0]


def test_dashboard_uses_only_the_signed_in_users_records(app, client, monkeypatch):
    monkeypatch.setattr(timezones, "utc_now", lambda: NOW)
    _register(client, "owner@example.com")
    other_client = app.test_client()
    _register(other_client, "other@example.com")
    with app.app_context():
        owner = db.session.scalar(db.select(User.id).filter_by(email="owner@example.com"))
        other = db.session.scalar(db.select(User.id).filter_by(email="other@example.com"))
        db.session.add_all([
            _subscription(owner, "Monthly subscription", "10.00", 0),
            _subscription(owner, "Weekly subscription", "1.25", 2, billing_cycle="weekly"),
            _subscription(owner, "Quarterly subscription", "12.30", 31, billing_cycle="quarterly"),
            _subscription(owner, "Yearly subscription", "12.95", 30, billing_cycle="yearly"),
            _subscription(owner, "Overdue European subscription", "30.00", -1, currency="EUR", billing_cycle="quarterly"),
            _subscription(owner, "Japanese subscription", "101", 90, currency="JPY", billing_cycle="yearly"),
            _subscription(owner, "Trial converting soon", "250", 7, subscription_type="trial_converts"),
            _subscription(owner, "Trial without a charge", "0", 8, subscription_type="trial_ends"),
            _subscription(owner, "Expired trial", "500", -1, subscription_type="trial_converts"),
            _subscription(owner, "Paused trial", "600", 1, status="paused", subscription_type="trial_converts"),
            _subscription(owner, "Paused subscription", "700", 1, status="paused"),
            _subscription(owner, "Cancelled subscription", "800", 1, status="cancelled"),
            _subscription(other, "Other account subscription", "975.00", 0),
        ])
        db.session.commit()

    response = client.get("/dashboard/")
    assert response.status_code == 200
    assert response.cache_control.private and response.cache_control.no_store
    html = response.get_data(as_text=True)
    assert "Preview mode" not in html
    assert "Other account subscription" not in html
    assert "Netflix" not in html
    assert "Monthly subscription" not in other_client.get("/dashboard/").get_data(as_text=True)

    stats = html.split('id="upcoming-payments"', 1)[0]
    assert "€10.00 + $20.60 + ¥8" in stats
    assert "€120.00 + $247.15 + ¥101" in stats
    assert re.search(r'Trials ending ≤ 7 days.*?class="stat-value">1</div>', stats, re.DOTALL)

    upcoming = _section(html, "upcoming-payments")
    due_in_order = ["Monthly subscription", "Weekly subscription", "Trial converting soon", "Yearly subscription"]
    positions = [upcoming.index(name) for name in due_in_order]
    assert positions == sorted(positions)
    assert upcoming.count('class="list-group-item ') == len(due_in_order)

    trials = _section(html, "active-free-trials")
    assert "Trial converting soon" in trials
    assert "Trial without a charge" in trials
    assert "Expired trial" not in trials
    assert "Paused trial" not in trials
    assert "Expired trial" in html
    assert "Paused subscription" in html
    assert "Cancelled subscription" in html

    guest_html = app.test_client().get("/dashboard/").get_data(as_text=True)
    assert "Preview mode" in guest_html
    assert "Monthly subscription" not in guest_html
    assert "Other account subscription" not in guest_html


def test_dashboard_updates_after_a_subscription_is_saved_paused_and_deleted(app, client, monkeypatch):
    monkeypatch.setattr(timezones, "utc_now", lambda: NOW)
    _register(client, "owner@example.com")
    empty = client.get("/dashboard/").get_data(as_text=True)
    assert "Add a subscription or free trial to see it here." in empty
    assert "Preview mode" not in empty
    assert "$0.00" in empty

    response = client.post("/subscriptions/new", data={
        "name": "New saved subscription",
        "price": "18.27",
        "currency": "USD",
        "billing_cycle": "monthly",
        "next_renewal_date": NOW.date().isoformat(),
        "category": "other",
        "subscription_type": "paid",
    })
    assert response.status_code == 302
    with app.app_context():
        subscription_id = db.session.scalars(db.select(Subscription.id)).one()
    path = f"/subscriptions/{subscription_id}"

    html = client.get("/dashboard/").get_data(as_text=True)
    assert "New saved subscription" in _section(html, "upcoming-payments")
    assert "$219.24" in html
    assert f'href="{path}/edit"' in html

    assert client.post(f"{path}/status", data={"status": "paused"}).status_code == 302
    html = client.get("/dashboard/").get_data(as_text=True)
    assert "New saved subscription" in html
    assert "New saved subscription" not in _section(html, "upcoming-payments")
    assert "$219.24" not in html

    assert client.post(f"{path}/delete").status_code == 302
    html = client.get("/dashboard/").get_data(as_text=True)
    assert "New saved subscription" not in html
    assert "Add a subscription or free trial to see it here." in html
