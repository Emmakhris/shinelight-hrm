"""Encrypted model fields for sensitive data at rest (bank account numbers, IDs)."""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import models


def _fernet():
    key = settings.FIELD_ENCRYPTION_KEY
    if not key:
        # Derive a stable key from SECRET_KEY for development. Production must set FIELD_ENCRYPTION_KEY.
        key = base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode()).digest())
    return Fernet(key)


class EncryptedCharField(models.TextField):
    """Stores Fernet-encrypted text. Not searchable; keep a separate hash/last4 field if lookups are needed."""

    def from_db_value(self, value, expression, connection):
        if value in (None, ""):
            return value
        try:
            return _fernet().decrypt(value.encode()).decode()
        except InvalidToken:
            return value

    def to_python(self, value):
        return value

    def get_prep_value(self, value):
        if value in (None, ""):
            return value
        return _fernet().encrypt(str(value).encode()).decode()


def mask(value: str | None, visible: int = 4) -> str | None:
    if not value:
        return value
    value = str(value)
    if len(value) <= visible:
        return "*" * len(value)
    return "*" * (len(value) - visible) + value[-visible:]
