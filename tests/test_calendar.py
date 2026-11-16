"""Calendar navigation and private, upcoming subscription dates."""
from datetime import date
from decimal import Decimal

from app.extensions import db
from app.models import Subscription, User
from app.routes import calendar


class FixedDate(date):
    @classmethod
    def today(cls):
        return cls(2026, 12, 28)


def _register(client, email):
    password = "a sample passphrase"
    response = client.post("/register", data={"email": email, "password": password, "confirm_password": password})
    assert response.status_code == 302


def _subscription(user_id, name, event_date, **overrides):
    values = {"price": Decimal("12.00"), "currency": "USD", "billing_cycle": "monthly", **overrides}
    return Subscription(
        user_id=user_id, name=name, category="other", next_renewal_date=event_date, **values,
    )


def test_calendar_requires_login(client):
    response = client.get("/calendar/")
    assert response.status_code == 302
    assert response.location.startswith("/login?")


def test_calendar_groups_upcoming_renewals_and_trials_for_one_account(app, client, monkeypatch):
    monkeypatch.setattr(calendar, "date", FixedDate)
    _register(client, "owner@example.com")
    other_client = app.test_client()
    _register(other_client, "other@example.com")
    today = FixedDate.today()
    with app.app_context():
        owner = db.session.scalar(db.select(User.id).filter_by(email="owner@example.com"))
        other = db.session.scalar(db.select(User.id).filter_by(email="other@example.com"))
        renewal = _subscription(owner, "Renewal due today", today)
        db.session.add_all([
            renewal,
            _subscription(owner, "Trial converting today", today, subscription_type="trial_converts"),
            _subscription(owner, "Trial without a charge", today, subscription_type="trial_ends", price=Decimal(0)),
            _subscription(owner, "Month end renewal", date(2026, 12, 31)),
            _subscription(owner, "Next month renewal", date(2027, 1, 1)),
            _subscription(owner, "Past renewal", date(2026, 12, 27)),
            _subscription(owner, "Paused renewal", today, status="paused"),
            _subscription(owner, "Cancelled renewal", today, status="cancelled"),
            _subscription(other, "Other account trial", today, subscription_type="trial_ends"),
        ])
        db.session.commit()
        renewal_id = renewal.id

    response = client.get("/calendar/")
    assert response.status_code == 200
    assert response.cache_control.private and response.cache_control.no_store
    html = response.get_data(as_text=True)
    assert "December 2026" in html
    assert 'href="/calendar/?month=2027-01"' in html
    assert 'disabled aria-label="Previous month"' in html
    assert 'datetime="2026-12-28" class="calendar-date" aria-current="date"' in html
    assert 'href="#events-2026-12-28" class="small">+1 more' in html
    assert 'aria-label="3 events on 28 Dec 2026"' in html
    assert f'href="/subscriptions/{renewal_id}/edit"' in html
    agenda = html.split('id="month-events"', 1)[1]
    assert agenda.index("Renewal due today") < agenda.index("Trial converting today") < agenda.index("Month end renewal")
    assert "Trial without a charge" in agenda and "No charge" in agenda
    assert "Then $12.00/mo" in agenda
    for excluded in ("Other account trial", "Past renewal", "Paused renewal", "Cancelled renewal", "Next month renewal"):
        assert excluded not in html
    other_html = other_client.get("/calendar/").get_data(as_text=True)
    assert "Other account trial" in other_html
    assert "Renewal due today" not in other_html

    january = client.get("/calendar/?month=2027-01").get_data(as_text=True)
    assert "January 2027" in january
    assert 'href="/calendar/?month=2026-12"' in january
    assert 'href="/calendar/?month=2027-02"' in january
    assert "Next month renewal" in january
    assert "Month end renewal" not in january
    assert 'aria-current="date"' not in january

    assert client.post(f"/subscriptions/{renewal_id}/status", data={"status": "paused"}).status_code == 302
    assert b"Renewal due today" not in client.get("/calendar/").data


def test_calendar_handles_empty_and_unavailable_months(client, monkeypatch):
    monkeypatch.setattr(calendar, "date", FixedDate)
    _register(client, "owner@example.com")
    for month in ("invalid", "2026-13", "2026-11"):
        response = client.get(f"/calendar/?month={month}")
        assert response.status_code == 200
        assert b"December 2026" in response.data
        assert b"No upcoming renewals or trial end dates this month." in response.data

    leap_month = client.get("/calendar/?month=2028-02")
    assert leap_month.status_code == 200
    assert b"February 2028" in leap_month.data
    assert b'datetime="2028-02-29"' in leap_month.data
    assert b'datetime="2028-02-30"' not in leap_month.data

    last_month = client.get("/calendar/?month=9999-12")
    assert last_month.status_code == 200
    assert b'datetime="9999-12-31"' in last_month.data
    assert b'disabled aria-label="Next month"' in last_month.data
