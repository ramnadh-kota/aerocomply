"""Outbound transactional email, for the auth verification/reset flows.

This codebase has no prior email-sending capability at all (no SMTP
integration, no provider SDK, no NotificationService). Rather than invent a
dependency on a specific paid provider (SendGrid/SES/Postmark/etc.) that
this repository has no credentials or account for, this follows the exact
pattern already established for the AI provider (see
app.core.config.Settings.ai_provider / app/services/lisa's
NotConfiguredProvider): if SMTP is not configured, email "sends" go to a
`ConsoleEmailSender` that logs the message instead of silently no-op'ing or
raising -- so the OTP flow is fully exercisable in local dev/CI without any
real mail server, and the exact code a developer needs is always visible in
the server log. Configuring `SMTP_HOST` switches to a real
`SmtpEmailSender` using only the Python standard library (smtplib), so no
new third-party dependency is added for this milestone.
"""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from typing import Protocol

from app.core.config import get_settings

logger = logging.getLogger("aerocomply.email")


class EmailSender(Protocol):
    def send(self, *, to: str, subject: str, body: str) -> None: ...


class ConsoleEmailSender:
    """Dev/CI fallback used whenever SMTP_HOST is not configured. Never used
    if real SMTP settings are present (see get_email_sender)."""

    def send(self, *, to: str, subject: str, body: str) -> None:
        logger.info(
            "EMAIL (console sink, SMTP not configured) to=%s subject=%r\n%s", to, subject, body
        )


class SmtpEmailSender:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        use_tls: bool,
        from_address: str,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._use_tls = use_tls
        self._from_address = from_address

    def send(self, *, to: str, subject: str, body: str) -> None:
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = self._from_address
        message["To"] = to
        message.set_content(body)

        with smtplib.SMTP(self._host, self._port, timeout=10) as smtp:
            if self._use_tls:
                smtp.starttls()
            if self._username:
                smtp.login(self._username, self._password)
            smtp.send_message(message)


def get_email_sender() -> EmailSender:
    settings = get_settings()
    if not settings.smtp_host:
        return ConsoleEmailSender()
    return SmtpEmailSender(
        host=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_username,
        password=settings.smtp_password,
        use_tls=settings.smtp_use_tls,
        from_address=settings.smtp_from_address or "no-reply@kotas-aerospace.com",
    )


def send_verification_code_email(*, to: str, code: str, purpose_label: str) -> None:
    sender = get_email_sender()
    sender.send(
        to=to,
        subject=f"KOTA AEROSPACE — {purpose_label} code",
        body=(
            f"Your {purpose_label.lower()} code is: {code}\n\n"
            "This code expires in 10 minutes and can only be used once. "
            "If you did not request this, you can safely ignore this email."
        ),
    )
