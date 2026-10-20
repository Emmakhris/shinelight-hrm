import re

from django.core.exceptions import ValidationError

GHANA_CARD_RE = re.compile(r"^GHA-\d{9}-\d$")
SSNIT_RE = re.compile(r"^[A-Z]\d{12}$")
GH_PHONE_RE = re.compile(r"^(\+233|0)\d{9}$")


def validate_ghana_card(value):
    """Ghana Card PIN format: GHA-123456789-0."""
    if value and not GHANA_CARD_RE.match(value.upper()):
        raise ValidationError("Ghana Card number must look like GHA-123456789-0.")


def validate_ssnit(value):
    """SSNIT number: one letter followed by 12 digits (e.g. C123456789012)."""
    if value and not SSNIT_RE.match(value.upper()):
        raise ValidationError("SSNIT number must be a letter followed by 12 digits.")


def validate_gh_phone(value):
    if value and not GH_PHONE_RE.match(value.replace(" ", "")):
        raise ValidationError("Enter a Ghana phone number, e.g. 0241234567 or +233241234567.")


def normalize_gh_phone(value: str) -> str:
    """Return E.164 (+233...) form used by SMS gateways."""
    if not value:
        return value
    v = value.replace(" ", "").replace("-", "")
    if v.startswith("0"):
        v = "+233" + v[1:]
    elif v.startswith("233"):
        v = "+" + v
    return v
