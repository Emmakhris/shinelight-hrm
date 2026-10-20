import base64
import io
import secrets
from datetime import timedelta

import qrcode
import qrcode.image.svg
from django.conf import settings
from django.contrib.auth import authenticate, get_user_model, password_validation
from django.contrib.auth.tokens import default_token_generator
from django.core import signing
from django.core.cache import cache
from django.core.mail import send_mail
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.views.decorators.csrf import ensure_csrf_cookie
from django_otp.plugins.otp_totp.models import TOTPDevice
from rest_framework import permissions, serializers, status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from apps.audit import services as audit
from apps.core.middleware import client_ip
from apps.rbac.services import all_permission_codes, get_grants

from .models import LoginAttempt

User = get_user_model()
MFA_SALT = "shinelight.mfa"
MFA_TOKEN_MAX_AGE = 300


def _set_auth_cookies(response, user):
    refresh = RefreshToken.for_user(user)
    common = {"httponly": True, "secure": settings.AUTH_COOKIE_SECURE, "samesite": settings.AUTH_COOKIE_SAMESITE}
    response.set_cookie(
        settings.AUTH_COOKIE_ACCESS, str(refresh.access_token),
        max_age=int(settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"].total_seconds()), **common,
    )
    response.set_cookie(
        settings.AUTH_COOKIE_REFRESH, str(refresh), path="/api/auth/",
        max_age=int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()), **common,
    )
    return response


def _record_attempt(request, username, user, success, reason=""):
    LoginAttempt.objects.create(
        username=username[:150], user=user, ip_address=client_ip(request),
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:255], success=success, reason=reason,
    )


def _complete_login(request, user):
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login = timezone.now()
    user.save(update_fields=["failed_login_count", "locked_until", "last_login"])
    _record_attempt(request, user.username, user, True)
    audit.log("login", user, actor=user, organization=user.organization)
    response = Response(me_payload(user))
    return _set_auth_cookies(response, user)


def me_payload(user):
    employee = getattr(user, "employee", None)
    grants = get_grants(user)
    org = user.organization
    return {
        "id": user.id,
        "username": user.username,
        "full_name": user.get_full_name() or user.username,
        "email": user.email,
        "must_change_password": user.must_change_password,
        "mfa_enabled": user.mfa_enabled,
        "is_superuser": user.is_superuser,
        "permissions": all_permission_codes(user),
        "scopes": {code: sorted({g.scope for g in gs}) for code, gs in grants.items()},
        "roles": list(user.role_assignments.values_list("role__code", flat=True)),
        "employee": (
            {
                "id": employee.id,
                "staff_number": employee.staff_number,
                "full_name": employee.full_name,
                "department": employee.department.name if employee.department_id else None,
                "job_title": employee.job_title.name if employee.job_title_id else None,
                "photo": employee.photo.url if employee.photo else None,
                "is_manager": employee.direct_reports.exists(),
            }
            if employee
            else None
        ),
        "organization": (
            {
                "id": org.id,
                "name": org.name,
                "currency": org.currency,
                "features": list(org.features.filter(enabled=True).values_list("code", flat=True)),
                "session_timeout_minutes": org.settings.get("session_timeout_minutes", 30),
            }
            if org
            else None
        ),
    }


@method_decorator(ensure_csrf_cookie, name="dispatch")
class CsrfView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request):
        return Response({"detail": "ok"})


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(trim_whitespace=False)


class LoginView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    def post(self, request):
        s = LoginSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        username = s.validated_data["username"].strip()
        candidate = User.objects.filter(username__iexact=username).first() or User.objects.filter(
            email__iexact=username
        ).first()
        if candidate and candidate.is_locked:
            _record_attempt(request, username, candidate, False, "locked")
            return Response({"detail": "Account temporarily locked. Try again later."}, status=status.HTTP_423_LOCKED)
        user = authenticate(request, username=candidate.username if candidate else username,
                            password=s.validated_data["password"])
        if user is None:
            if candidate:
                candidate.failed_login_count += 1
                if candidate.failed_login_count >= settings.LOGIN_MAX_FAILURES:
                    candidate.locked_until = timezone.now() + timedelta(minutes=settings.LOGIN_LOCKOUT_MINUTES)
                candidate.save(update_fields=["failed_login_count", "locked_until"])
                audit.log("login_failed", candidate, actor=None, organization=candidate.organization)
            _record_attempt(request, username, candidate, False, "bad_credentials")
            return Response({"detail": "Invalid username or password."}, status=status.HTTP_401_UNAUTHORIZED)

        if user.requires_mfa():
            token = signing.dumps({"uid": user.id}, salt=MFA_SALT)
            has_device = TOTPDevice.objects.filter(user=user, confirmed=True).exists()
            return Response({"mfa_required": True, "mfa_setup_required": not has_device and not user.phone,
                             "mfa_methods": (["totp"] if has_device else []) + (["sms"] if user.phone else []),
                             "mfa_token": token})
        return _complete_login(request, user)


def _user_from_mfa_token(token):
    try:
        data = signing.loads(token, salt=MFA_SALT, max_age=MFA_TOKEN_MAX_AGE)
    except signing.BadSignature as exc:
        raise serializers.ValidationError({"detail": "MFA session expired. Sign in again."}) from exc
    return User.objects.get(pk=data["uid"])


class MfaSetupView(APIView):
    """Create (or re-create) an unconfirmed TOTP device and return its QR code."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        user = _user_from_mfa_token(request.data.get("mfa_token", ""))
        if TOTPDevice.objects.filter(user=user, confirmed=True).exists():
            return Response({"detail": "Authenticator already configured."}, status=400)
        TOTPDevice.objects.filter(user=user, confirmed=False).delete()
        device = TOTPDevice.objects.create(user=user, name="authenticator", confirmed=False)
        img = qrcode.make(device.config_url, image_factory=qrcode.image.svg.SvgImage)
        buf = io.BytesIO()
        img.save(buf)
        return Response({"otpauth_url": device.config_url,
                         "qr_svg": "data:image/svg+xml;base64," + base64.b64encode(buf.getvalue()).decode()})


class MfaSmsView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    def post(self, request):
        from apps.notifications.sms import send_sms

        user = _user_from_mfa_token(request.data.get("mfa_token", ""))
        if not user.phone:
            return Response({"detail": "No phone number on file."}, status=400)
        code = f"{secrets.randbelow(1000000):06d}"
        cache.set(f"mfa_sms:{user.id}", code, 300)
        send_sms(user.phone, f"Your ShineLight HRM sign-in code is {code}. It expires in 5 minutes.")
        return Response({"detail": "Code sent."})


class MfaVerifyView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    def post(self, request):
        user = _user_from_mfa_token(request.data.get("mfa_token", ""))
        code = str(request.data.get("code", "")).strip()
        method = request.data.get("method", "totp")
        ok = False
        if method == "sms":
            expected = cache.get(f"mfa_sms:{user.id}")
            ok = bool(expected) and secrets.compare_digest(expected, code)
            if ok:
                cache.delete(f"mfa_sms:{user.id}")
        else:
            for device in TOTPDevice.objects.filter(user=user):
                if device.verify_token(code):
                    if not device.confirmed:
                        device.confirmed = True
                        device.save(update_fields=["confirmed"])
                    ok = True
                    break
        if not ok:
            _record_attempt(request, user.username, user, False, "bad_mfa")
            return Response({"detail": "Invalid verification code."}, status=status.HTTP_401_UNAUTHORIZED)
        if not user.mfa_enabled:
            user.mfa_enabled = True
            user.save(update_fields=["mfa_enabled"])
        return _complete_login(request, user)


class RefreshView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        raw = request.COOKIES.get(settings.AUTH_COOKIE_REFRESH) or request.data.get("refresh")
        if not raw:
            return Response({"detail": "No refresh token."}, status=401)
        try:
            refresh = RefreshToken(raw)
            user = User.objects.get(pk=refresh["user_id"])
            if not user.is_active:
                raise TokenError("inactive")
            refresh.blacklist()
        except (TokenError, User.DoesNotExist):
            return Response({"detail": "Session expired."}, status=401)
        response = Response({"detail": "refreshed"})
        return _set_auth_cookies(response, user)


class LogoutView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        raw = request.COOKIES.get(settings.AUTH_COOKIE_REFRESH)
        if raw:
            try:
                RefreshToken(raw).blacklist()
            except TokenError:
                pass
        if request.user.is_authenticated:
            audit.log("logout", request.user)
        response = Response({"detail": "Signed out."})
        response.delete_cookie(settings.AUTH_COOKIE_ACCESS)
        response.delete_cookie(settings.AUTH_COOKIE_REFRESH, path="/api/auth/")
        return response


class MeView(APIView):
    def get(self, request):
        return Response(me_payload(request.user))


class ChangePasswordView(APIView):
    def post(self, request):
        user = request.user
        current = request.data.get("current_password", "")
        new = request.data.get("new_password", "")
        if not user.check_password(current):
            return Response({"current_password": ["Current password is incorrect."]}, status=400)
        try:
            password_validation.validate_password(new, user)
        except Exception as exc:  # django ValidationError
            return Response({"new_password": list(getattr(exc, "messages", [str(exc)]))}, status=400)
        user.set_password(new)
        user.must_change_password = False
        user.password_changed_at = timezone.now()
        user.save()
        audit.log("update", user, {"password": "<changed>"})
        return _set_auth_cookies(Response({"detail": "Password changed."}), user)


class PasswordResetRequestView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    def post(self, request):
        email = request.data.get("email", "").strip()
        user = User.objects.filter(email__iexact=email, is_active=True).first() if email else None
        if user:
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            link = f"{settings.FRONTEND_URL}/reset-password?uid={uid}&token={token}"
            send_mail("ShineLight HRM password reset",
                      f"Use this link to reset your password (valid for a limited time):\n{link}\n\n"
                      "If you did not request this, ignore this email.",
                      settings.DEFAULT_FROM_EMAIL, [user.email])
        # Always the same response so accounts cannot be enumerated.
        return Response({"detail": "If the email is registered, a reset link has been sent."})


class PasswordResetConfirmView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        try:
            uid = force_str(urlsafe_base64_decode(request.data.get("uid", "")))
            user = User.objects.get(pk=uid)
        except (ValueError, User.DoesNotExist, TypeError):
            return Response({"detail": "Invalid reset link."}, status=400)
        if not default_token_generator.check_token(user, request.data.get("token", "")):
            return Response({"detail": "Reset link is invalid or has expired."}, status=400)
        new = request.data.get("new_password", "")
        try:
            password_validation.validate_password(new, user)
        except Exception as exc:
            return Response({"new_password": list(getattr(exc, "messages", [str(exc)]))}, status=400)
        user.set_password(new)
        user.must_change_password = False
        user.failed_login_count = 0
        user.locked_until = None
        user.password_changed_at = timezone.now()
        user.save()
        audit.log("update", user, {"password": "<reset>"}, actor=user, organization=user.organization)
        return Response({"detail": "Password reset. You can now sign in."})
