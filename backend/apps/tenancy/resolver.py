"""Work out which organization a request is for from the host name.

- `<code>.<SAAS_BASE_DOMAIN>` (e.g. korlebu.shinelighthrm.com) -> the organization with that code;
- `<code>.localhost` in development;
- an organization's own `domain` (e.g. hr.korlebu.gov.gh).
Any other host (the bare base domain, localhost, an IP) resolves to no organization, which keeps the
single-organization deployment working exactly as before.
"""

from django.conf import settings
from django.core.cache import cache

RESERVED_CODES = {"www", "api", "app", "admin", "platform", "static", "media", "mail", "status", "help", "support",
                  "signup", "login", "auth", "docs", "careers", "localhost"}
CACHE_SECONDS = 60


def _host(request):
    host = request.META.get("HTTP_X_FORWARDED_HOST") if settings.USE_X_FORWARDED_HOST else None
    host = (host or request.META.get("HTTP_HOST") or "").split(",")[0].strip().lower()
    return host.rsplit(":", 1)[0] if ":" in host and not host.endswith("]") else host


def code_for_host(host):
    base = (getattr(settings, "SAAS_BASE_DOMAIN", "") or "").lower().strip(".")
    for suffix in filter(None, [base, "localhost"]):
        if host.endswith("." + suffix):
            label = host[: -len(suffix) - 1]
            if label and "." not in label and label not in RESERVED_CODES:
                return label
    return None


def org_for_host(host):
    """The Organization for a host name, or None. Cached briefly; inactive organizations are returned too
    so callers can explain that access is suspended."""
    from .models import Organization

    if not host:
        return None
    key = f"tenant-host:{host}"
    org_id = cache.get(key)
    if org_id is None:
        code = code_for_host(host)
        org = (Organization.objects.filter(code=code).first() if code else None) or \
            Organization.objects.filter(domain__iexact=host).exclude(domain="").first()
        org_id = org.pk if org else 0
        cache.set(key, org_id, CACHE_SECONDS)
    return Organization.objects.filter(pk=org_id).first() if org_id else None


def is_cloud():
    return getattr(settings, "DEPLOYMENT_MODE", "self_hosted") == "cloud"


def request_tenant(request):
    """The organization the host name selects (cloud edition only; self-hosted serves its one organization)."""
    if not hasattr(request, "_tenant"):
        request._tenant = org_for_host(_host(request)) if is_cloud() else None
    return request._tenant


def forget(org):
    """Drop cached host lookups after an organization's code or domain changes."""
    base = (getattr(settings, "SAAS_BASE_DOMAIN", "") or "").lower().strip(".")
    for host in filter(None, [f"{org.code}.localhost", f"{org.code}.{base}" if base else "", (org.domain or "").lower()]):
        cache.delete(f"tenant-host:{host}")
