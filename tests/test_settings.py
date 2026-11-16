"""Per-account preferences and local calendar dates."""
from datetime import datetime, timezone
import re

from app.extensions import db
from app.models import User, UserPreferences
from app.services import timezones


def _register(client, email):
    password = "a sample passphrase"
    response = client.post("/register", data={"email": email, "password": password, "confirm_password": password})
    assert response.status_code == 302


def test_settings_validates_and_saves_only_the_current_account(app, client):
    assert client.get("/settings/").location.startswith("/login?")
    _register(client, "owner@example.com")
    other = app.test_client()
    _register(other, "other@example.com")
    app.config["WTF_CSRF_ENABLED"] = True

    page = client.get("/settings/")
    assert page.cache_control.private and page.cache_control.no_store
    assert b'value="UTC"' in page.data
    match = re.search(rb'name="csrf_token"[^>]*value="([^"]+)"', page.data)
    assert match is not None
    assert client.post("/settings/", data={"time_zone": "Asia/Shanghai", "reminder_days": "7"}).status_code == 400
    token = {"csrf_token": match[1].decode()}

    invalid = client.post("/settings/", data={**token, "time_zone": "invalid", "reminder_days": "10"})
    assert b"Choose a time zone from the list." in invalid.data
    assert b"Not a valid choice." in invalid.data
    with app.app_context():
        assert db.session.scalars(db.select(UserPreferences)).first() is None
        owner_id = db.session.scalar(db.select(User.id).filter_by(email="owner@example.com"))
        other_id = db.session.scalar(db.select(User.id).filter_by(email="other@example.com"))

    saved = client.post(
        "/settings/", data={**token, "time_zone": "Asia/Shanghai", "reminder_days": "7", "user_id": other_id},
        follow_redirects=True,
    )
    assert b"Settings saved." in saved.data
    assert re.search(rb'<option [^>]*selected[^>]*value="7"[^>]*>7 days before</option>', saved.data)
    assert re.search(rb'<input [^>]*name="time_zone"[^>]*value="Asia/Shanghai"', saved.data)
    assert re.search(rb'<input [^>]*name="time_zone"[^>]*value="UTC"', other.get("/settings/").data)
    with app.app_context():
        preferences = db.session.get(UserPreferences, owner_id)
        assert (preferences.time_zone, preferences.reminder_days) == ("Asia/Shanghai", 7)
        assert db.session.get(UserPreferences, other_id) is None

    assert client.post("/settings/", data={**token, "time_zone": "Europe/Paris", "reminder_days": "default"}).status_code == 302
    with app.app_context():
        preferences = db.session.get(UserPreferences, owner_id)
        assert (preferences.time_zone, preferences.reminder_days) == ("Europe/Paris", None)


def test_calendar_dashboard_and_subscription_cards_follow_account_date(client, monkeypatch):
    now = datetime(2026, 11, 30, 18, tzinfo=timezone.utc)
    monkeypatch.setattr(timezones, "utc_now", lambda: now)
    _register(client, "owner@example.com")

    response = client.post("/subscriptions/new", data={
        "name": "Midnight renewal",
        "price": "10",
        "currency": "USD",
        "billing_cycle": "monthly",
        "next_renewal_date": "2026-12-01",
        "category": "other",
        "subscription_type": "paid",
    })
    assert response.status_code == 302
    assert b"November 2026" in client.get("/calendar/").data
    assert b">Tomorrow</span>" in client.get("/dashboard/").data

    assert client.post("/settings/", data={"time_zone": "Asia/Shanghai", "reminder_days": "0"}).status_code == 302
    calendar_page = client.get("/calendar/").data
    assert b"December 2026" in calendar_page
    assert b'datetime="2026-12-01" class="calendar-date" aria-current="date"' in calendar_page
    assert b"Midnight renewal" in calendar_page
    assert b">Today</span>" in client.get("/dashboard/").data
    assert b">Today</span>" in client.get("/subscriptions/").data
