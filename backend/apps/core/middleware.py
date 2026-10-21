from .context import set_current_ip, set_current_org, set_current_user


def client_ip(request):
    """The client's address, trusting only the proxies we run (settings.TRUSTED_PROXY_COUNT). Entries a client
    puts in X-Forwarded-For itself sit further left and are ignored."""
    from django.conf import settings

    remote = request.META.get("REMOTE_ADDR")
    count = getattr(settings, "TRUSTED_PROXY_COUNT", 0)
    if not count:
        return remote
    chain = [p.strip() for p in request.META.get("HTTP_X_FORWARDED_FOR", "").split(",") if p.strip()]
    return chain[-count] if len(chain) >= count else (chain[0] if chain else remote)


class RequestContextMiddleware:
    """Resets the request context. For JWT/API-key requests the organization and user
    are populated by the DRF authentication classes (which run after middleware)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        set_current_ip(client_ip(request))
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            set_current_user(user)
            set_current_org(user.organization)
        else:
            set_current_user(None)
            set_current_org(None)
        return self.get_response(request)
