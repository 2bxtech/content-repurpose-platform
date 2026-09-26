"""Outbound email: SMTP when configured, otherwise the log (development only).

Senders return whether delivery worked. Registration doesn't fail over a
failed email (the user can ask for another); the resend endpoint reports it.
"""

import logging
import smtplib
import ssl
from email.message import EmailMessage

from starlette.concurrency import run_in_threadpool

from app.core.config import settings

logger = logging.getLogger(__name__)


def _send_smtp(to: str, subject: str, body: str) -> None:
    message = EmailMessage()
    message["From"] = settings.SMTP_FROM
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as smtp:
        # Verify the server certificate: credentials and verification links go over this.
        smtp.starttls(context=ssl.create_default_context())
        if settings.SMTP_USERNAME:
            smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        smtp.send_message(message)


async def send_email(to: str, subject: str, body: str) -> bool:
    if settings.SMTP_HOST:
        try:
            await run_in_threadpool(_send_smtp, to, subject, body)
            return True
        except Exception:
            logger.exception("Could not send %r to %s", subject, to)
            return False
    if settings.ENVIRONMENT.lower() == "production":
        # Never fall back to logging in production: the body carries a credential.
        logger.error("SMTP is not configured; %r to %s was not sent", subject, to)
        return False
    logger.info("Email (SMTP not configured, development only) to %s: %s\n%s", to, subject, body)
    return True


async def send_verification_email(to: str, token: str) -> bool:
    link = f"{settings.FRONTEND_URL.rstrip('/')}/verify-email?token={token}"
    body = (
        "Confirm your email address to start using Content Repurpose:\n\n"
        f"{link}\n\n"
        f"The link expires in {settings.EMAIL_VERIFICATION_EXPIRE_HOURS} hours. "
        "If you didn't create an account, you can ignore this email."
    )
    return await send_email(to, "Confirm your email address", body)
