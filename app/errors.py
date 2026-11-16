"""Friendly error pages instead of Flask's plain default ones."""
from flask import render_template

from .extensions import db


def register_error_handlers(app):
    @app.errorhandler(404)
    def not_found(error):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def server_error(error):
        # If a database operation failed half-way, undo it so the next request starts clean.
        db.session.rollback()
        return render_template("errors/500.html"), 500
