"""Account and subscription forms."""
from decimal import Decimal
from urllib.parse import urlsplit

from flask_wtf import FlaskForm
from wtforms import DateField, DecimalField, EmailField, PasswordField, SelectChoice, SelectField, StringField, URLField
from wtforms.validators import DataRequired, Email, EqualTo, InputRequired, Length, Optional, URL, ValidationError

from .constants import (
    BILLING_CYCLES,
    CATEGORIES,
    CURRENCIES,
    MAX_SUBSCRIPTION_PRICE,
    REMINDER_LEAD_TIMES,
    SUBSCRIPTION_TYPES,
    ZERO_DECIMAL_CURRENCIES,
)
from .services.timezones import time_zone_names


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


class EmailChangeForm(FlaskForm):
    email = EmailField(
        "Email address",
        filters=[normalize_email],
        validators=[InputRequired(), Length(max=254), Email()],
        description="Reminder emails are sent to this address. You also use it to log in.",
    )
    password = PasswordField("Current password", validators=[InputRequired(), Length(max=128)])


class PasswordChangeForm(FlaskForm):
    current_password = PasswordField("Current password", validators=[InputRequired(), Length(max=128)])
    new_password = PasswordField(
        "New password",
        validators=[InputRequired(), Length(min=12, max=128)],
        description="Use at least 12 characters.",
    )
    confirm_password = PasswordField(
        "Confirm new password",
        validators=[InputRequired(), Length(max=128), EqualTo("new_password", message="The passwords must match.")],
    )


def _strip(value):
    return value.strip() if value else value


class PreferencesForm(FlaskForm):
    time_zone = StringField(
        "Time zone",
        filters=[_strip],
        validators=[DataRequired(), Length(max=128)],
        description="Choose a city or region, such as Asia/Shanghai. Calendar and reminder dates use this time zone.",
    )
    reminder_days = SelectField(
        "Email reminders",
        choices=[
            SelectChoice("default", "Use app default"),
            *(SelectChoice(str(days), f"{days} {'day' if days == 1 else 'days'} before") for days in REMINDER_LEAD_TIMES),
            SelectChoice("0", "Off"),
        ],
        description="Applies to both renewals and free-trial endings.",
    )

    currency = SelectField(
        "Preferred currency",
        choices=[SelectChoice(code, f"{code} ({symbol})") for code, symbol in CURRENCIES.items()],
        description="Selected first when you add a subscription and shown first in totals. Amounts are never converted.",
    )

    def validate_time_zone(self, field):
        if field.data not in time_zone_names():
            raise ValidationError("Choose a time zone from the list.")


class SubscriptionForm(FlaskForm):
    name = StringField("Service name", filters=[_strip], validators=[DataRequired(), Length(max=120)])
    price = DecimalField(
        "Price per billing cycle",
        places=None,
        validators=[InputRequired()],
        description="For a free trial, enter its price after the trial or 0 if there is no charge.",
    )
    currency = SelectField(
        "Currency",
        choices=[SelectChoice(code, f"{code} ({symbol})") for code, symbol in CURRENCIES.items()],
    )
    billing_cycle = SelectField(
        "Billing cycle",
        choices=[SelectChoice(key, label) for key, (label, _) in BILLING_CYCLES.items()],
        default="monthly",
    )
    next_renewal_date = DateField("Next renewal or trial end date", validators=[InputRequired()])
    trial_start_date = DateField(
        "Trial start date (optional)",
        validators=[Optional()],
        description="For free trials only. Shows how long the trial runs.",
    )
    category = SelectField(
        "Category",
        choices=[SelectChoice(key, label) for key, (label, _) in CATEGORIES.items()],
        default="other",
    )
    subscription_type = SelectField(
        "Subscription type",
        choices=[SelectChoice(key, label) for key, label in SUBSCRIPTION_TYPES.items()],
    )
    cancellation_url = URLField(
        "Cancellation link (optional)",
        filters=[_strip],
        validators=[Optional(), Length(max=2048), URL()],
        description="Use the service’s official account-management page.",
    )

    def validate_price(self, field):
        price = field.data
        if price is None:
            return
        if not price.is_finite() or not 0 <= price <= MAX_SUBSCRIPTION_PRICE:
            raise ValidationError(f"Enter a price from 0 to {MAX_SUBSCRIPTION_PRICE:,}.")
        if self.currency.data in ZERO_DECIMAL_CURRENCIES:
            if price != price.to_integral_value():
                raise ValidationError(f"Enter a whole amount for {self.currency.data}.")
        elif price != price.quantize(Decimal("0.01")):
            raise ValidationError("Enter a price with up to two decimal places.")

    def validate_trial_start_date(self, field):
        # Ignored for paid subscriptions, so only check it for trials.
        if self.subscription_type.data == "paid" or field.data is None or self.next_renewal_date.data is None:
            return
        if field.data > self.next_renewal_date.data:
            raise ValidationError("The trial must start on or before the date it ends.")

    def validate_cancellation_url(self, field):
        try:
            url = urlsplit(field.data)
        except ValueError:
            raise ValidationError("Enter a valid cancellation link.") from None
        if url.scheme not in ("https", "http") or not url.hostname or url.username is not None:
            raise ValidationError("Enter an HTTP or HTTPS link without login credentials.")
