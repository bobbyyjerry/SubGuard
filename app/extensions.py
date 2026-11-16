"""Flask extension objects.

They are created here *without* an app, then attached to the app inside
create_app(). This avoids circular imports: models and routes can import
`db` from here without importing the app itself.
"""
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect

db = SQLAlchemy()
csrf = CSRFProtect()

# Flask-Login's LoginManager is added on Day 3, together with the User model.
