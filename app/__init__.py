"""The SubGuard application package.

create_app() is an "application factory": a function that builds and returns
a configured Flask app. Tests call it with "testing", the dev server and the
production server call it with their own settings.
"""
import os
from pathlib import Path

import click
from flask import Flask

from .config import config_by_name
from .extensions import csrf, db, login_manager


# Example values that must never protect a live site.
PLACEHOLDER_SECRET_KEYS = {"change-me-to-a-long-random-string", "test-secret-key"}


def create_app(config_name=None):
    config_name = config_name or os.environ.get("FLASK_CONFIG", "development")
    if config_name not in config_by_name:
        raise ValueError(
            f"Unknown FLASK_CONFIG '{config_name}'. "
            f"Use one of: {', '.join(config_by_name)}"
        )

    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_by_name[config_name])

    if config_name == "production" and app.config.get("SECRET_KEY") in PLACEHOLDER_SECRET_KEYS:
        raise RuntimeError("SECRET_KEY is still the example value. Generate a new one for production.")
    if not app.config.get("SECRET_KEY"):
        raise RuntimeError(
            "SECRET_KEY is not set. Copy .env.example to .env and set SECRET_KEY."
        )

    # The instance/ folder holds local data such as the SQLite file.
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    if not app.config.get("SQLALCHEMY_DATABASE_URI"):
        db_file = Path(app.instance_path) / "subguard.db"
        app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_file.as_posix()}"

    # Attach extensions to this app.
    db.init_app(app)
    csrf.init_app(app)
    login_manager.init_app(app)

    # Template filters (money, dates) and shared constants.
    from .template_helpers import register_template_helpers

    register_template_helpers(app)

    # Register blueprints (groups of routes).
    from .routes.analytics import bp as analytics_bp
    from .routes.auth import bp as auth_bp
    from .routes.calendar import bp as calendar_bp
    from .routes.dashboard import bp as dashboard_bp
    from .routes.main import bp as main_bp
    from .routes.settings import bp as settings_bp
    from .routes.subscriptions import bp as subscriptions_bp
    from .routes.tasks import bp as tasks_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(subscriptions_bp)
    app.register_blueprint(analytics_bp)
    app.register_blueprint(calendar_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(tasks_bp)

    from .reminder_cli import reminders_command

    app.cli.add_command(reminders_command)

    @app.cli.command("init-db")
    def init_db():
        """Create any missing database tables and columns."""
        db.create_all()
        # create_all() never changes existing tables, so add newer columns here.
        newer_columns = (
            ("subscriptions", "billing_anchor_date", "DATE"),
            ("subscriptions", "trial_start_date", "DATE"),
            ("user_preferences", "currency", "VARCHAR(3)"),
        )
        for table, name, column_type in newer_columns:
            existing = {column["name"] for column in db.inspect(db.engine).get_columns(table)}
            if name not in existing:
                with db.engine.begin() as connection:
                    connection.execute(db.text(f"ALTER TABLE {table} ADD COLUMN {name} {column_type}"))
        # Older databases can hold reminder records for subscriptions that were deleted.
        with db.engine.begin() as connection:
            connection.execute(db.text(
                "DELETE FROM reminder_deliveries WHERE subscription_id NOT IN (SELECT id FROM subscriptions)"
            ))
        click.echo("Database tables are ready.")

    # Security headers on every response and the failed-login limit.
    from .security import register_security

    register_security(app)

    # Friendly 404 / 500 pages.
    from .errors import register_error_handlers

    register_error_handlers(app)

    return app
