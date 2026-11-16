"""Find upcoming events and send at most one reminder per saved date."""
from datetime import date, datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import format_datetime, make_msgid

from flask import current_app
from sqlalchemy.exc import IntegrityError

from ..extensions import db
from ..models import ReminderDelivery, Subscription, User
from ..template_helpers import cycle_suffix, money, nice_date
from .mail import MailRejected, MailUnconfirmed, deliver


def _message(subscription, email, sender):
    event_date = nice_date(subscription.next_renewal_date)
    amount = money(subscription.price, subscription.currency)
    message = EmailMessage()
    message["From"] = sender
    message["To"] = email
    message["Date"] = format_datetime(datetime.now(timezone.utc))
    message["Message-ID"] = make_msgid(domain=message["From"].addresses[0].domain)

    if subscription.is_trial:
        message["Subject"] = "SubGuard reminder: free trial ending"
        event = f"Your free trial for {subscription.name} ends on {event_date}."
        if subscription.converts_to_paid:
            charge = f"Expected price after the trial: {amount}{cycle_suffix(subscription.billing_cycle)}."
        else:
            charge = "This trial is recorded as ending without a charge."
    else:
        message["Subject"] = "SubGuard reminder: subscription renewal"
        event = f"{subscription.name} renews on {event_date}."
        charge = f"Expected charge: {amount}."

    message.set_content(f"{event}\n{charge}\n\nOpen SubGuard to review the subscription details.\n")
    return message


def _claim(subscription_id, event_date):
    eligible = db.select(
        Subscription.id, Subscription.next_renewal_date, db.literal(datetime.now(timezone.utc)),
    ).where(
        Subscription.id == subscription_id,
        Subscription.next_renewal_date == event_date,
        Subscription.status == "active",
    )
    claim = db.insert(ReminderDelivery).from_select(
        ["subscription_id", "event_date", "claimed_at"], eligible,
    )
    try:
        result = db.session.execute(claim)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        if db.session.get(ReminderDelivery, (subscription_id, event_date)) is None:
            raise
        return False
    return result.rowcount == 1


def send_due_reminders(settings, lead_days, *, today=None):
    """Check dates one to lead_days days away and return sent and failed counts."""
    today = today or date.today()
    already_claimed = db.select(ReminderDelivery.subscription_id).where(
        ReminderDelivery.subscription_id == Subscription.id,
        ReminderDelivery.event_date == Subscription.next_renewal_date,
    ).exists()
    upcoming = (
        db.select(Subscription, User.email)
        .join(User, User.id == Subscription.user_id)
        .where(
            Subscription.status == "active",
            Subscription.next_renewal_date.between(today + timedelta(days=1), today + timedelta(days=lead_days)),
            ~already_claimed,
        )
        .order_by(Subscription.next_renewal_date, Subscription.id)
    )
    messages = [
        (subscription.id, subscription.next_renewal_date, _message(subscription, email, settings.sender))
        for subscription, email in db.session.execute(upcoming)
    ]

    sent = failed = 0
    for subscription_id, event_date, message in messages:
        if not _claim(subscription_id, event_date):
            continue
        filters = (ReminderDelivery.subscription_id == subscription_id, ReminderDelivery.event_date == event_date)
        try:
            deliver(settings, message)
        except MailRejected as error:
            db.session.execute(db.delete(ReminderDelivery).where(*filters))
            db.session.commit()
            current_app.logger.warning(
                "Reminder %s on %s was rejected (%s) and can retry.",
                subscription_id, event_date, type(error.__cause__).__name__,
            )
            failed += 1
        except MailUnconfirmed:
            current_app.logger.warning("Reminder %s on %s has an unconfirmed SMTP handoff.", subscription_id, event_date)
            failed += 1
        else:
            db.session.execute(db.update(ReminderDelivery).where(*filters).values(sent_at=datetime.now(timezone.utc)))
            db.session.commit()
            sent += 1
    return sent, failed
