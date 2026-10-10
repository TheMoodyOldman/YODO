"""Outgoing mail over SMTP (STARTTLS). Without SMTP settings nothing is sent and the message is
written to the server log instead, so verification links can still be tried locally."""

import logging
import smtplib
from email.message import EmailMessage

from app.config import settings

log = logging.getLogger(__name__)


def configured() -> bool:
    return bool(settings.smtp_host and settings.mail_from)


def send(to: str, subject: str, body: str) -> None:
    """Meant for FastAPI BackgroundTasks: failures are logged, never raised to a page."""
    if not configured():
        log.warning("Mail not configured; would send to %s: %s\n%s", to, subject, body)
        print(f"[mail not configured] To: {to}\nSubject: {subject}\n{body}\n", flush=True)
        return
    msg = EmailMessage()
    msg["From"] = settings.mail_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
            smtp.starttls()
            if settings.smtp_user:
                smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(msg)
    except (smtplib.SMTPException, OSError):
        log.exception("Sending mail to %s failed", to)
