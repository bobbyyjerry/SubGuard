"""The optional start date on free trials."""
from datetime import date, datetime, timezone

from app.extensions import db
from app.models import Subscription
from app.services import timezones

NOW = datetime(2026, 11, 16, 12, tzinfo=timezone.utc)


def _register(client, email="owner@example.com"):
    password = "a sample passphrase"
    response = client.post("/register", data={"email": email, "password": password, "confirm_password": password})
    assert response.status_code == 302


def _form(**overrides):
    return {
        "name": "Language trial", "price": "12.99", "currency": "USD", "billing_cycle": "monthly",
        "next_renewal_date": "2026-11-20", "category": "education", "subscription_type": "trial_converts",
        "trial_start_date": "2026-11-06", **overrides,
    }


def _saved(app):
    with app.app_context():
        return db.session.scalars(db.select(Subscription)).one()


def test_trial_start_date_is_saved_shown_and_editable(app, client, monkeypatch):
    monkeypatch.setattr(timezones, "utc_now", lambda: NOW)
    _register(client)

    assert b'name="trial_start_date"' in client.get("/subscriptions/new").data
    assert client.post("/subscriptions/new", data=_form()).status_code == 302
    saved = _saved(app)
    assert (saved.trial_start_date, saved.trial_length_days) == (date(2026, 11, 6), 14)

    for page in ("/subscriptions/", "/dashboard/"):
        html = " ".join(client.get(page).get_data(as_text=True).split())
        assert "Started 6 Nov 2026 · 14-day trial" in html

    edit_path = f"/subscriptions/{saved.id}/edit"
    assert b'value="2026-11-06"' in client.get(edit_path).data

    # The start date is optional: clearing it removes the line.
    assert client.post(edit_path, data=_form(trial_start_date="")).status_code == 302
    assert _saved(app).trial_start_date is None
    assert "Started" not in client.get("/subscriptions/").get_data(as_text=True)

    # A trial that starts and ends on the same day shows no length.
    assert client.post(edit_path, data=_form(trial_start_date="2026-11-20")).status_code == 302
    html = " ".join(client.get("/subscriptions/").get_data(as_text=True).split())
    assert "Started 20 Nov 2026" in html and "-day trial" not in html


def test_trial_start_date_must_not_be_after_the_end(app, client):
    _register(client)
    response = client.post("/subscriptions/new", data=_form(trial_start_date="2026-11-21"))
    assert response.status_code == 200
    assert b"The trial must start on or before the date it ends." in response.data
    assert b"Not a valid date value." in client.post("/subscriptions/new", data=_form(trial_start_date="soon")).data
    with app.app_context():
        assert db.session.scalars(db.select(Subscription)).first() is None


def test_paid_subscriptions_never_keep_a_trial_start_date(app, client, monkeypatch):
    monkeypatch.setattr(timezones, "utc_now", lambda: NOW)
    _register(client)

    # Sent with a paid subscription, even an impossible one, it is ignored rather than rejected.
    paid = _form(subscription_type="paid", trial_start_date="2027-01-01")
    assert client.post("/subscriptions/new", data=paid).status_code == 302
    saved = _saved(app)
    assert (saved.trial_start_date, saved.trial_length_days) == (None, None)

    edit_path = f"/subscriptions/{saved.id}/edit"
    assert client.post(edit_path, data=_form(subscription_type="trial_ends")).status_code == 302
    assert _saved(app).trial_start_date == date(2026, 11, 6)
    assert client.post(edit_path, data=_form(subscription_type="paid")).status_code == 302
    assert _saved(app).trial_start_date is None


def test_a_trial_that_became_paid_stops_showing_its_trial_dates(app, client, monkeypatch):
    clock = {"now": NOW}
    monkeypatch.setattr(timezones, "utc_now", lambda: clock["now"])
    _register(client)
    assert client.post("/subscriptions/new", data=_form()).status_code == 302

    clock["now"] = datetime(2026, 11, 25, 12, tzinfo=timezone.utc)
    html = " ".join(client.get("/subscriptions/").get_data(as_text=True).split())
    saved = _saved(app)
    assert (saved.subscription_type, saved.next_renewal_date) == ("paid", date(2026, 12, 20))
    assert saved.trial_length_days is None
    assert "Started 6 Nov 2026" not in html and "Renews 20 Dec 2026" in html


def test_init_db_adds_the_trial_start_column_to_an_older_database(app):
    with app.app_context():
        db.drop_all()
        with db.engine.begin() as connection:
            connection.execute(db.text(
                "CREATE TABLE subscriptions (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, "
                "name VARCHAR(120) NOT NULL, price NUMERIC(9, 2) NOT NULL, currency VARCHAR(3) NOT NULL, "
                "billing_cycle VARCHAR(12) NOT NULL, next_renewal_date DATE NOT NULL, billing_anchor_date DATE, "
                "category VARCHAR(20) NOT NULL, subscription_type VARCHAR(20) NOT NULL, status VARCHAR(12) NOT NULL, "
                "cancellation_url VARCHAR(2048))"
            ))
            connection.execute(db.text(
                "INSERT INTO subscriptions (user_id, name, price, currency, billing_cycle, next_renewal_date, "
                "category, subscription_type, status) VALUES (1, 'Old trial', 5, 'USD', 'monthly', '2026-11-20', "
                "'other', 'trial_ends', 'active')"
            ))

    runner = app.test_cli_runner()
    assert runner.invoke(args=["init-db"]).exit_code == 0
    assert runner.invoke(args=["init-db"]).exit_code == 0  # safe to run again

    with app.app_context():
        old = db.session.scalars(db.select(Subscription)).one()
        assert (old.name, old.trial_start_date, old.trial_length_days) == ("Old trial", None, None)
