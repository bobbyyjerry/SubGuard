"""Changing the email address, password and preferred currency in Settings."""
import re
from datetime import date
from decimal import Decimal

from app.extensions import db
from app.models import Subscription, User, UserPreferences

PASSWORD = "a sample passphrase"
NEW_PASSWORD = "another sample passphrase"


def _register(client, email):
    response = client.post("/register", data={"email": email, "password": PASSWORD, "confirm_password": PASSWORD})
    assert response.status_code == 302


def _user(app, email):
    with app.app_context():
        return db.session.scalar(db.select(User).filter_by(email=email))


def _add(app, email, name, price, currency, renewal=date(2030, 1, 1)):
    with app.app_context():
        owner = db.session.scalar(db.select(User.id).filter_by(email=email))
        db.session.add(Subscription(
            user_id=owner, name=name, price=Decimal(price), currency=currency, billing_cycle="monthly",
            category="other", next_renewal_date=renewal,
        ))
        db.session.commit()


def test_account_forms_need_login_and_a_csrf_token(app, client):
    for path in ("/settings/email", "/settings/password"):
        assert client.post(path, data={}).location.startswith("/login?")
        assert client.get(path).status_code == 405
    _register(client, "owner@example.com")
    app.config["WTF_CSRF_ENABLED"] = True
    assert client.post("/settings/email", data={"email": "new@example.com", "password": PASSWORD}).status_code == 400
    change = {"current_password": PASSWORD, "new_password": NEW_PASSWORD, "confirm_password": NEW_PASSWORD}
    assert client.post("/settings/password", data=change).status_code == 400
    assert _user(app, "owner@example.com").check_password(PASSWORD)


def test_change_email(app, client):
    _register(client, "owner@example.com")
    _register(app.test_client(), "taken@example.com")

    page = client.get("/settings/").get_data(as_text=True)
    assert re.search(r'<input [^>]*name="email"[^>]*value="owner@example.com"', page)

    def submit(email, password=PASSWORD):
        return client.post("/settings/email", data={"email": email, "password": password}, follow_redirects=True).get_data(as_text=True)

    assert "The current password is incorrect." in submit("new@example.com", "the wrong passphrase")
    assert "This is already your email address." in submit("Owner@Example.com ")
    assert "An account already uses this email address." in submit("taken@example.com")
    assert "Invalid email address." in submit("not-an-email")
    assert _user(app, "owner@example.com") is not None

    # A failed email change leaves the other forms showing the saved values.
    failed = submit("taken@example.com")
    assert re.search(r'<input [^>]*name="time_zone"[^>]*value="UTC"', failed)
    assert re.search(r'<input [^>]*name="email"[^>]*value="taken@example.com"', failed)

    saved = submit(" New@Example.com")
    assert "Email address updated." in saved
    assert re.search(r'<input [^>]*name="email"[^>]*value="new@example.com"', saved)
    assert _user(app, "owner@example.com") is None
    assert _user(app, "new@example.com").check_password(PASSWORD)

    # Still signed in, and the new address is the one that logs in.
    assert client.get("/dashboard/").status_code == 200
    client.post("/logout")
    assert client.post("/login", data={"email": "owner@example.com", "password": PASSWORD}).status_code == 200
    assert client.post("/login", data={"email": "new@example.com", "password": PASSWORD}).status_code == 302


def test_change_password_signs_out_other_devices(app, client):
    _register(client, "owner@example.com")
    other_device = app.test_client()
    assert other_device.post("/login", data={"email": "owner@example.com", "password": PASSWORD}).status_code == 302
    bystander = app.test_client()
    _register(bystander, "bystander@example.com")

    def submit(current, new, confirm=None):
        data = {"current_password": current, "new_password": new, "confirm_password": new if confirm is None else confirm}
        return client.post("/settings/password", data=data, follow_redirects=True).get_data(as_text=True)

    assert "The current password is incorrect." in submit("the wrong passphrase", NEW_PASSWORD)
    assert "Field must be between 12 and 128 characters long." in submit(PASSWORD, "too short")
    assert "The passwords must match." in submit(PASSWORD, NEW_PASSWORD, "something different")
    assert "Choose a password you are not already using." in submit(PASSWORD, PASSWORD)
    assert _user(app, "owner@example.com").check_password(PASSWORD)
    assert other_device.get("/settings/").status_code == 200

    failed = submit("the wrong passphrase", NEW_PASSWORD)
    # Passwords are never sent back to the page.
    assert NEW_PASSWORD not in failed and "the wrong passphrase" not in failed

    changed = submit(PASSWORD, NEW_PASSWORD)
    assert "Password changed. Other devices have been signed out." in changed
    owner = _user(app, "owner@example.com")
    assert owner.check_password(NEW_PASSWORD) and not owner.check_password(PASSWORD)
    assert NEW_PASSWORD not in owner.password_hash

    # This browser stays signed in, the other device does not, other accounts are untouched.
    assert client.get("/settings/").status_code == 200
    assert other_device.get("/settings/").location.startswith("/login?")
    assert bystander.get("/settings/").status_code == 200
    assert _user(app, "bystander@example.com").check_password(PASSWORD)

    client.post("/logout")
    assert client.post("/login", data={"email": "owner@example.com", "password": PASSWORD}).status_code == 200
    assert client.post("/login", data={"email": "owner@example.com", "password": NEW_PASSWORD}).status_code == 302


def test_a_tampered_or_old_style_session_is_not_signed_in(app, client):
    _register(client, "owner@example.com")
    owner_id = _user(app, "owner@example.com").id
    for forged in (str(owner_id), f"{owner_id}:", f"{owner_id}:0000000000000000", "abc:def"):
        with client.session_transaction() as session:
            session["_user_id"] = forged
        assert client.get("/settings/").location.startswith("/login?")


def test_preferred_currency_is_saved_and_used(app, client):
    _register(client, "owner@example.com")
    other = app.test_client()
    _register(other, "other@example.com")
    _add(app, "owner@example.com", "Dollar music", "10.00", "USD", date(2030, 1, 1))
    _add(app, "owner@example.com", "Euro gym", "30.00", "EUR", date(2030, 2, 1))

    # Before a choice is made: USD is selected and totals keep their usual order.
    assert re.search(r'<option [^>]*selected[^>]*value="USD"', client.get("/settings/").get_data(as_text=True))
    assert "$10.00 + €30.00" in client.get("/dashboard/").get_data(as_text=True)

    settings = {"time_zone": "UTC", "reminder_days": "default"}
    invalid = client.post("/settings/", data={**settings, "currency": "XXX"})
    assert b"Not a valid choice." in invalid.data
    saved = client.post("/settings/", data={**settings, "currency": "EUR"}, follow_redirects=True).get_data(as_text=True)
    assert "Settings saved." in saved
    assert re.search(r'<option [^>]*selected[^>]*value="EUR"', saved)
    with app.app_context():
        assert db.session.scalars(db.select(UserPreferences.currency)).all() == ["EUR"]

    # Shown first on the dashboard; each currency keeps its own total (nothing is converted).
    dashboard = client.get("/dashboard/").get_data(as_text=True)
    assert "€30.00 + $10.00" in dashboard and "€360.00 + $120.00" in dashboard
    # Opened first on Analytics, and selected on the new-subscription form.
    assert re.search(r'href="/analytics/\?currency=EUR"\s+aria-current="page"', client.get("/analytics/").get_data(as_text=True))
    assert re.search(r'<option [^>]*selected[^>]*value="EUR"', client.get("/subscriptions/new").get_data(as_text=True))
    # A link to another currency still works.
    assert re.search(r'href="/analytics/\?currency=USD"\s+aria-current="page"',
                     client.get("/analytics/?currency=USD").get_data(as_text=True))

    # The other account is unaffected.
    assert not re.search(r'<option [^>]*selected[^>]*value="EUR"', other.get("/subscriptions/new").get_data(as_text=True))

    # A preferred currency with no subscriptions falls back without errors.
    assert client.post("/settings/", data={**settings, "currency": "JPY"}).status_code == 302
    assert "$10.00 + €30.00" in client.get("/dashboard/").get_data(as_text=True)
    assert re.search(r'href="/analytics/\?currency=USD"\s+aria-current="page"', client.get("/analytics/").get_data(as_text=True))


def test_init_db_adds_the_currency_column_to_an_older_database(app):
    with app.app_context():
        db.drop_all()
        with db.engine.begin() as connection:
            connection.execute(db.text(
                "CREATE TABLE user_preferences (user_id INTEGER PRIMARY KEY, time_zone VARCHAR(128) NOT NULL, "
                "reminder_days INTEGER)"
            ))
            connection.execute(db.text("INSERT INTO user_preferences VALUES (1, 'Asia/Shanghai', 7)"))

    runner = app.test_cli_runner()
    assert runner.invoke(args=["init-db"]).exit_code == 0
    assert runner.invoke(args=["init-db"]).exit_code == 0  # safe to run again

    with app.app_context():
        old = db.session.scalars(db.select(UserPreferences)).one()
        assert (old.time_zone, old.reminder_days, old.currency) == ("Asia/Shanghai", 7, None)
