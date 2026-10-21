"""Signed licence files for the self-hosted edition.

A licence is a JSON payload signed with the vendor's Ed25519 private key, which never leaves the vendor. The
installed system holds only public keys (`keys.py`), so it can verify a licence offline but nobody can change
the employee cap, modules or expiry without breaking the signature.

Lifecycle: no licence -> evaluation (EVALUATION_EMPLOYEES); valid -> its limits apply; within 60 days of expiry
-> reminders; expired -> GRACE_DAYS of normal use; after that -> read-only (sign-in, viewing and exports keep
working, changes are refused until a renewed licence is installed). Data is never locked away.

The cloud edition ignores all of this; it uses plans instead.
"""

import base64
import datetime as dt
import json
from contextlib import contextmanager
from contextvars import ContextVar

from django.core.cache import cache

from apps.core.exceptions import BusinessRuleError

HEADER = "-----BEGIN SHINELIGHT LICENCE-----"
FOOTER = "-----END SHINELIGHT LICENCE-----"
EVALUATION_EMPLOYEES = 25
DEFAULT_GRACE_DAYS = 30
WARN_DAYS = 60
SETTINGS_KEY = "licence"
CACHE_KEY = "licence:state"


_bypass = ContextVar("licence_bypass", default=False)


class LicenceError(Exception):
    pass


@contextmanager
def bypass():
    """Development only (demo seeding): ignore licence limits inside this block."""
    token = _bypass.set(True)
    try:
        yield
    finally:
        _bypass.reset(token)


def _b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _b64d(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


# ---------------------------------------------------------------- signing (vendor side)
def sign(payload: dict, private_key_pem: bytes) -> str:
    from cryptography.hazmat.primitives import serialization

    key = serialization.load_pem_private_key(private_key_pem, password=None)
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    sig = key.sign(body)
    return f"{HEADER}\n{_b64e(body)}.{_b64e(sig)}\n{FOOTER}\n"


# ---------------------------------------------------------------- verification (customer side)
def public_keys():
    from . import keys

    return list(keys.TRUSTED_PUBLIC_KEYS)


def parse(text: str) -> dict:
    """Verify a licence file and return its payload, or raise LicenceError."""
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    body = (text or "").strip()
    if HEADER in body:
        body = body.split(HEADER, 1)[1].split(FOOTER, 1)[0]
    body = "".join(body.split())
    try:
        raw, sig = (_b64d(part) for part in body.split(".", 1))
    except (ValueError, TypeError) as exc:
        raise LicenceError("This is not a ShineLight licence file.") from exc
    for pem in public_keys():
        try:
            Ed25519PublicKey.from_public_bytes(_b64d(pem)).verify(sig, raw)
            break
        except InvalidSignature:
            continue
    else:
        raise LicenceError("The licence signature is not valid. The file may have been altered.")
    try:
        payload = json.loads(raw)
        payload["expires"] = str(dt.date.fromisoformat(payload["expires"]))
    except (ValueError, KeyError) as exc:
        raise LicenceError("The licence file is incomplete.") from exc
    return payload


def _org():
    from apps.tenancy.models import Organization

    return Organization.get_default()


def installed_text(org=None):
    org = org or _org()
    return ((org.settings or {}).get(SETTINGS_KEY) or "") if org else ""


def install(text, user=None):
    """Verify and store a licence for the organization of this installation."""
    from apps.audit import services as audit
    from apps.tenancy.models import OrganizationFeature

    org = _org()
    if org is None:
        raise BusinessRuleError("Set up the organization before installing a licence.", code="licence")
    try:
        payload = parse(text)
    except LicenceError as exc:
        raise BusinessRuleError(str(exc), code="licence_invalid") from exc
    if payload.get("organization") and payload["organization"] != org.code:
        raise BusinessRuleError(f"This licence is for organization '{payload['organization']}', not '{org.code}'.",
                                code="licence_wrong_org")
    org.settings = {**(org.settings or {}), SETTINGS_KEY: text.strip()}
    org.save(update_fields=["settings"])
    features = payload.get("features")
    if features is not None:                       # modules the licence doesn't include are switched off
        OrganizationFeature.objects.filter(organization=org).exclude(code__in=features).update(enabled=False)
    cache.delete(CACHE_KEY)
    audit.log("config", org, {"licence": payload.get("licence_id"), "expires": payload["expires"],
                              "max_employees": payload.get("max_employees")}, actor=user,
              organization=org, object_repr="Licence installed")
    return state(refresh=True)


def state(today=None, refresh=False):
    """The licence state of this installation (cached briefly; cheap to call per request)."""
    from apps.tenancy.resolver import is_cloud

    if is_cloud():
        return {"state": "not_applicable", "read_only": False}
    if not refresh and today is None:
        cached = cache.get(CACHE_KEY)
        if cached is not None:
            return cached
    today = today or dt.date.today()
    text = installed_text()
    if not text:
        out = {"state": "evaluation", "read_only": False, "max_employees": EVALUATION_EMPLOYEES, "features": None,
               "message": f"Evaluation mode: up to {EVALUATION_EMPLOYEES} employees. Install a licence under "
                          "Administration > Licence."}
    else:
        try:
            p = parse(text)
        except LicenceError as exc:
            out = {"state": "invalid", "read_only": True, "max_employees": 0, "features": None,
                   "message": f"The installed licence is not valid ({exc}). Install a valid licence."}
        else:
            expires = dt.date.fromisoformat(p["expires"])
            grace_end = expires + dt.timedelta(days=int(p.get("grace_days", DEFAULT_GRACE_DAYS)))
            days = (expires - today).days
            base = {"customer": p.get("customer"), "licence_id": p.get("licence_id"), "expires": p["expires"],
                    "grace_ends": str(grace_end), "max_employees": p.get("max_employees") or 0,
                    "features": p.get("features"), "days_left": days}
            if today > grace_end:
                out = {**base, "state": "expired", "read_only": True,
                       "message": f"The licence expired on {expires:%d/%m/%Y}. The system is read-only until a "
                                  "renewed licence is installed."}
            elif today > expires:
                out = {**base, "state": "grace", "read_only": False,
                       "message": f"The licence expired on {expires:%d/%m/%Y}. Renew before {grace_end:%d/%m/%Y} "
                                  "to avoid the system becoming read-only."}
            elif days <= WARN_DAYS:
                out = {**base, "state": "expiring", "read_only": False,
                       "message": f"The licence expires on {expires:%d/%m/%Y} ({days} days)."}
            else:
                out = {**base, "state": "active", "read_only": False, "message": ""}
    if today == dt.date.today():
        cache.set(CACHE_KEY, out, 300)
    return out


def employee_cap():
    """Active-employee cap from the licence (self-hosted), or None when there isn't one."""
    s = state()
    if s["state"] == "not_applicable" or _bypass.get():
        return None
    return s.get("max_employees") or None


def feature_allowed(code):
    s = state()
    return s["state"] == "not_applicable" or s.get("features") is None or code in s["features"]


def reminders(today=None):
    """Daily: email administrators 60, 30 and 7 days before expiry and weekly during the grace period."""
    from django.conf import settings
    from django.core.mail import send_mail

    from apps.rbac.services import has_perm

    s = state(today=today)
    today = today or dt.date.today()
    if s["state"] not in ("expiring", "grace", "expired"):
        return 0
    days = s.get("days_left")
    due = (days in (60, 30, 7, 1) or (s["state"] == "grace" and days % 7 == 0)
           or (s["state"] == "expired" and today.weekday() == 0))
    org = _org()
    if not due or org is None:
        return 0
    admins = [u.email for u in org.users.filter(is_active=True) if u.email and has_perm(u, "admin.settings")]
    if admins:
        send_mail("ShineLight HRM licence", s["message"] + "\n\nContact your ShineLight provider to renew.",
                  settings.DEFAULT_FROM_EMAIL, admins)
    return len(admins)
