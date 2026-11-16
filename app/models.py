"""Database models for SubGuard."""
from datetime import date, datetime
from decimal import Decimal

from flask_login import UserMixin
from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db, login_manager


class UserPreferences(db.Model):
    __tablename__ = "user_preferences"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    time_zone: Mapped[str] = mapped_column(String(128))
    reminder_days: Mapped[int | None]


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    preferences: Mapped[UserPreferences | None] = relationship()

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Subscription(db.Model):
    __tablename__ = "subscriptions"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    price: Mapped[Decimal] = mapped_column(Numeric(9, 2))
    currency: Mapped[str] = mapped_column(String(3))
    billing_cycle: Mapped[str] = mapped_column(String(12))
    next_renewal_date: Mapped[date]
    category: Mapped[str] = mapped_column(String(20))
    subscription_type: Mapped[str] = mapped_column(String(20), default="paid")
    status: Mapped[str] = mapped_column(String(12), default="active")
    cancellation_url: Mapped[str | None] = mapped_column(String(2048))

    @classmethod
    def for_user(cls, user_id):
        return db.select(cls).filter_by(user_id=user_id).order_by(cls.next_renewal_date, cls.id)

    @classmethod
    def list_for_user(cls, user_id):
        return db.session.scalars(cls.for_user(user_id)).all()

    @property
    def is_trial(self):
        return self.subscription_type != "paid"

    @property
    def trial_end_date(self):
        return self.next_renewal_date if self.is_trial else None

    @property
    def converts_to_paid(self):
        return self.subscription_type == "trial_converts"


class ReminderDelivery(db.Model):
    __tablename__ = "reminder_deliveries"

    subscription_id: Mapped[int] = mapped_column(ForeignKey("subscriptions.id", ondelete="CASCADE"), primary_key=True)
    event_date: Mapped[date] = mapped_column(primary_key=True)
    claimed_at: Mapped[datetime]
    sent_at: Mapped[datetime | None]


@login_manager.user_loader
def load_user(user_id):
    try:
        return db.session.get(User, int(user_id))
    except ValueError:
        return None
