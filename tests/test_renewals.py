"""Renewal dates roll forward after they pass, without month-end drift."""
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.extensions import db
from app.models import ReminderDelivery, Subscription, User, UserPreferences
from app.services import mail, reminders, timezones
from app.services.renewals import advance_all_renewals, next_renewal_on_or_after


NOW = datetime(2026, 11, 16, 12, tzinfo=timezone.utc)
SETTINGS = mail.MailSettings("127.0.0.1", 1025, "none", "SubGuard <reminders@example.com>")


@pytest.mark.parametrize(
    ("anchor", "cycle", "today", "expected"),
    [
        # Not passed yet, or due today: unchanged.
        (date(2026, 11, 20), "monthly", date(2026, 11, 16), date(2026, 11, 20)),
        (date(2026, 11, 16), "monthly", date(2026, 11, 16), date(2026, 11, 16)),
        # Passed yesterday: one cycle later.
        (date(2026, 11, 15), "monthly", date(2026, 11, 16), date(2026, 12, 15)),
        (date(2026, 11, 15), "weekly", date(2026, 11, 16), date(2026, 11, 22)),
        (date(2026, 11, 15), "quarterly", date(2026, 11, 16), date(2027, 2, 15)),
        (date(2026, 11, 15), "yearly", date(2026, 11, 16), date(2027, 11, 15)),
        # Weekly lands exactly on today after two weeks.
        (date(2026, 11, 2), "weekly", date(2026, 11, 16), date(2026, 11, 16)),
        # Month ends clamp, then return to the 31st (no drift to the 28th).
        (date(2026, 1, 31), "monthly", date(2026, 2, 1), date(2026, 2, 28)),
        (date(2026, 1, 31), "monthly", date(2026, 3, 1), date(2026, 3, 31)),
        (date(2026, 1, 31), "monthly", date(2026, 4, 1), date(2026, 4, 30)),
        # Leap day: 28 Feb in normal years, 29 Feb again in the next leap year.
        (date(2024, 2, 29), "yearly", date(2026, 3, 1), date(2027, 2, 28)),
        (date(2024, 2, 29), "yearly", date(2027, 3, 1), date(2028, 2, 29)),
        (date(2024, 2, 29), "monthly", date(2028, 2, 1), date(2028, 2, 29)),
        # Several missed cycles are skipped in one step.
        (date(2025, 8, 30), "quarterly", date(2026, 11, 16), date(2026, 11, 30)),
        (date(2020, 6, 10), "monthly", date(2026, 11, 16), date(2026, 12, 10)),
    ],
)
def test_next_renewal_date(anchor, cycle, today, expected):
    assert next_renewal_on_or_after(anchor, cycle, today) == expected


def _register(client, email):
    password = "a sample passphrase"
    response = client.post("/register", data={"email": email, "password": password, "confirm_password": password})
    assert response.status_code == 302


def _add(owner_id, name, renewal, **overrides):
    values = {"price": Decimal("10.00"), "currency": "USD", "billing_cycle": "monthly", "category": "other", **overrides}
    subscription = Subscription(user_id=owner_id, name=name, next_renewal_date=renewal, **values)
    db.session.add(subscription)
    return subscription


def _dates(app):
    with app.app_context():
        rows = db.session.execute(db.select(Subscription.name, Subscription.next_renewal_date)).all()
        return dict(rows)


@pytest.mark.parametrize("page", ["/dashboard/", "/subscriptions/", "/calendar/"])
def test_pages_advance_only_the_viewers_active_renewals(app, client, monkeypatch, page):
    monkeypatch.setattr(timezones, "utc_now", lambda: NOW)
    _register(client, "owner@example.com")
    _register(app.test_client(), "other@example.com")
    with app.app_context():
        owner = db.session.scalar(db.select(User.id).filter_by(email="owner@example.com"))
        other = db.session.scalar(db.select(User.id).filter_by(email="other@example.com"))
        _add(owner, "Overdue", date(2026, 11, 10))
        _add(owner, "Due today", date(2026, 11, 16))
        _add(owner, "Month end", date(2026, 10, 31))
        _add(owner, "Paused", date(2026, 11, 10), status="paused")
        _add(owner, "Cancelled", date(2026, 11, 10), status="cancelled")
        _add(owner, "Trial became paid", date(2026, 11, 10), subscription_type="trial_converts")
        _add(owner, "Trial ended free", date(2026, 11, 10), subscription_type="trial_ends")
        _add(other, "Someone else's", date(2026, 11, 10))
        db.session.commit()

    assert client.get(page).status_code == 200

    assert _dates(app) == {
        "Overdue": date(2026, 12, 10),
        "Due today": date(2026, 11, 16),
        "Month end": date(2026, 11, 30),
        "Paused": date(2026, 11, 10),
        "Cancelled": date(2026, 11, 10),
        "Trial became paid": date(2026, 12, 10),
        "Trial ended free": date(2026, 11, 10),
        "Someone else's": date(2026, 11, 10),
    }
    with app.app_context():
        converted = db.session.scalar(db.select(Subscription).filter_by(name="Trial became paid"))
        assert converted.subscription_type == "paid"
        month_end = db.session.scalar(db.select(Subscription).filter_by(name="Month end"))
        assert month_end.billing_anchor_date == date(2026, 10, 31)


def test_month_end_returns_to_the_31st_on_later_visits(app, client, monkeypatch):
    clock = {"now": datetime(2026, 2, 1, 12, tzinfo=timezone.utc)}
    monkeypatch.setattr(timezones, "utc_now", lambda: clock["now"])
    _register(client, "owner@example.com")
    with app.app_context():
        owner = db.session.scalar(db.select(User.id))
        _add(owner, "Month end", date(2026, 1, 31))
        db.session.commit()

    client.get("/dashboard/")
    assert _dates(app)["Month end"] == date(2026, 2, 28)

    clock["now"] = datetime(2026, 3, 1, 12, tzinfo=timezone.utc)
    client.get("/dashboard/")
    assert _dates(app)["Month end"] == date(2026, 3, 31)


def test_editing_keeps_the_anchor_unless_the_date_changes(app, client, monkeypatch):
    monkeypatch.setattr(timezones, "utc_now", lambda: datetime(2026, 2, 1, 12, tzinfo=timezone.utc))
    _register(client, "owner@example.com")
    form = {
        "name": "Month end", "price": "10.00", "currency": "USD", "billing_cycle": "monthly",
        "next_renewal_date": "2026-01-31", "category": "other", "subscription_type": "paid",
    }
    assert client.post("/subscriptions/new", data=form).status_code == 302
    client.get("/subscriptions/")  # rolls 31 Jan forward to 28 Feb

    with app.app_context():
        saved = db.session.scalars(db.select(Subscription)).one()
        subscription_id = saved.id
        assert (saved.next_renewal_date, saved.billing_anchor_date) == (date(2026, 2, 28), date(2026, 1, 31))

    renamed = {**form, "name": "Renamed", "next_renewal_date": "2026-02-28"}
    assert client.post(f"/subscriptions/{subscription_id}/edit", data=renamed).status_code == 302
    with app.app_context():
        assert db.session.get(Subscription, subscription_id).billing_anchor_date == date(2026, 1, 31)

    moved = {**renamed, "next_renewal_date": "2026-03-05"}
    assert client.post(f"/subscriptions/{subscription_id}/edit", data=moved).status_code == 302
    with app.app_context():
        assert db.session.get(Subscription, subscription_id).billing_anchor_date == date(2026, 3, 5)


def test_worker_advances_by_local_date_and_reminds_for_the_new_date(app, monkeypatch):
    delivered = []
    monkeypatch.setattr(reminders, "deliver", lambda settings, message: delivered.append(message))
    # 23:30 UTC on 16 Nov is already 17 Nov in Auckland but still 16 Nov in UTC.
    late = datetime(2026, 11, 16, 23, 30, tzinfo=timezone.utc)
    with app.app_context():
        ahead = User(email="ahead@example.com", password_hash="unused")
        utc_user = User(email="utc@example.com", password_hash="unused")
        db.session.add_all([ahead, utc_user])
        db.session.flush()
        db.session.add(UserPreferences(user_id=ahead.id, time_zone="Pacific/Auckland", reminder_days=None))
        _add(ahead.id, "Ahead weekly", date(2026, 11, 16), billing_cycle="weekly")
        _add(utc_user.id, "UTC weekly", date(2026, 11, 16), billing_cycle="weekly")
        _add(utc_user.id, "UTC overdue weekly", date(2026, 11, 12), billing_cycle="weekly")
        db.session.commit()

        assert advance_all_renewals(late) == 2
        assert advance_all_renewals(late) == 0

    assert _dates(app) == {
        "Ahead weekly": date(2026, 11, 23),
        "UTC weekly": date(2026, 11, 16),
        "UTC overdue weekly": date(2026, 11, 19),
    }

    with app.app_context():
        # The worker itself advances first (weekly: 11 Nov -> 18 Nov), then reminds about the new date.
        db.session.execute(db.update(Subscription).values(next_renewal_date=date(2026, 11, 11), billing_anchor_date=None))
        db.session.commit()
        sent, failed = reminders.send_due_reminders(SETTINGS, 3, now=NOW)
        assert (sent, failed) == (3, 0)
        assert all("renews on 18 Nov 2026" in message.get_content() for message in delivered)
        assert db.session.scalars(db.select(ReminderDelivery.event_date).distinct()).all() == [date(2026, 11, 18)]


def test_init_db_adds_the_anchor_column_to_an_older_database(app):
    with app.app_context():
        db.drop_all()
        with db.engine.begin() as connection:
            connection.execute(db.text(
                "CREATE TABLE subscriptions (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, "
                "name VARCHAR(120) NOT NULL, price NUMERIC(9, 2) NOT NULL, currency VARCHAR(3) NOT NULL, "
                "billing_cycle VARCHAR(12) NOT NULL, next_renewal_date DATE NOT NULL, category VARCHAR(20) NOT NULL, "
                "subscription_type VARCHAR(20) NOT NULL, status VARCHAR(12) NOT NULL, cancellation_url VARCHAR(2048))"
            ))
            connection.execute(db.text(
                "INSERT INTO subscriptions (user_id, name, price, currency, billing_cycle, next_renewal_date, "
                "category, subscription_type, status) VALUES (1, 'Old row', 5, 'USD', 'monthly', '2026-11-10', "
                "'other', 'paid', 'active')"
            ))

    runner = app.test_cli_runner()
    assert runner.invoke(args=["init-db"]).exit_code == 0
    assert runner.invoke(args=["init-db"]).exit_code == 0  # safe to run again

    with app.app_context():
        old = db.session.scalars(db.select(Subscription)).one()
        assert (old.name, old.billing_anchor_date) == ("Old row", None)
