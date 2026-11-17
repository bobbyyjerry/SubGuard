"""Brevo reminder delivery through the CLI and scheduled web endpoint."""
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from email.message import EmailMessage
from io import BytesIO
import json
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.error import HTTPError, URLError

import pytest

from app.extensions import db
from app.models import ReminderDelivery, Subscription, User
from app.services import mail, reminders


NOW = datetime(2026, 11, 17, 12, tzinfo=timezone.utc)
SENDER = "SubGuard <sender@example.com>"
API_KEY = "test-brevo-key"


def _message():
    message = EmailMessage()
    message["From"] = SENDER
    message["To"] = "owner@example.com"
    message["Subject"] = "Test reminder"
    message.set_content("Your subscription renews tomorrow.")
    return message


@pytest.mark.parametrize("entry_point", ["cli", "scheduled"])
def test_brevo_delivers_and_records_reminder(app, client, monkeypatch, entry_point):
    connect = Mock(return_value=nullcontext(SimpleNamespace(status=201)))
    monkeypatch.setattr(mail, "urlopen", connect)
    monkeypatch.setattr(reminders, "utc_now", lambda: NOW)
    app.config.update(
        MAIL_TRANSPORT="brevo", MAIL_SERVER=None, MAIL_DEFAULT_SENDER=SENDER,
        BREVO_API_KEY=API_KEY, REMINDER_DAYS=3, REMINDER_TRIGGER_TOKEN="t" * 40,
    )
    with app.app_context():
        owner = User(email="owner@example.com", password_hash="unused")
        db.session.add(owner)
        db.session.flush()
        db.session.add(Subscription(
            user_id=owner.id, name="Demo Streaming", price=Decimal("5"), currency="USD",
            billing_cycle="monthly", category="streaming", next_renewal_date=NOW.date() + timedelta(days=1),
        ))
        db.session.commit()

    if entry_point == "cli":
        result = app.test_cli_runner().invoke(args=["reminders", "--once"])
        assert result.exit_code == 0, result.output
        assert "Reminders sent: 1. Failed or unconfirmed: 0." in result.output
    else:
        response = client.post("/tasks/reminders", headers={"Authorization": "Bearer " + "t" * 40})
        assert response.status_code == 200
        assert response.get_json() == {"sent": 1, "failed": 0}

    connect.assert_called_once()
    request = connect.call_args.args[0]
    assert request.full_url == "https://api.brevo.com/v3/smtp/email"
    assert request.get_method() == "POST"
    assert request.unredirected_hdrs["Api-key"] == API_KEY
    payload = json.loads(request.data)
    assert payload["sender"] == {"name": "SubGuard", "email": "sender@example.com"}
    assert payload["to"] == [{"email": "owner@example.com"}]
    assert "Demo Streaming renews" in payload["textContent"]
    with app.app_context():
        delivery = db.session.scalars(db.select(ReminderDelivery)).one()
        assert delivery.sent_at is not None


@pytest.mark.parametrize(("status", "error_type"), [
    (401, mail.MailRejected),
    (429, mail.MailRejected),
    (408, mail.MailUnconfirmed),
    (503, mail.MailUnconfirmed),
])
def test_brevo_distinguishes_http_rejection_from_uncertain_delivery(monkeypatch, status, error_type):
    error = HTTPError(mail.BREVO_EMAIL_URL, status, "Test HTTP error", {}, BytesIO(b""))
    monkeypatch.setattr(mail, "urlopen", Mock(side_effect=error))
    with pytest.raises(error_type):
        mail.deliver(mail.BrevoSettings(SENDER, API_KEY), _message())


def test_brevo_holds_a_timed_out_handoff(monkeypatch):
    monkeypatch.setattr(mail, "urlopen", Mock(side_effect=URLError(TimeoutError())))
    with pytest.raises(mail.MailUnconfirmed):
        mail.deliver(mail.BrevoSettings(SENDER, API_KEY), _message())


def test_brevo_requires_an_api_key():
    with pytest.raises(ValueError, match="BREVO_API_KEY"):
        mail.mail_settings_from_config({"MAIL_TRANSPORT": "brevo", "MAIL_DEFAULT_SENDER": SENDER})
