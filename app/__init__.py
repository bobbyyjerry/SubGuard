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


def create_app(config_name=None):
    config_name = config_name or os.environ.get("FLASK_CONFIG", "development")
    if config_name not in config_by_name:
        raise ValueError(
            f"Unknown FLASK_CONFIG '{config_name}'. "
            f"Use one of: {', '.join(config_by_name)}"
        )

    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_by_name[config_name])

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
    from .routes.auth import bp as auth_bp
    from .routes.dashboard import bp as dashboard_bp
    from .routes.main import bp as main_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(auth_bp)

    @app.cli.command("init-db")
    def init_db():
        """Create any missing database tables."""
        db.create_all()
        click.echo("Database tables are ready.")

    # Friendly 404 / 500 pages.
    from .errors import register_error_handlers

    register_error_handlers(app)

    return app
