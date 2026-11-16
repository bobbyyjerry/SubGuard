"""Smoke tests: does the app start and answer basic requests?"""
import pytest

from app import create_app


def test_home_page_loads(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"SubGuard" in response.data


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_unknown_page_returns_404(client):
    assert client.get("/does-not-exist").status_code == 404


def test_unknown_config_name_is_rejected():
    with pytest.raises(ValueError):
        create_app("nonsense")
