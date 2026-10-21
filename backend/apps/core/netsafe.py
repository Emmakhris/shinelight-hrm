"""Outbound HTTP to URLs that organization administrators configure (webhooks, SSO identity providers).

In the cloud edition one tenant's administrator must not be able to make the server call internal services
(the database, Redis, the backend itself, the cloud provider's metadata endpoint). Such URLs must use HTTPS and
resolve only to public addresses, and redirects are not followed. The self-hosted edition allows private
addresses, because calling systems on the customer's own network is the point there.
"""

import ipaddress
import socket
from urllib.parse import urlsplit

from django.conf import settings


class UnsafeURL(ValueError):
    pass


def _cloud():
    return getattr(settings, "DEPLOYMENT_MODE", "self_hosted") == "cloud"


def check_url(url, require_https=None):
    """Raise UnsafeURL unless `url` may be called from this server. Returns the URL."""
    parts = urlsplit(url or "")
    cloud = _cloud()
    if require_https is None:
        require_https = cloud
    if parts.scheme not in ("https",) + (() if require_https else ("http",)):
        raise UnsafeURL("The address must start with https://." if require_https else "Use an http(s) address.")
    host = parts.hostname
    if not host:
        raise UnsafeURL("The address has no host name.")
    if not cloud:
        return url
    try:
        infos = socket.getaddrinfo(host, parts.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise UnsafeURL(f"{host} could not be resolved.") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global or ip.is_multicast:
            raise UnsafeURL(f"{host} points to a private or reserved network address, which is not allowed.")
    return url


def request_kwargs():
    """Extra arguments for `requests` calls to administrator-configured URLs."""
    return {"allow_redirects": False}
