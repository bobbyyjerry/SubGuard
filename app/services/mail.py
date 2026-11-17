"""Send reminder messages through SMTP or Brevo's HTTPS API."""
import json
import smtplib
import ssl
from contextlib import suppress
from dataclasses import dataclass, field
from email.message import EmailMessage
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


BREVO_EMAIL_URL = "https://api.brevo.com/v3/smtp/email"


class MailRejected(Exception):
    """The mail provider did not accept the message."""


class MailUnconfirmed(Exception):
    """The mail provider did not confirm the handoff."""


def _validate_sender(sender):
    header = EmailMessage()
    header["From"] = sender
    addresses = header["From"].addresses
    if len(addresses) != 1 or header["From"].defects or not addresses[0].domain:
        raise ValueError("Set MAIL_DEFAULT_SENDER to one valid email address.")


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
        _validate_sender(sender)

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


@dataclass(frozen=True)
class BrevoSettings:
    sender: str
    api_key: str = field(repr=False)


def mail_settings_from_config(config):
    transport = config.get("MAIL_TRANSPORT", "smtp").strip().lower()
    if transport == "smtp":
        return MailSettings.from_config(config)
    if transport != "brevo":
        raise ValueError("MAIL_TRANSPORT must be smtp or brevo.")

    sender = (config.get("MAIL_DEFAULT_SENDER") or "").strip()
    api_key = (config.get("BREVO_API_KEY") or "").strip()
    if not sender or not api_key:
        raise ValueError("Set BREVO_API_KEY and MAIL_DEFAULT_SENDER before running reminders with Brevo.")
    _validate_sender(sender)
    return BrevoSettings(sender, api_key)


def deliver(settings, message):
    if isinstance(settings, BrevoSettings):
        _deliver_via_brevo(settings, message)
        return

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


def _deliver_via_brevo(settings, message):
    sender = message["From"].addresses[0]
    payload = {
        "sender": {"name": sender.display_name or "SubGuard", "email": sender.addr_spec},
        "to": [{"email": recipient.addr_spec} for recipient in message["To"].addresses],
        "subject": str(message["Subject"]),
        "textContent": message.get_content(),
    }
    request = Request(
        BREVO_EMAIL_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    request.add_unredirected_header("api-key", settings.api_key)
    try:
        with urlopen(request, timeout=10) as response:
            if response.status != 201:
                raise MailUnconfirmed
    except HTTPError as error:
        with suppress(OSError):
            error.close()
        if 400 <= error.code < 500 and error.code != 408:
            raise MailRejected(f"HTTP {error.code}") from error
        raise MailUnconfirmed from error
    except URLError as error:
        if isinstance(error.reason, ConnectionRefusedError):
            raise MailRejected from error
        raise MailUnconfirmed from error
    except OSError as error:
        raise MailUnconfirmed from error
