"""Pluggable email delivery for password resets.

Without SMTP configuration the message is only written to the server log
(dev mode). Configure SMTP_HOST / SMTP_PORT / SMTP_USER / SMTP_PASSWORD /
SMTP_FROM in .env to send real mail.
"""

import logging
import smtplib
from email.message import EmailMessage

from .config import settings

logger = logging.getLogger("ignitia.mail")


def send_email(to: str, subject: str, body: str) -> bool:
    """Deliver an email. Returns True when the message was handed to SMTP,
    False when it was only logged (no SMTP configured)."""
    if settings.SMTP_HOST:
        try:
            message = EmailMessage()
            message["From"] = settings.SMTP_FROM
            message["To"] = to
            message["Subject"] = subject
            message.set_content(body)
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
                if settings.SMTP_USER:
                    server.starttls()
                    server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                server.send_message(message)
            logger.info("Password-reset email sent to %s", to)
            return True
        except Exception:
            logger.exception("Failed to send password-reset email to %s", to)
            return False

    logger.info("DEV MODE - password reset for %s:\n%s", to, body)
    return False
