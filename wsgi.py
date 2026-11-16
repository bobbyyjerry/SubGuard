"""Entry point. `flask run` finds this file automatically, and production
servers (e.g. PythonAnywhere) import `app` from here."""
from app import create_app

app = create_app()
