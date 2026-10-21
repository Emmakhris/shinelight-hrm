"""OpenID Connect single sign-on (authorization code flow with PKCE).

Security notes:
- state, nonce and the PKCE verifier live in a short-lived signed cookie, so the callback can only complete
  a sign-in this browser started; the ID token signature is checked against the provider's JWKS, along
  with issuer, audience, expiry and nonce.
- A login only maps to an existing ShineLight user in the provider's organization. With
  auto_create_accounts a login is created for an existing active employee, never an employee record.
- MFA is the identity provider's responsibility for SSO sign-ins (configure it there).
"""

import base64
import hashlib
import secrets
import urllib.parse

import jwt
import requests
from django.conf import settings
from django.core import signing
from django.core.cache import cache
from django.utils import timezone

from apps.core.exceptions import BusinessRuleError

from .models import ExternalIdentity, IdentityProvider

STATE_SALT = "shinelight.sso"
STATE_MAX_AGE = 600
STATE_COOKIE = "sl_sso"
HTTP_TIMEOUT = 10


class SsoError(Exception):
    """A sign-in failure with a code the login page can explain."""

    def __init__(self, code, detail=""):
        super().__init__(detail or code)
        self.code = code


def redirect_uri(request=None, organization=None):
    """Where the identity provider sends the user back: the address they signed in on, so the session cookie
    lands on their organization's own host (cloud subdomain or custom domain). SSO_REDIRECT_BASE overrides."""
    base = getattr(settings, "SSO_REDIRECT_BASE", "")
    if not base and request is not None:
        return request.build_absolute_uri("/api/sso/callback/")
    if not base and organization is not None:
        from apps.tenancy.services import login_url

        base = login_url(organization).rsplit("/login", 1)[0]
    return f"{(base or settings.FRONTEND_URL).rstrip('/')}/api/sso/callback/"


def provider_for_email(email):
    """The active provider (in any organization) that owns this email's domain."""
    domain = (email or "").rsplit("@", 1)[-1].strip().lower()
    if not domain or "@" not in (email or ""):
        return None
    for p in IdentityProvider.all_objects.filter(is_active=True, email_domains__icontains=domain) \
            .select_related("organization"):
        if domain in p.domains and p.organization.is_active:
            return p
    return None


def domain_taken(domains, exclude_pk=None):
    """Domains must map to one provider across all organizations, or sign-in would be ambiguous."""
    from apps.tenancy.rls import unrestricted

    clash = []
    with unrestricted():
        for p in IdentityProvider.all_objects.exclude(pk=exclude_pk):
            clash += [d for d in domains if d in p.domains]
    return clash


def password_login_blocked(user):
    """True when the user's domain is SSO-only. Organization administrators keep a break-glass password route."""
    from apps.rbac.services import has_perm

    if not user.email or user.is_superuser:
        return False
    p = provider_for_email(user.email)
    if p is None or p.allow_password_login or p.organization_id != user.organization_id:
        return False
    return not has_perm(user, "admin.settings")


# ---------------------------------------------------------------- provider metadata
def discovery(provider):
    key = f"sso:disc:{provider.pk}:{hashlib.sha1(provider.issuer.encode()).hexdigest()}"
    doc = cache.get(key)
    if doc is None:
        url = provider.issuer.rstrip("/") + "/.well-known/openid-configuration"
        try:
            r = requests.get(url, timeout=HTTP_TIMEOUT)
            r.raise_for_status()
            doc = r.json()
        except (requests.RequestException, ValueError) as exc:
            raise SsoError("provider_unreachable", f"Could not read {url}: {exc}") from exc
        for k in ("authorization_endpoint", "token_endpoint", "jwks_uri", "issuer"):
            if k not in doc:
                raise SsoError("provider_misconfigured", f"Discovery document has no {k}.")
        cache.set(key, doc, 3600)
    return doc


def jwks(provider, uri):
    key = f"sso:jwks:{provider.pk}"
    data = cache.get(key)
    if data is None:
        try:
            r = requests.get(uri, timeout=HTTP_TIMEOUT)
            r.raise_for_status()
            data = r.json()
        except (requests.RequestException, ValueError) as exc:
            raise SsoError("provider_unreachable", str(exc)) from exc
        cache.set(key, data, 3600)
    return data


def test_provider(provider):
    doc = discovery(provider)
    return {"issuer": doc["issuer"], "authorization_endpoint": doc["authorization_endpoint"],
            "token_endpoint": doc["token_endpoint"], "redirect_uri": redirect_uri(organization=provider.organization)}


# ---------------------------------------------------------------- flow
def _b64(data: bytes):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def start(provider, next_path="/", request=None):
    """Return (authorization_url, signed_state_cookie_value)."""
    doc = discovery(provider)
    verifier = _b64(secrets.token_bytes(32))
    state, nonce = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
    if not next_path.startswith("/") or next_path.startswith("//"):
        next_path = "/"
    params = {
        "response_type": "code", "client_id": provider.client_id, "redirect_uri": redirect_uri(request),
        "scope": provider.scopes, "state": state, "nonce": nonce,
        "code_challenge": _b64(hashlib.sha256(verifier.encode()).digest()), "code_challenge_method": "S256",
    }
    cookie = signing.dumps({"p": provider.pk, "s": state, "n": nonce, "v": verifier, "next": next_path},
                           salt=STATE_SALT)
    sep = "&" if "?" in doc["authorization_endpoint"] else "?"
    return doc["authorization_endpoint"] + sep + urllib.parse.urlencode(params), cookie


def read_state(cookie, state):
    try:
        data = signing.loads(cookie or "", salt=STATE_SALT, max_age=STATE_MAX_AGE)
    except signing.BadSignature as exc:
        raise SsoError("expired", "The sign-in attempt expired. Please try again.") from exc
    if not state or not secrets.compare_digest(str(data.get("s")), str(state)):
        raise SsoError("state_mismatch", "The sign-in response did not match this browser.")
    return data


def exchange_code(provider, code, verifier, request=None):
    doc = discovery(provider)
    try:
        r = requests.post(doc["token_endpoint"], timeout=HTTP_TIMEOUT, data={
            "grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri(request),
            "client_id": provider.client_id, "client_secret": provider.client_secret or "",
            "code_verifier": verifier})
        body = r.json()
    except (requests.RequestException, ValueError) as exc:
        raise SsoError("provider_unreachable", str(exc)) from exc
    if r.status_code != 200 or "id_token" not in body:
        raise SsoError("token_rejected", body.get("error_description") or body.get("error") or "No ID token.")
    return body["id_token"]


def verify_id_token(provider, id_token, nonce):
    doc = discovery(provider)
    try:
        header = jwt.get_unverified_header(id_token)
        keys = jwt.PyJWKSet.from_dict(jwks(provider, doc["jwks_uri"]))
        key = next((k for k in keys.keys if k.key_id == header.get("kid")), None) or (
            keys.keys[0] if len(keys.keys) == 1 else None)
        if key is None:
            raise SsoError("bad_token", "Signing key not found.")
        claims = jwt.decode(id_token, key.key, algorithms=["RS256", "RS384", "RS512", "ES256", "PS256"],
                            audience=provider.client_id, issuer=doc["issuer"], leeway=60,
                            options={"require": ["exp", "iat", "sub", "iss", "aud"]})
    except jwt.PyJWTError as exc:
        raise SsoError("bad_token", f"ID token rejected: {exc}") from exc
    if not secrets.compare_digest(str(claims.get("nonce", "")), str(nonce)):
        raise SsoError("bad_token", "ID token nonce mismatch.")
    return claims


def resolve_user(provider, claims):
    """Map verified claims to a user of the provider's organization (caller sets the org context)."""
    from django.contrib.auth import get_user_model

    from apps.employees.models import ACTIVE_STATUSES, Employee

    User = get_user_model()
    link = ExternalIdentity.objects.filter(provider=provider, subject=claims["sub"]).select_related("user").first()
    email = (claims.get(provider.email_claim) or claims.get("email") or "").strip().lower()
    if link is None:
        if claims.get("email_verified") is False:
            raise SsoError("email_unverified", "Your identity provider has not verified this email address.")
        if not email or email.rsplit("@", 1)[-1] not in provider.domains:
            raise SsoError("domain_not_allowed", "This account's email domain is not set up for single sign-on.")
        user = User.objects.filter(organization=provider.organization, email__iexact=email).first()
        if user is None:
            emp = Employee.objects.filter(work_email__iexact=email, status__in=ACTIVE_STATUSES).first()
            if emp is not None and emp.user_id:
                user = emp.user
            elif emp is not None and provider.auto_create_accounts:
                user = _create_account(emp, email)
        if user is None:
            raise SsoError("no_account", "There is no ShineLight HRM account for this email. Please contact HR.")
        link = ExternalIdentity.objects.create(provider=provider, user=user, subject=claims["sub"], email=email)
    user = link.user
    if not user.is_active or user.organization_id != provider.organization_id:
        raise SsoError("inactive", "This account is disabled.")
    if user.is_locked:
        raise SsoError("locked", "This account is temporarily locked.")
    link.last_login_at = timezone.now()
    link.email = email or link.email
    link.save(update_fields=["last_login_at", "email"])
    return user


def _create_account(emp, email):
    from django.contrib.auth import get_user_model

    from apps.rbac.models import Role, RoleAssignment

    User = get_user_model()
    base = email.split("@")[0][:120] or emp.staff_number.lower()
    username, n = base, 1
    while User.objects.filter(username__iexact=username).exists():
        n += 1
        username = f"{base}{n}"
    user = User.objects.create_user(username=username, email=email, first_name=emp.first_name,
                                    last_name=emp.last_name, organization=emp.organization)
    user.set_unusable_password()
    user.save()
    emp.user = user
    emp.save(update_fields=["user"])
    for code in ["employee"] + (["line_manager"] if emp.direct_reports.exists() else []):
        role = Role.objects.filter(code=code).first()
        if role:
            RoleAssignment.objects.create(user=user, role=role)
    return user


def ensure_unique_domains(domains, exclude_pk=None):
    clash = domain_taken(domains, exclude_pk)
    if clash:
        raise BusinessRuleError(f"Domain already used by another identity provider: {', '.join(clash)}.",
                                code="sso_domain_taken")
