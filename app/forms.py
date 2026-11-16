"""Account forms and validation."""
from flask_wtf import FlaskForm
from wtforms import EmailField, PasswordField
from wtforms.validators import Email, EqualTo, InputRequired, Length


def normalize_email(value):
    return value.strip().lower() if value else value


class LoginForm(FlaskForm):
    email = EmailField(
        "Email address",
        filters=[normalize_email],
        validators=[InputRequired(), Length(max=254), Email()],
    )
    password = PasswordField("Password", validators=[InputRequired(), Length(max=128)])


class RegistrationForm(LoginForm):
    password = PasswordField(
        "Password",
        validators=[InputRequired(), Length(min=12, max=128)],
        description="Use at least 12 characters.",
    )
    confirm_password = PasswordField(
        "Confirm password",
        validators=[InputRequired(), Length(max=128), EqualTo("password", message="The passwords must match.")],
    )
