"""Encryption boundary for organization SMTP passwords; the key is deployment-only."""

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.exceptions import ValidationError


def _cipher():
    key = settings.OUTREACH_CREDENTIAL_ENCRYPTION_KEY
    if not key:
        raise ValidationError(
            "Server credential encryption is not configured. Ask an administrator."
        )
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, UnicodeError) as error:
        raise ValidationError(
            "Server credential encryption is invalid. Ask an administrator."
        ) from error


def encryption_ready():
    try:
        _cipher()
    except ValidationError:
        return False
    return True


def encrypt_password(secret):
    if not secret:
        raise ValidationError("Enter an SMTP password or app password.")
    return _cipher().encrypt(secret.encode("utf-8")).decode("ascii")


def decrypt_password(ciphertext):
    if not ciphertext:
        raise ValidationError("SMTP password is not configured.")
    try:
        return _cipher().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, UnicodeError) as error:
        raise ValidationError(
            "Stored SMTP credential cannot be used. Re-enter it in Settings."
        ) from error
