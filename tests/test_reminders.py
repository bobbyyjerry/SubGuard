"""Reminder selection, SMTP outcomes, and duplicate prevention."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from email.message import EmailMessage
import smtplib
from unittest.mock import Mock

import pytest

from app.extensions import db
from app.models import ReminderDelivery, Subscription, User, UserPreferences
from app.services import mail, reminders


NOW = datetime(2026, 11, 16, 12, tzinfo=timezone.utc)
TODAY = NOW.date()
SETTINGS = mail.MailSettings("127.0.0.1", 1025, "none", "SubGuard <reminders@example.com>")


def _subscription(owner, name, days, **overrides):
    details = {
        "price": Decimal("9.99"),
        "currency": "USD",
        "billing_cycle": "monthly",
        "category": "other",
        **overrides,
    }
    return Subscription(
        user_id=owner.id, name=name, next_renewal_date=TODAY + timedelta(days=days), **details,
    )


def test_sends_one_reminder_per_upcoming_active_date(app, monkeypatch):
    delivered = []
    monkeypatch.setattr(reminders, "deliver", lambda settings, message: delivered.append(message))
    with app.app_context():
        owner = User(email="owner@example.com", password_hash="unused")
        other = User(email="other@example.com", password_hash="unused")
        db.session.add_all([owner, other])
        db.session.flush()
        renewal = _subscription(owner, "Streaming service", 3)
        db.session.add_all([
            renewal,
            _subscription(owner, "Design tool", 2, subscription_type="trial_converts"),
            _subscription(other, "News service", 1, subscription_type="trial_ends", price=Decimal(0)),
            _subscription(owner, "Paused service", 1, status="paused"),
            _subscription(owner, "Cancelled service", 1, status="cancelled"),
            _subscription(owner, "Later service", 4),
            _subscription(owner, "Due today", 0),
            _subscription(owner, "Expired trial", -1, subscription_type="trial_converts"),
        ])
        db.session.commit()

        assert reminders.send_due_reminders(SETTINGS, 3, now=NOW) == (3, 0)
        assert reminders.send_due_reminders(SETTINGS, 3, now=NOW) == (0, 0)
        assert [str(message["To"]) for message in delivered] == [
            "other@example.com", "owner@example.com", "owner@example.com",
        ]
        assert "without a charge" in delivered[0].get_content()
        assert "Expected price after the trial: $9.99/mo." in delivered[1].get_content()
        assert "Streaming service renews on 19 Nov 2026." in delivered[2].get_content()
        assert "Expected charge: $9.99." in delivered[2].get_content()
        assert len(db.session.scalars(db.select(ReminderDelivery).where(ReminderDelivery.sent_at.is_not(None))).all()) == 3

        renewal.next_renewal_date = TODAY + timedelta(days=2)
        db.session.commit()
        assert reminders.send_due_reminders(SETTINGS, 3, now=NOW) == (1, 0)
        assert "Streaming service renews on 18 Nov 2026." in delivered[-1].get_content()


def test_rejected_mail_retries_but_unconfirmed_handoff_is_held(app, monkeypatch):
    smtp = Mock(side_effect=[mail.MailRejected, mail.MailUnconfirmed, None])
    monkeypatch.setattr(reminders, "deliver", smtp)
    with app.app_context():
        owner = User(email="owner@example.com", password_hash="unused")
        db.session.add(owner)
        db.session.flush()
        retry = _subscription(owner, "Definitively rejected", 1)
        unknown = _subscription(owner, "Unconfirmed", 2)
        db.session.add_all([retry, unknown])
        db.session.commit()

        assert reminders.send_due_reminders(SETTINGS, 3, now=NOW) == (0, 2)
        assert db.session.get(ReminderDelivery, (retry.id, retry.next_renewal_date)) is None
        assert db.session.get(ReminderDelivery, (unknown.id, unknown.next_renewal_date)).sent_at is None
        assert reminders.send_due_reminders(SETTINGS, 3, now=NOW) == (1, 0)
        assert "Definitively rejected" in smtp.call_args.args[1].get_content()
        assert reminders.send_due_reminders(SETTINGS, 3, now=NOW) == (0, 0)


def test_reminder_uses_local_date_and_account_lead_time(app, monkeypatch):
    delivered = []
    monkeypatch.setattr(reminders, "deliver", lambda settings, message: delivered.append(str(message["To"])))
    with app.app_context():
        for account, zone, preferred_days, due_in in [
            ("shanghai", "Asia/Shanghai", None, 4),
            ("los-angeles", "America/Los_Angeles", None, 4),
            ("seven-days", "UTC", 7, 7),
            ("one-day", "UTC", 1, 2),
            ("reminders-off", "UTC", 0, 2),
        ]:
            user = User(email=f"{account}@example.com", password_hash="unused")
            db.session.add(user)
            db.session.flush()
            db.session.add(UserPreferences(user_id=user.id, time_zone=zone, reminder_days=preferred_days))
            subscription = _subscription(user, account, due_in)
            db.session.add(subscription)
            db.session.flush()
            if preferred_days == 0:
                disabled_id = subscription.id
        db.session.commit()

        # Shanghai is already on the next calendar day.
        evening_utc = NOW + timedelta(hours=9)
        assert reminders.send_due_reminders(SETTINGS, 3, now=evening_utc) == (2, 0)
        assert set(delivered) == {"shanghai@example.com", "seven-days@example.com"}

        next_day_utc = NOW + timedelta(days=1)
        delivered.clear()
        assert reminders.send_due_reminders(SETTINGS, 3, now=next_day_utc) == (2, 0)
        assert set(delivered) == {"los-angeles@example.com", "one-day@example.com"}
        assert not reminders._claim(disabled_id, TODAY + timedelta(days=2))


def test_claim_is_unique_and_checks_latest_subscription_state(app):
    with app.app_context():
        owner = User(email="owner@example.com", password_hash="unused")
        db.session.add(owner)
        db.session.flush()
        subscription = _subscription(owner, "Active", 1)
        paused = _subscription(owner, "Paused", 1, status="paused")
        db.session.add_all([subscription, paused])
        db.session.commit()
        event_date = TODAY + timedelta(days=1)

        assert reminders._claim(subscription.id, event_date)
        assert not reminders._claim(subscription.id, event_date)
        assert not reminders._claim(paused.id, event_date)
        assert not reminders._claim(subscription.id, TODAY + timedelta(days=2))


def test_smtp_classifies_rejection_and_lost_handoff(monkeypatch):
    relay = Mock()
    monkeypatch.setattr(mail.smtplib, "SMTP", lambda *args, **kwargs: relay)
    message = EmailMessage()
    relay.send_message.side_effect = smtplib.SMTPDataError(450, b"Please retry later")
    with pytest.raises(mail.MailRejected):
        mail.deliver(SETTINGS, message)

    relay.send_message.side_effect = smtplib.SMTPServerDisconnected("Timed out after DATA")
    with pytest.raises(mail.MailUnconfirmed):
        mail.deliver(SETTINGS, message)
    assert relay.close.call_count == 2


def test_worker_cli_configuration_and_run_once(app):
    app.config.update(
        MAIL_SERVER=None, MAIL_DEFAULT_SENDER=None, MAIL_USERNAME=None, MAIL_PASSWORD=None,
        MAIL_SECURITY="none", MAIL_PORT=1025, REMINDER_DAYS=3,
    )
    runner = app.test_cli_runner()
    unconfigured = runner.invoke(args=["reminders", "--once"])
    assert unconfigured.exit_code == 1
    assert "Set MAIL_SERVER and MAIL_DEFAULT_SENDER" in unconfigured.output

    app.config.update(MAIL_SERVER=SETTINGS.server, MAIL_DEFAULT_SENDER=SETTINGS.sender)
    result = runner.invoke(args=["reminders", "--once"])
    assert result.exit_code == 0, result.output
    assert "Reminders sent: 0." in result.output
