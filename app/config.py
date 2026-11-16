"""Configuration for SubGuard.

All secrets come from environment variables. In development they are loaded
from the .env file in the project root; in production the hosting platform
provides them. Nothing secret is ever written in this file.
"""
import os

from dotenv import load_dotenv

# Project root = the folder that contains the "app" package.
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
load_dotenv(os.path.join(BASE_DIR, ".env"))


class Config:
    """Settings shared by every environment."""

    SECRET_KEY = os.environ.get("SECRET_KEY")
    # None means "use instance/subguard.db" (worked out in create_app).
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = True
    MAIL_SERVER = os.environ.get("MAIL_SERVER")
    MAIL_PORT = os.environ.get("MAIL_PORT")
    MAIL_SECURITY = os.environ.get("MAIL_SECURITY", "starttls")
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER")
    REMINDER_DAYS = os.environ.get("REMINDER_DAYS", "3")


class DevelopmentConfig(Config):
    DEBUG = True


class TestingConfig(Config):
    TESTING = True
    SECRET_KEY = "test-secret-key"  # a fake key, only used by pytest
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"  # throwaway in-memory database
    WTF_CSRF_ENABLED = False  # lets tests submit forms without a token


class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True  # cookies only sent over HTTPS
    SESSION_COOKIE_HTTPONLY = True  # JavaScript can't read the session cookie
    SESSION_COOKIE_SAMESITE = "Lax"


config_by_name = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}
