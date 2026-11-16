"""Verify account creation, sign-in, and session protection."""
import re

from app.extensions import db
from app.models import User


PASSWORD = "a sample passphrase"


def _registration_data(email="reader@example.com"):
    return {"email": email, "password": PASSWORD, "confirm_password": PASSWORD}


def _csrf_token(response):
    match = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', response.get_data(as_text=True))
    assert match is not None
    return match[1]


def test_account_lifecycle_with_csrf_enabled(app, client):
    app.config["WTF_CSRF_ENABLED"] = True
    registration = _registration_data(" Reader@Example.com ")
    assert client.post("/register", data=registration).status_code == 400
    registration["csrf_token"] = _csrf_token(client.get("/register"))
    response = client.post("/register", data=registration, follow_redirects=True)
    assert response.request.path == "/dashboard/"
    assert b"Your account has been created." in response.data
    assert b"reader@example.com" in response.data

    with app.app_context():
        user = db.session.scalars(db.select(User)).one()
        assert user.email == "reader@example.com"
        assert user.password_hash != PASSWORD
        assert user.check_password(PASSWORD)

    assert client.get("/logout").status_code == 405
    assert client.post("/logout").status_code == 400
    response = client.post("/logout", data={"csrf_token": _csrf_token(response)}, follow_redirects=True)
    assert response.request.path == "/"
    assert b"reader@example.com" not in response.data
    assert b'href="/login"' in response.data

    login_data = {"email": "READER@example.com", "password": PASSWORD}
    assert client.post("/login", data=login_data).status_code == 400
    login_data["csrf_token"] = _csrf_token(client.get("/login"))
    response = client.post("/login", data=login_data, follow_redirects=True)
    assert response.request.path == "/dashboard/"
    assert b"reader@example.com" in response.data


def test_registration_rejects_duplicate_normalized_email(app, client):
    assert client.post("/register", data=_registration_data()).status_code == 302

    other_client = app.test_client()
    response = other_client.post("/register", data=_registration_data("READER@EXAMPLE.COM"))
    assert b"An account already uses this email address." in response.data
    assert b'href="/login"' in response.data
    with app.app_context():
        assert db.session.scalars(db.select(User)).one().email == "reader@example.com"


def test_registration_rejects_mismatched_passwords(app, client):
    response = client.post("/register", data={**_registration_data(), "confirm_password": "other password"})
    assert b"The passwords must match." in response.data
    with app.app_context():
        assert db.session.scalars(db.select(User)).first() is None


def test_bad_credentials_leave_user_signed_out(app, client):
    assert client.post("/register", data=_registration_data()).status_code == 302

    other_client = app.test_client()
    for email in ("reader@example.com", "missing@example.com"):
        response = other_client.post("/login", data={"email": email, "password": "wrong password"})
        assert b"The email address or password is incorrect." in response.data
        assert b'href="/login"' in response.data
