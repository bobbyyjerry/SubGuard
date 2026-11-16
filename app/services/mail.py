"""Send reminder messages through the configured SMTP relay."""
import smtplib
import ssl
from contextlib import suppress
from dataclasses import dataclass, field
from email.message import EmailMessage


class MailRejected(Exception):
    """The relay did not accept the message."""


class MailUnconfirmed(Exception):
    """The connection was lost while handing off the message."""


@dataclass(frozen=True)
class MailSettings:
    server: str
    port: int
    security: str
    sender: str
    username: str | None = None
    password: str | None = field(default=None, repr=False)

    @classmethod
    def from_config(cls, config):
        server = (config.get("MAIL_SERVER") or "").strip()
        sender = (config.get("MAIL_DEFAULT_SENDER") or "").strip()
        if not server or not sender:
            raise ValueError("Set MAIL_SERVER and MAIL_DEFAULT_SENDER before running reminders.")
        header = EmailMessage()
        header["From"] = sender
        addresses = header["From"].addresses
        if len(addresses) != 1 or header["From"].defects or not addresses[0].domain:
            raise ValueError("Set MAIL_DEFAULT_SENDER to one valid email address.")

        security = config["MAIL_SECURITY"].strip().lower()
        default_ports = {"starttls": 587, "ssl": 465, "none": 25}
        if security not in default_ports:
            raise ValueError("MAIL_SECURITY must be starttls, ssl, or none.")
        try:
            port = int(config.get("MAIL_PORT") or default_ports[security])
        except ValueError:
            raise ValueError("MAIL_PORT must be an integer from 1 to 65535.") from None
        if not 1 <= port <= 65535:
            raise ValueError("MAIL_PORT must be an integer from 1 to 65535.")

        username = config.get("MAIL_USERNAME")
        password = config.get("MAIL_PASSWORD")
        if bool(username) != bool(password):
            raise ValueError("Set both MAIL_USERNAME and MAIL_PASSWORD for authenticated SMTP.")
        if username and security == "none":
            raise ValueError("Use starttls or ssl with SMTP credentials.")
        return cls(server, port, security, sender, username, password)


def deliver(settings, message):
    connection = None
    handing_off = False
    try:
        if settings.security == "ssl":
            connection = smtplib.SMTP_SSL(settings.server, settings.port, timeout=10, context=ssl.create_default_context())
        else:
            connection = smtplib.SMTP(settings.server, settings.port, timeout=10)
            if settings.security == "starttls":
                connection.starttls(context=ssl.create_default_context())
        if settings.username:
            connection.login(settings.username, settings.password)

        handing_off = True
        connection.send_message(message)
    except (smtplib.SMTPSenderRefused, smtplib.SMTPRecipientsRefused, smtplib.SMTPDataError,
            smtplib.SMTPNotSupportedError, smtplib.SMTPHeloError) as error:
        raise MailRejected from error
    except OSError as error:
        if handing_off:
            raise MailUnconfirmed from error
        raise MailRejected from error
    finally:
        if connection is not None:
            # A dropped connection after acceptance does not undo the delivery.
            with suppress(OSError):
                connection.close()
