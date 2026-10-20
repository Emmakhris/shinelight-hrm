from .context import set_current_ip, set_current_org, set_current_user


def client_ip(request):
    fwd = request.META.get("HTTP_X_FORWARDED_FOR")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


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
