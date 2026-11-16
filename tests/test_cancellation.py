"""Marking subscriptions as cancelled and estimating what that saves."""
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.extensions import db
from app.models import Subscription, User
from app.services import timezones
from app.services.renewals import charges_due


NOW = datetime(2026, 11, 16, 12, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    ("first_charge", "cycle", "today", "expected"),
    [
        (date(2026, 11, 17), "monthly", date(2026, 11, 16), 0),  # not reached yet
        (date(2026, 11, 16), "monthly", date(2026, 11, 16), 1),  # due today
        (date(2026, 8, 16), "monthly", date(2026, 11, 16), 4),
        (date(2026, 8, 17), "monthly", date(2026, 11, 16), 3),
        (date(2026, 1, 31), "monthly", date(2026, 2, 28), 2),  # month end clamps
        (date(2026, 1, 31), "monthly", date(2026, 2, 27), 1),
        (date(2026, 11, 2), "weekly", date(2026, 11, 16), 3),
        (date(2026, 11, 3), "weekly", date(2026, 11, 16), 2),
        (date(2026, 2, 16), "quarterly", date(2026, 11, 16), 4),
        (date(2024, 11, 16), "yearly", date(2026, 11, 16), 3),
        (date(2024, 2, 29), "yearly", date(2026, 2, 28), 3),  # leap day
    ],
)
def test_charges_due(first_charge, cycle, today, expected):
    assert charges_due(first_charge, cycle, today) == expected


def _register(client, email):
    password = "a sample passphrase"
    response = client.post("/register", data={"email": email, "password": password, "confirm_password": password})
    assert response.status_code == 302


def _add(owner_id, name, price, renewal, **overrides):
    values = {"currency": "USD", "billing_cycle": "monthly", "category": "other", **overrides}
    subscription = Subscription(
        user_id=owner_id, name=name, price=Decimal(price), next_renewal_date=renewal, **values,
    )
    db.session.add(subscription)
    return subscription


def _section(html, heading_id):
    return html.split(f'id="{heading_id}"', 1)[1].split("</section>", 1)[0]


def test_cancel_and_resume_from_the_card_menu(app, client, monkeypatch):
    monkeypatch.setattr(timezones, "utc_now", lambda: NOW)
    _register(client, "owner@example.com")
    with app.app_context():
        owner = db.session.scalar(db.select(User.id))
        subscription = _add(owner, "Overdue streaming", "10.00", date(2026, 11, 10))
        db.session.commit()
        path = f"/subscriptions/{subscription.id}/status"

    page = client.get("/subscriptions/").get_data(as_text=True)
    assert 'name="status" value="cancelled"' in page
    assert "Mark as cancelled" in page

    # Reset the date to check that cancelling brings an overdue date forward first.
    with app.app_context():
        db.session.execute(db.update(Subscription).values(next_renewal_date=date(2026, 11, 10), billing_anchor_date=None))
        db.session.commit()

    response = client.post(path, data={"status": "cancelled"}, follow_redirects=True)
    html = response.get_data(as_text=True)
    assert "Remember to cancel with the provider too." in html
    assert "Would have renewed 10 Dec 2026" in html
    assert "Mark as cancelled" not in html
    assert "Resume tracking" in html
    with app.app_context():
        saved = db.session.scalars(db.select(Subscription)).one()
        assert (saved.status, saved.next_renewal_date) == ("cancelled", date(2026, 12, 10))

    # Cancelled subscriptions stay put and drop out of spending.
    dashboard = client.get("/dashboard/").get_data(as_text=True)
    assert "$0.00" in dashboard.split('id="upcoming-payments"', 1)[0]
    with app.app_context():
        assert db.session.scalars(db.select(Subscription.next_renewal_date)).one() == date(2026, 12, 10)

    response = client.post(path, data={"status": "active"}, follow_redirects=True)
    assert "Subscription resumed." in response.get_data(as_text=True)
    assert client.post(path, data={"status": "deleted"}).status_code == 400


def test_cancelling_is_private_to_the_owner(app, client):
    _register(client, "owner@example.com")
    other_client = app.test_client()
    _register(other_client, "other@example.com")
    with app.app_context():
        owner = db.session.scalar(db.select(User.id).filter_by(email="owner@example.com"))
        subscription = _add(owner, "Private", "10.00", date(2030, 1, 1))
        db.session.commit()
        subscription_id = subscription.id

    assert other_client.post(f"/subscriptions/{subscription_id}/status", data={"status": "cancelled"}).status_code == 404
    with app.app_context():
        assert db.session.get(Subscription, subscription_id).status == "active"


def test_analytics_estimates_savings_by_currency(app, client, monkeypatch):
    monkeypatch.setattr(timezones, "utc_now", lambda: NOW)
    _register(client, "owner@example.com")
    other_client = app.test_client()
    _register(other_client, "other@example.com")
    with app.app_context():
        owner = db.session.scalar(db.select(User.id).filter_by(email="owner@example.com"))
        other = db.session.scalar(db.select(User.id).filter_by(email="other@example.com"))
        _add(owner, "Active music", "5.00", date(2026, 12, 1))
        # First avoided charge 16 Aug: Aug, Sep, Oct, Nov = 4 charges.
        _add(owner, "Old streaming", "10.00", date(2026, 8, 16), status="cancelled")
        # Cancelled today, nothing avoided yet.
        _add(owner, "Just cancelled", "120.00", date(2027, 3, 1), status="cancelled", billing_cycle="yearly")
        _add(owner, "Cancelled trial", "20.00", date(2026, 11, 1), status="cancelled", subscription_type="trial_converts")
        _add(owner, "Euro gym", "30.00", date(2026, 10, 20), status="cancelled", currency="EUR")
        _add(owner, "Free trial that ended", "50.00", date(2026, 1, 1), status="cancelled", subscription_type="trial_ends")
        _add(owner, "Free plan", "0", date(2026, 1, 1), status="cancelled")
        _add(owner, "Paused", "70.00", date(2026, 1, 1), status="paused")
        _add(other, "Someone else's", "999.00", date(2026, 1, 1), status="cancelled")
        db.session.commit()

    html = client.get("/analytics/").get_data(as_text=True)
    savings = _section(html, "cancellation-savings")
    # Saved so far: 4 x $10 + 0 + 1 x $20. Per year: $120 + $120 + $240.
    assert "$60.00" in savings and "$480.00" in savings
    for name in ("Old streaming", "Just cancelled", "Cancelled trial"):
        assert name in savings
    for name in ("Euro gym", "Free trial that ended", "Free plan", "Paused", "Active music", "Someone else"):
        assert name not in savings
    assert "16 Aug 2026" in savings
    assert 'href="/analytics/?currency=EUR"' in html

    euro = client.get("/analytics/?currency=EUR").get_data(as_text=True)
    euro_savings = _section(euro, "cancellation-savings")
    assert "€30.00" in euro_savings and "€360.00" in euro_savings
    assert "Euro gym" in euro_savings and "Old streaming" not in euro_savings
    # No active EUR spending, but savings exist, so the empty state stays hidden.
    assert "No spending to show yet" not in euro

    other_html = other_client.get("/analytics/").get_data(as_text=True)
    assert "$999.00" in _section(other_html, "cancellation-savings")
    assert "Old streaming" not in other_html


def test_analytics_hides_savings_when_nothing_is_cancelled(app, client):
    _register(client, "owner@example.com")
    with app.app_context():
        owner = db.session.scalar(db.select(User.id))
        _add(owner, "Active music", "5.00", date(2030, 1, 1))
        db.session.commit()
    assert b"cancellation-savings" not in client.get("/analytics/").data
