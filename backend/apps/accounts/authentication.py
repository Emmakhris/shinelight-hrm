from django.conf import settings
from rest_framework import exceptions
from rest_framework.authentication import CSRFCheck
from rest_framework_simplejwt.authentication import JWTAuthentication

from apps.core.context import set_current_org, set_current_user


def _enforce_csrf(request):
    def dummy_get_response(request):  # pragma: no cover
        return None

    check = CSRFCheck(dummy_get_response)
    check.process_request(request)
    reason = check.process_view(request, None, (), {})
    if reason:
        raise exceptions.PermissionDenied(f"CSRF Failed: {reason}")


class CookieJWTAuthentication(JWTAuthentication):
    """JWT from the HttpOnly `sl_access` cookie (browser) or Authorization header (API clients).
    Cookie-authenticated unsafe requests must pass CSRF validation."""

    def authenticate(self, request):
        header = self.get_header(request)
        from_cookie = False
        if header is not None:
            raw = self.get_raw_token(header)
        else:
            raw = request.COOKIES.get(settings.AUTH_COOKIE_ACCESS)
            from_cookie = True
        if raw is None:
            return None
        validated = self.get_validated_token(raw)
        user = self.get_user(validated)
        if not user.is_active:
            raise exceptions.AuthenticationFailed("Account disabled.")
        if from_cookie and request.method not in ("GET", "HEAD", "OPTIONS"):
            _enforce_csrf(request)
        from apps.tenancy.services import check_access

        check_access(request, user)
        set_current_user(user)
        set_current_org(user.organization)
        return user, validated
