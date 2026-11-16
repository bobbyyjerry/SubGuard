"""Subscription lifecycle, ownership, and form validation."""
import re
from decimal import Decimal

from app.extensions import db
from app.models import Subscription, User


def _register(client, email):
    password = "a sample passphrase"
    response = client.post("/register", data={"email": email, "password": password, "confirm_password": password})
    assert response.status_code == 302


def _subscription_data(**overrides):
    return {
        "name": "Private streaming subscription",
        "price": "7.95",
        "currency": "USD",
        "billing_cycle": "monthly",
        "next_renewal_date": "2030-02-15",
        "category": "streaming",
        "subscription_type": "paid",
        "cancellation_url": "https://example.com/account",
        **overrides,
    }


def _saved_subscription_id(app):
    with app.app_context():
        return db.session.scalars(db.select(Subscription.id)).one()


def test_subscription_lifecycle_with_csrf(app, client):
    _register(client, "owner@example.com")
    assert b"No subscriptions yet" in client.get("/subscriptions/").data
    app.config["WTF_CSRF_ENABLED"] = True
    add_page = client.get("/subscriptions/new")
    assert add_page.status_code == 200
    match = re.search(rb'name="csrf_token"[^>]*value="([^"]+)"', add_page.data)
    assert match is not None
    token = {"csrf_token": match[1].decode()}

    assert client.post("/subscriptions/new", data=_subscription_data()).status_code == 400
    response = client.post("/subscriptions/new", data={**_subscription_data(), **token}, follow_redirects=True)
    assert response.request.path == "/subscriptions/"
    assert b"Private streaming subscription" in response.data
    assert b"$7.95" in response.data
    assert b'https://example.com/account' in response.data

    subscription_id = _saved_subscription_id(app)
    path = f"/subscriptions/{subscription_id}"
    edit_page = client.get(f"{path}/edit")
    assert b'value="Private streaming subscription"' in edit_page.data
    assert b'value="2030-02-15"' in edit_page.data

    updated = _subscription_data(name="Annual trial", price="59.99", billing_cycle="yearly", subscription_type="trial_converts")
    assert client.post(f"{path}/edit", data=updated).status_code == 400
    response = client.post(f"{path}/edit", data={**updated, **token}, follow_redirects=True)
    assert b"Annual trial" in response.data
    assert b"Then converts to paid" in response.data
    assert b"Trial ends 15 Feb 2030" in response.data

    assert client.get(f"{path}/status").status_code == 405
    assert client.post(f"{path}/status", data={"status": "paused"}).status_code == 400
    for _ in range(2):
        response = client.post(f"{path}/status", data={"status": "paused", **token}, follow_redirects=True)
        assert b"Resume tracking" in response.data
        assert b">Paused</span>" in response.data
    response = client.post(f"{path}/status", data={"status": "active", **token}, follow_redirects=True)
    assert b"Pause tracking" in response.data
    assert b">Paused</span>" not in response.data

    assert client.get(f"{path}/delete").status_code == 405
    assert client.post(f"{path}/delete").status_code == 400
    response = client.post(f"{path}/delete", data=token, follow_redirects=True)
    assert b"No subscriptions yet" in response.data
    assert client.post("/subscriptions/new", data={**_subscription_data(), **token}).status_code == 302
    assert _saved_subscription_id(app) != subscription_id
    assert client.post(f"{path}/delete", data=token).status_code == 404


def test_subscriptions_require_login_and_are_private(app, client):
    assert client.get("/subscriptions/").location.startswith("/login?")
    assert client.get("/subscriptions/new").location.startswith("/login?")
    _register(client, "owner@example.com")
    other_client = app.test_client()
    _register(other_client, "other@example.com")
    with app.app_context():
        other_id = db.session.scalar(db.select(User.id).filter_by(email="other@example.com"))

    response = client.post("/subscriptions/new", data=_subscription_data(user_id=other_id, status="paused"))
    assert response.status_code == 302
    subscription_id = _saved_subscription_id(app)
    path = f"/subscriptions/{subscription_id}"

    assert b"Private streaming subscription" not in other_client.get("/subscriptions/").data
    assert other_client.get(f"{path}/edit").status_code == 404
    assert other_client.post(f"{path}/edit", data=_subscription_data(name="Other user edit")).status_code == 404
    assert other_client.post(f"{path}/status", data={"status": "paused"}).status_code == 404
    assert other_client.post(f"{path}/delete").status_code == 404
    assert b"Private streaming subscription" in client.get("/subscriptions/").data

    with app.app_context():
        subscription = db.session.get(Subscription, subscription_id)
        assert subscription.user_id != other_id
        assert subscription.status == "active"
        assert subscription.price == Decimal("7.95")


def test_subscription_form_rejects_invalid_input(app, client):
    _register(client, "owner@example.com")
    cases = [
        ({"name": "   "}, b"This field is required."),
        ({"price": "NaN"}, b"Enter a price from 0"),
        ({"price": "-1"}, b"Enter a price from 0"),
        ({"price": "1.001"}, b"Enter a price with up to two decimal places."),
        ({"price": "1.5", "currency": "JPY"}, b"Enter a whole amount for JPY."),
        ({"billing_cycle": "daily"}, b"Not a valid choice."),
        ({"next_renewal_date": "2030-02-30"}, b"Not a valid date value."),
        ({"cancellation_url": "javascript://example.com"}, b"Enter an HTTP or HTTPS link"),
    ]
    for overrides, error in cases:
        response = client.post("/subscriptions/new", data=_subscription_data(**overrides))
        assert response.status_code == 200, overrides
        assert error in response.data, overrides

    with app.app_context():
        assert db.session.scalar(db.select(Subscription.id)) is None
