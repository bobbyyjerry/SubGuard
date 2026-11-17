"""The secret-protected address an outside scheduler calls to send reminders."""
from datetime import date, timedelta
from decimal import Decimal

from app.extensions import db
from app.models import ReminderDelivery, Subscription, User
from app.services import reminders

TOKEN = "t" * 40
MAIL = {"MAIL_SERVER": "127.0.0.1", "MAIL_DEFAULT_SENDER": "SubGuard <reminders@example.com>", "MAIL_SECURITY": "none"}


def _call(client, token=TOKEN):
    headers = {"Authorization": f"Bearer {token}"} if token is not None else {}
    return client.post("/tasks/reminders", headers=headers)


def _add_due_subscription(app):
    with app.app_context():
        owner = User(email="owner@example.com", password_hash="unused")
        db.session.add(owner)
        db.session.flush()
        db.session.add(Subscription(
            user_id=owner.id, name="Due soon", price=Decimal("9.99"), currency="USD", billing_cycle="monthly",
            category="other", next_renewal_date=date.today() + timedelta(days=2),
        ))
        db.session.commit()


def test_address_does_not_exist_until_a_long_token_is_set(app, client):
    assert _call(client).status_code == 404
    app.config["REMINDER_TRIGGER_TOKEN"] = "too-short"
    assert _call(client, "too-short").status_code == 404
    # An empty token must never match an empty header.
    app.config["REMINDER_TRIGGER_TOKEN"] = ""
    assert client.post("/tasks/reminders", headers={"Authorization": "Bearer "}).status_code == 404


def test_wrong_or_missing_token_is_refused_and_sends_nothing(app, client, monkeypatch):
    delivered = []
    monkeypatch.setattr(reminders, "deliver", lambda settings, message: delivered.append(message))
    app.config.update(MAIL, REMINDER_TRIGGER_TOKEN=TOKEN)
    _add_due_subscription(app)

    assert _call(client, None).status_code == 403
    assert _call(client, "w" * 40).status_code == 403
    assert client.post("/tasks/reminders", headers={"Authorization": TOKEN}).status_code == 403
    assert client.get("/tasks/reminders", headers={"Authorization": f"Bearer {TOKEN}"}).status_code == 405
    # The token is never accepted from the address itself, where it would end up in logs.
    assert client.post(f"/tasks/reminders?token={TOKEN}").status_code == 403
    assert delivered == []


def test_right_token_sends_each_reminder_once(app, client, monkeypatch):
    delivered = []
    monkeypatch.setattr(reminders, "deliver", lambda settings, message: delivered.append(message))
    app.config.update(MAIL, REMINDER_TRIGGER_TOKEN=TOKEN)
    _add_due_subscription(app)

    first = _call(client)
    assert first.status_code == 200 and first.get_json() == {"sent": 1, "failed": 0}
    assert len(delivered) == 1 and delivered[0]["To"] == "owner@example.com"

    # Calling again the same day sends nothing new.
    second = _call(client)
    assert second.status_code == 200 and second.get_json() == {"sent": 0, "failed": 0}
    assert len(delivered) == 1
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(ReminderDelivery)) == 1


def test_works_with_csrf_protection_switched_on(app, client, monkeypatch):
    monkeypatch.setattr(reminders, "deliver", lambda settings, message: None)
    app.config.update(MAIL, REMINDER_TRIGGER_TOKEN=TOKEN, WTF_CSRF_ENABLED=True)
    assert _call(client).status_code == 200
    # Ordinary forms still need their CSRF token.
    assert client.post("/logout").status_code == 400


def test_reports_when_email_is_not_set_up_or_a_send_fails(app, client, monkeypatch):
    app.config.update(REMINDER_TRIGGER_TOKEN=TOKEN, MAIL_SERVER=None, MAIL_DEFAULT_SENDER=None)
    response = _call(client)
    assert response.status_code == 503 and "not set up" in response.get_json()["error"]

    def refuse(settings, message):
        raise reminders.MailRejected("refused")

    monkeypatch.setattr(reminders, "deliver", refuse)
    app.config.update(MAIL)
    _add_due_subscription(app)
    response = _call(client)
    assert response.status_code == 502 and response.get_json() == {"sent": 0, "failed": 1}
