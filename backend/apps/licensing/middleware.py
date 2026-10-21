from django.http import JsonResponse

# Still allowed when the licence has run out: signing in and out, password changes and installing a renewed
# licence. Nothing that changes HR records.
ALLOWED_WRITES = ("/api/auth/", "/api/licence/")
SAFE_METHODS = ("GET", "HEAD", "OPTIONS")


class LicenceMiddleware:
    """Self-hosted edition: once a licence is past its grace period, the API becomes read-only.
    Viewing and exporting keep working so the organization never loses access to its own data."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method not in SAFE_METHODS and request.path.startswith("/api/") \
                and not request.path.startswith(ALLOWED_WRITES):
            from .services import state

            s = state()
            if s.get("read_only"):
                return JsonResponse({"detail": s.get("message") or "The licence has expired; the system is read-only.",
                                     "code": "licence_expired"}, status=402)
        return self.get_response(request)
