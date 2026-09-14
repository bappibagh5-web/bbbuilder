"""Organization-scoped real SMTP transport. Readiness never connects or decrypts."""

import smtplib
import socket
import ssl
import uuid
from email.message import EmailMessage
from email.utils import formataddr

from django.core.exceptions import ValidationError

from .credentials import decrypt_password, encryption_ready
from .models import OutreachSenderSettings, OutreachSMTPConfiguration


def provider_status(organization=None, *, include_disabled=True):
    """Return safe status only; no credentials, host value, or network access."""
    config = (
        OutreachSMTPConfiguration.objects.filter(organization=organization).first()
        if organization is not None
        else None
    )
    base = {
        "provider": "smtp",
        "host_configured": bool(config and config.host),
        "port_configured": bool(config and config.port),
        "username_configured": bool(config and config.username),
        "password_saved": bool(config and config.encrypted_password),
        "tls_mode": config.security if config else "none",
        "encryption_ready": encryption_ready(),
    }
    if not config or (include_disabled and not config.is_enabled):
        return {**base, "state": "disabled", "label": "Email delivery is disabled"}
    if not (
        config.host
        and config.port
        and config.username
        and config.encrypted_password
        and config.security in {"starttls", "ssl"}
        and 1 <= config.timeout_seconds <= 120
        and encryption_ready()
    ):
        return {**base, "state": "misconfigured", "label": "Email delivery is not configured"}
    return {**base, "state": "configured", "label": "Email delivery configured"}


def _open_connection(config):
    if provider_status(config.organization, include_disabled=False)["state"] != "configured":
        raise ValidationError("Email delivery is not configured. Check Settings.")
    password = decrypt_password(config.encrypted_password)
    context = ssl.create_default_context()
    if config.security == OutreachSMTPConfiguration.Security.SSL:
        connection = smtplib.SMTP_SSL(
            config.host, config.port, timeout=config.timeout_seconds, context=context
        )
    else:
        connection = smtplib.SMTP(config.host, config.port, timeout=config.timeout_seconds)
    try:
        if config.security == OutreachSMTPConfiguration.Security.STARTTLS:
            connection.starttls(context=context)
        connection.login(config.username, password)
    except Exception:
        connection.close()
        raise
    return connection


def test_connection(organization):
    config = OutreachSMTPConfiguration.objects.get(organization=organization)
    with _open_connection(config):
        pass


def _send(
    organization, *, from_name, from_address, reply_to, to_address, subject, body, message_id
):
    config = OutreachSMTPConfiguration.objects.get(organization=organization)
    if provider_status(organization)["state"] != "configured":
        raise ValidationError("Email delivery is not ready. Check Settings.")
    email = EmailMessage()
    email["From"] = formataddr((from_name, from_address))
    email["To"] = to_address
    email["Reply-To"] = reply_to
    email["Subject"] = subject
    email["Message-ID"] = message_id
    email.set_content(body)
    with _open_connection(config) as connection:
        refused = connection.send_message(email)
        if refused:
            raise smtplib.SMTPRecipientsRefused(refused)


class SMTPDeliveryProvider:
    key = "smtp"

    def deliver(self, *, message, idempotency_key):
        organization = message.recipient.batch.campaign.organization
        domain = message.from_address.rsplit("@", 1)[-1]
        _send(
            organization,
            from_name=message.from_name,
            from_address=message.from_address,
            reply_to=message.reply_to,
            to_address=message.to_address,
            subject=message.subject,
            body=message.body,
            message_id=f"<{idempotency_key}@{domain}>",
        )
        return ""


def send_test_email(organization, recipient_email):
    sender = OutreachSenderSettings.objects.get(organization=organization, is_enabled=True)
    _send(
        organization,
        from_name=sender.display_name,
        from_address=sender.from_address,
        reply_to=sender.reply_to,
        to_address=recipient_email,
        subject="BB Builders Email Delivery Test",
        body=(
            "This is a test message confirming that BB Builders outreach email "
            "delivery is configured correctly. No bid invitation was sent."
        ),
        message_id=f"<outreach-test-{uuid.uuid4().hex}@{sender.from_address.rsplit('@', 1)[-1]}>",
    )


def safe_smtp_failure(error):
    """Categorize without retaining raw SMTP exception text or credentials."""
    if isinstance(error, smtplib.SMTPAuthenticationError):
        return "smtp_authentication", "Email provider authentication failed.", False
    if isinstance(error, smtplib.SMTPRecipientsRefused):
        return "smtp_recipient_rejected", "The email provider rejected the recipient.", False
    if isinstance(error, smtplib.SMTPSenderRefused):
        return "smtp_sender_rejected", "The email provider rejected the sender.", False
    if isinstance(error, (TimeoutError, socket.timeout, smtplib.SMTPServerDisconnected)):
        return (
            "delivery_uncertain",
            "Delivery outcome is uncertain; investigate before retrying.",
            True,
        )
    if isinstance(error, (socket.gaierror, ConnectionRefusedError, ConnectionError)):
        return "smtp_connection", "Could not connect to the email provider.", False
    if isinstance(error, ssl.SSLError):
        return "smtp_security", "Secure email connection failed.", False
    if isinstance(error, smtplib.SMTPConnectError):
        return "smtp_unavailable", "Email provider is unavailable.", False
    if isinstance(error, smtplib.SMTPException):
        return "smtp_protocol", "Email provider rejected the delivery attempt.", False
    if isinstance(error, OSError):
        return "smtp_connection", "Could not connect to the email provider.", False
    return "delivery_failed", "Email delivery failed. You may retry explicitly.", False
