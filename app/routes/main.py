"""Public pages that don't need a login."""
from flask import Blueprint, jsonify, render_template

bp = Blueprint("main", __name__)


@bp.route("/")
def index():
    return render_template("main/index.html")


@bp.route("/health")
def health():
    """A tiny endpoint hosting platforms (and we) can use to check the app is up."""
    return jsonify(status="ok")
