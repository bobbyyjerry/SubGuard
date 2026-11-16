"""Run reminder checks independently of the Flask web process."""
from datetime import datetime, timezone

import click
from apscheduler.schedulers.blocking import BlockingScheduler
from flask import current_app
from flask.cli import with_appcontext
from sqlalchemy import inspect

from .extensions import db
from .models import ReminderDelivery
from .services.mail import MailSettings
from .services.reminders import send_due_reminders


def _scan(app, settings, lead_days):
    with app.app_context():
        sent, failed = send_due_reminders(settings, lead_days)
    click.echo(f"Reminders sent: {sent}. Failed or unconfirmed: {failed}.")
    return failed


@click.command("reminders")
@click.option("--once", is_flag=True, help="Send due reminders once and exit.")
@with_appcontext
def reminders_command(once):
    """Run the email reminder worker."""
    app = current_app._get_current_object()
    try:
        settings = MailSettings.from_config(app.config)
    except ValueError as error:
        raise click.ClickException(str(error)) from None
    try:
        lead_days = int(app.config["REMINDER_DAYS"])
    except (ValueError, TypeError):
        lead_days = 0
    if not 1 <= lead_days <= 30:
        raise click.ClickException("REMINDER_DAYS must be an integer from 1 to 30.")
    if not inspect(db.engine).has_table(ReminderDelivery.__tablename__):
        raise click.ClickException("Run flask init-db to create the reminder delivery table.")

    if once:
        if _scan(app, settings, lead_days):
            raise click.ClickException("Some reminders could not be confirmed.")
        return

    scheduler = BlockingScheduler(timezone=timezone.utc)
    scheduler.add_job(
        _scan,
        "interval",
        args=(app, settings, lead_days),
        minutes=15,
        next_run_time=datetime.now(timezone.utc),
        coalesce=True,
        max_instances=1,
        misfire_grace_time=900,
    )
    click.echo(f"Checking for reminders every 15 minutes with a {lead_days}-day reminder window.")
    try:
        scheduler.start()
    except KeyboardInterrupt:
        pass
    finally:
        if scheduler.running:
            scheduler.shutdown()
