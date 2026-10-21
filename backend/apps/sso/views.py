import logging
import urllib.parse

from django.conf import settings
from django.http import HttpResponseRedirect
from django.utils import timezone
from rest_framework import permissions, serializers
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.accounts.views import _record_attempt, _set_auth_cookies
from apps.audit import services as audit
from apps.core.context import org_context
from apps.core.serializers import TenantSerializer
from apps.core.views import TenantModelViewSet

from . import services
from .models import IdentityProvider

log = logging.getLogger(__name__)


def _to_login(code):
    return HttpResponseRedirect(f"{settings.FRONTEND_URL.rstrip('/')}/login?sso_error={urllib.parse.quote(code)}")


class DiscoverView(APIView):
    """Find the identity provider for a work email. Public; reveals only whether SSO exists for the domain."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    def post(self, request):
        p = services.provider_for_email(str(request.data.get("email", "")))
        if p is None:
            return Response({"detail": "Single sign-on is not set up for this email domain. "
                                       "Sign in with your username and password."}, status=404)
        return Response({"name": p.name, "start_url": f"/api/sso/{p.pk}/start/"})


class StartView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request, pk):
        p = IdentityProvider.all_objects.filter(pk=pk, is_active=True).select_related("organization").first()
        if p is None or not p.organization.is_active:
            return _to_login("unknown_provider")
        try:
            url, cookie = services.start(p, request.query_params.get("next", "/"))
        except services.SsoError as exc:
            log.warning("SSO start failed for provider %s: %s", p.pk, exc)
            return _to_login(exc.code)
        resp = HttpResponseRedirect(url)
        resp.set_cookie(services.STATE_COOKIE, cookie, max_age=services.STATE_MAX_AGE, httponly=True,
                        secure=settings.AUTH_COOKIE_SECURE, samesite="Lax", path="/api/sso/")
        return resp


class CallbackView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request):
        q = request.query_params
        if q.get("error"):
            return _to_login("cancelled" if q["error"] == "access_denied" else "provider_error")
        try:
            state = services.read_state(request.COOKIES.get(services.STATE_COOKIE), q.get("state"))
            p = IdentityProvider.all_objects.select_related("organization").get(pk=state["p"], is_active=True)
        except services.SsoError as exc:
            return _to_login(exc.code)
        except IdentityProvider.DoesNotExist:
            return _to_login("unknown_provider")
        with org_context(p.organization):
            try:
                token = services.exchange_code(p, q.get("code", ""), state["v"])
                claims = services.verify_id_token(p, token, state["n"])
                user = services.resolve_user(p, claims)
            except services.SsoError as exc:
                log.warning("SSO sign-in failed (%s) via provider %s: %s", exc.code, p.pk, exc)
                _record_attempt(request, f"sso:{p.pk}", None, False, f"sso_{exc.code}"[:50])
                return _to_login(exc.code)
            user.failed_login_count = 0
            user.last_login = timezone.now()
            user.save(update_fields=["failed_login_count", "last_login"])
            _record_attempt(request, user.username, user, True, "sso")
            audit.log("login", user, {"method": "sso", "provider": p.name}, actor=user, organization=p.organization)
        resp = HttpResponseRedirect(settings.FRONTEND_URL.rstrip("/") + state.get("next", "/"))
        resp.delete_cookie(services.STATE_COOKIE, path="/api/sso/")
        return _set_auth_cookies(resp, user)


class IdentityProviderSerializer(TenantSerializer):
    client_secret = serializers.CharField(write_only=True, required=False, allow_blank=True)
    has_secret = serializers.SerializerMethodField()
    redirect_uri = serializers.SerializerMethodField()
    linked_users = serializers.SerializerMethodField()

    class Meta(TenantSerializer.Meta):
        model = IdentityProvider

    def get_has_secret(self, obj):
        return bool(obj.client_secret)

    def get_redirect_uri(self, obj):
        return services.redirect_uri()

    def get_linked_users(self, obj):
        return obj.identities.count()

    def validate(self, attrs):
        raw = attrs.get("email_domains", getattr(self.instance, "email_domains", ""))
        domains = IdentityProvider(email_domains=raw).domains
        if not domains:
            raise serializers.ValidationError({"email_domains": "Enter at least one email domain."})
        services.ensure_unique_domains(domains, getattr(self.instance, "pk", None))
        attrs["email_domains"] = ", ".join(domains)
        if self.instance is not None and not attrs.get("client_secret"):
            attrs.pop("client_secret", None)        # blank on edit keeps the stored secret
        return attrs


class IdentityProviderViewSet(TenantModelViewSet):
    queryset = IdentityProvider.objects.all()
    serializer_class = IdentityProviderSerializer
    perm_module = "admin"
    perm_read = "admin.settings"
    perm_write = "admin.settings"
    pagination_class = None

    @action(detail=True, methods=["post"])
    def test(self, request, pk=None):
        p = self.get_object()
        try:
            return Response({"ok": True, **services.test_provider(p)})
        except services.SsoError as exc:
            return Response({"ok": False, "code": exc.code, "detail": str(exc)})
