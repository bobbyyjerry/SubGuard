"""Security headers, the failed-login limit, cookie settings and database clean-up."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app import create_app
from app.extensions import db
from app.models import ReminderDelivery, Subscription, User, UserPreferences
from app.security import LoginThrottle
from app.services import mail, reminders

PASSWORD = "a sample passphrase"
NOW = datetime(2026, 11, 16, 12, tzinfo=timezone.utc)
SETTINGS = mail.MailSettings("127.0.0.1", 1025, "none", "SubGuard <reminders@example.com>")


def _register(client, email="owner@example.com"):
    response = client.post("/register", data={"email": email, "password": PASSWORD, "confirm_password": PASSWORD})
    assert response.status_code == 302


def _login(client, password, email="owner@example.com"):
    return client.post("/login", data={"email": email, "password": password})


# ---------- Security headers ----------

@pytest.mark.parametrize("path", ["/", "/login", "/dashboard/", "/no-such-page", "/static/js/app.js"])
def test_every_response_has_security_headers(client, path):
    headers = client.get(path).headers
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    policy = headers["Content-Security-Policy"]
    assert "default-src 'self'" in policy and "frame-ancestors 'none'" in policy and "object-src 'none'" in policy
    # Scripts may only come from the site itself and the CDN: never from inside a page.
    script_rule = next(rule for rule in policy.split("; ") if rule.startswith("script-src"))
    assert script_rule == "script-src 'self' https://cdn.jsdelivr.net"
    # HTTPS-only is announced in production, not on local http://localhost.
    assert "Strict-Transport-Security" not in headers


def test_pages_only_load_scripts_the_policy_allows(app, client):
    import re

    _register(client)
    for path in ("/", "/dashboard/", "/subscriptions/", "/subscriptions/new", "/analytics/", "/calendar/", "/settings/"):
        html = client.get(path).get_data(as_text=True)
        for tag in re.findall(r"<script\b[^>]*>", html):
            source = re.search(r'src="([^"]+)"', tag)
            if source is None:
                assert 'type="application/json"' in tag, (path, tag)  # data only, never run
            else:
                assert source[1].startswith(("/static/", "https://cdn.jsdelivr.net/")), (path, tag)
        assert not re.search(r"\son[a-z]+=", html), path  # no inline event handlers


def test_production_uses_secure_cookies_and_refuses_example_keys(monkeypatch):
    from app import config

    monkeypatch.setattr(config.ProductionConfig, "SECRET_KEY", "change-me-to-a-long-random-string")
    with pytest.raises(RuntimeError, match="example value"):
        create_app("production")

    monkeypatch.setattr(config.ProductionConfig, "SECRET_KEY", "a-long-random-value-made-for-this-test")
    monkeypatch.setattr(config.ProductionConfig, "SQLALCHEMY_DATABASE_URI", "sqlite:///:memory:")
    production = create_app("production")
    assert not production.debug
    assert production.config["SESSION_COOKIE_SECURE"] and production.config["SESSION_COOKIE_HTTPONLY"]
    assert production.config["SESSION_COOKIE_SAMESITE"] == "Lax"
    response = production.test_client().get("/login")
    assert response.headers["Strict-Transport-Security"].startswith("max-age=31536000")


def test_session_cookie_is_http_only_and_same_site(app, client):
    assert app.config["MAX_CONTENT_LENGTH"] == 1024 * 1024
    response = client.post("/register", data={"email": "owner@example.com", "password": PASSWORD, "confirm_password": PASSWORD})
    cookie = next(value for name, value in response.headers if name == "Set-Cookie" and value.startswith("session="))
    assert "HttpOnly" in cookie and "SameSite=Lax" in cookie
    assert app.test_client().post("/login", data={"email": "x" * (1024 * 1024 + 1)}).status_code == 413


# ---------- Failed-login limit ----------

def test_login_is_blocked_after_five_wrong_passwords(app, client):
    clock = {"now": 1000.0}
    app.extensions["login_throttle"] = LoginThrottle(clock=lambda: clock["now"])
    _register(client)
    client.post("/logout")

    for _ in range(5):
        response = _login(client, "the wrong passphrase")
        assert response.status_code == 200 and b"The email address or password is incorrect." in response.data

    # Now even the right password is refused, and nothing says whether it was right.
    blocked = _login(client, PASSWORD)
    assert blocked.status_code == 429 and b"Too many failed attempts." in blocked.data
    assert client.get("/settings/").location.startswith("/login?")

    # Other accounts can still sign in.
    other = app.test_client()
    _register(other, "other@example.com")
    other.post("/logout")
    assert _login(other, PASSWORD, "other@example.com").status_code == 302

    # After 15 minutes the block lifts.
    clock["now"] += 15 * 60 + 1
    assert _login(client, PASSWORD).status_code == 302


def test_a_successful_login_clears_the_count_and_unknown_emails_are_limited_too(app, client):
    _register(client)
    client.post("/logout")
    for _ in range(4):
        _login(client, "the wrong passphrase")
    assert _login(client, PASSWORD).status_code == 302
    client.post("/logout")
    for _ in range(4):
        assert _login(client, "the wrong passphrase").status_code == 200
    assert _login(client, PASSWORD).status_code == 302

    # An address with no account gets the same message and the same limit.
    stranger = app.test_client()
    for _ in range(5):
        response = _login(stranger, "anything at all", "nobody@example.com")
        assert response.status_code == 200 and b"The email address or password is incorrect." in response.data
    assert _login(stranger, "anything at all", "nobody@example.com").status_code == 429


def test_throttle_forgets_old_failures_and_stays_bounded():
    clock = {"now": 0.0}
    throttle = LoginThrottle(clock=lambda: clock["now"])
    for _ in range(4):
        throttle.record_failure("a")
    clock["now"] = 14 * 60
    throttle.record_failure("a")
    assert throttle.is_blocked("a")
    clock["now"] = 15 * 60 + 1  # the first four are now too old to count
    assert not throttle.is_blocked("a")

    throttle.MAX_TRACKED = 3
    for key in ("b", "c", "d", "e"):
        throttle.record_failure(key)
    assert len(throttle._failures) <= 3


# ---------- Database clean-up ----------

def _subscription(owner_id, name, renewal):
    return Subscription(
        user_id=owner_id, name=name, price=Decimal("9.99"), currency="USD", billing_cycle="monthly",
        category="other", next_renewal_date=renewal,
    )


def test_deleting_a_subscription_removes_its_reminder_records(app, client, monkeypatch):
    monkeypatch.setattr(reminders, "deliver", lambda settings, message: None)
    _register(client)
    with app.app_context():
        owner = db.session.scalar(db.select(User.id))
        kept = _subscription(owner, "Kept", NOW.date() + timedelta(days=2))
        removed = _subscription(owner, "Removed", NOW.date() + timedelta(days=2))
        db.session.add_all([kept, removed])
        db.session.commit()
        assert reminders.send_due_reminders(SETTINGS, 3, now=NOW) == (2, 0)
        kept_id, removed_id = kept.id, removed.id

    assert client.post(f"/subscriptions/{removed_id}/delete").status_code == 302
    with app.app_context():
        assert db.session.scalars(db.select(ReminderDelivery.subscription_id)).all() == [kept_id]


def test_deleting_an_account_removes_everything_it_owned(app):
    with app.app_context():
        leaving = User(email="leaving@example.com", password_hash="unused")
        staying = User(email="staying@example.com", password_hash="unused")
        db.session.add_all([leaving, staying])
        db.session.flush()
        db.session.add_all([
            UserPreferences(user_id=leaving.id, time_zone="UTC", reminder_days=None),
            UserPreferences(user_id=staying.id, time_zone="UTC", reminder_days=None),
        ])
        gone = _subscription(leaving.id, "Gone", date(2030, 1, 1))
        kept = _subscription(staying.id, "Kept", date(2030, 1, 1))
        db.session.add_all([gone, kept])
        db.session.flush()
        for subscription in (gone, kept):
            db.session.add(ReminderDelivery(
                subscription_id=subscription.id, event_date=date(2030, 1, 1), claimed_at=NOW,
            ))
        db.session.commit()
        staying_id, kept_id = staying.id, kept.id

        db.session.delete(leaving)
        db.session.commit()

        assert db.session.scalars(db.select(User.email)).all() == ["staying@example.com"]
        assert db.session.scalars(db.select(UserPreferences.user_id)).all() == [staying_id]
        assert db.session.scalars(db.select(Subscription.name)).all() == ["Kept"]
        assert db.session.scalars(db.select(ReminderDelivery.subscription_id)).all() == [kept_id]


def test_rows_cannot_point_at_a_missing_owner(app):
    from sqlalchemy.exc import IntegrityError

    with app.app_context():
        db.session.add(_subscription(999, "Nobody's", date(2030, 1, 1)))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_init_db_removes_leftover_reminder_records(app):
    with app.app_context():
        owner = User(email="owner@example.com", password_hash="unused")
        db.session.add(owner)
        db.session.flush()
        kept = _subscription(owner.id, "Kept", date(2030, 1, 1))
        db.session.add(kept)
        db.session.flush()
        db.session.add(ReminderDelivery(subscription_id=kept.id, event_date=date(2030, 1, 1), claimed_at=NOW))
        db.session.commit()
        kept_id = kept.id
        # A leftover from before foreign keys were switched on.
        with db.engine.connect() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            connection.execute(db.text(
                "INSERT INTO reminder_deliveries (subscription_id, event_date, claimed_at) "
                "VALUES (4242, '2030-01-01', '2026-11-16 12:00:00')"
            ))
            connection.commit()
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")

    assert app.test_cli_runner().invoke(args=["init-db"]).exit_code == 0
    with app.app_context():
        assert db.session.scalars(db.select(ReminderDelivery.subscription_id)).all() == [kept_id]


# ---------- Cancellation link in reminder emails ----------

def test_reminder_email_includes_the_saved_cancellation_link(app, monkeypatch):
    delivered = []
    monkeypatch.setattr(reminders, "deliver", lambda settings, message: delivered.append(message))
    with app.app_context():
        owner = User(email="owner@example.com", password_hash="unused")
        db.session.add(owner)
        db.session.flush()
        with_link = _subscription(owner.id, "With link", NOW.date() + timedelta(days=2))
        with_link.cancellation_url = "https://example.com/account/cancel?plan=1"
        db.session.add_all([with_link, _subscription(owner.id, "Without link", NOW.date() + timedelta(days=3))])
        db.session.commit()
        assert reminders.send_due_reminders(SETTINGS, 3, now=NOW) == (2, 0)

    first, second = (message.get_content() for message in delivered)
    assert "To cancel, use the link you saved: https://example.com/account/cancel?plan=1" in first
    assert "To cancel" not in second and "https://" not in second
    for body in (first, second):
        assert body.endswith("Open SubGuard to review the subscription details.\n")
