"""Shared pytest fixtures.

A fixture is a helper pytest runs before a test. Every test that asks for
`client` gets a fresh app with an empty in-memory database.
"""
import pytest

from app import create_app
from app.extensions import db


@pytest.fixture
def app():
    app = create_app("testing")
    with app.app_context():
        db.create_all()
    yield app
    with app.app_context():
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()
