"""User account administration (admin.users)."""

import secrets

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django_otp.plugins.otp_totp.models import TOTPDevice
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.audit import services as audit
from apps.core.context import get_current_org
from apps.rbac.permissions import RBACPermission, require

from .models import LoginAttempt

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    roles = serializers.SerializerMethodField()
    employee_id = serializers.SerializerMethodField()
    is_locked = serializers.BooleanField(read_only=True)

    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "email", "phone", "is_active", "mfa_enabled",
                  "must_change_password", "last_login", "date_joined", "roles", "employee_id", "is_locked"]
        read_only_fields = ["last_login", "date_joined", "mfa_enabled"]

    def get_roles(self, obj):
        return [{"id": ra.id, "role": ra.role.code, "name": ra.role.name, "scope": ra.effective_scope}
                for ra in obj.role_assignments.select_related("role")]

    def get_employee_id(self, obj):
        emp = getattr(obj, "employee", None)
        return emp.id if emp else None


def create_user_account(username, email="", first_name="", last_name="", phone="", password=None, notify=True):
    org = get_current_org()
    temp = password or secrets.token_urlsafe(10)
    user = User.objects.create_user(username=username, email=email, password=temp, first_name=first_name,
                                    last_name=last_name, phone=phone, organization=org,
                                    must_change_password=password is None)
    if notify and email and password is None:
        send_mail("Your ShineLight HRM account",
                  f"Hello {first_name},\n\nAn account has been created for you.\nUsername: {username}\n"
                  f"Temporary password: {temp}\nSign in at {settings.FRONTEND_URL} and change it immediately.",
                  settings.DEFAULT_FROM_EMAIL, [email])
    return user, temp


class UserViewSet(viewsets.ModelViewSet):
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated, RBACPermission]
    perm_module = "admin"
    perm_read = "admin.users"
    perm_write = "admin.users"
    search_fields = ["username", "first_name", "last_name", "email"]
    filterset_fields = ["is_active"]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        return User.objects.filter(organization=get_current_org()).prefetch_related("role_assignments__role")

    def create(self, request, *args, **kwargs):
        s = self.get_serializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        user, _ = create_user_account(d["username"], d.get("email", ""), d.get("first_name", ""),
                                      d.get("last_name", ""), d.get("phone", ""))
        audit.log("create", user, {"username": user.username})
        return Response(self.get_serializer(user).data, status=201)

    @action(detail=True, methods=["post"])
    def unlock(self, request, pk=None):
        user = self.get_object()
        user.failed_login_count = 0
        user.locked_until = None
        user.save(update_fields=["failed_login_count", "locked_until"])
        audit.log("update", user, {"unlocked": True})
        return Response({"detail": "Account unlocked."})

    @action(detail=True, methods=["post"])
    def reset_mfa(self, request, pk=None):
        user = self.get_object()
        TOTPDevice.objects.filter(user=user).delete()
        user.mfa_enabled = False
        user.save(update_fields=["mfa_enabled"])
        audit.log("update", user, {"mfa": "<reset>"})
        return Response({"detail": "MFA reset; the user must enrol again at next sign-in."})

    @action(detail=True, methods=["post"])
    def reset_password(self, request, pk=None):
        user = self.get_object()
        temp = secrets.token_urlsafe(10)
        user.set_password(temp)
        user.must_change_password = True
        user.save()
        if user.email:
            send_mail("ShineLight HRM password reset", f"Your temporary password is: {temp}",
                      settings.DEFAULT_FROM_EMAIL, [user.email])
        audit.log("update", user, {"password": "<admin reset>"})
        return Response({"detail": "Temporary password emailed to the user." if user.email
                         else "User has no email; share the temporary password securely.",
                         "temporary_password": None if user.email else temp})

    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        user = self.get_object()
        if user == request.user:
            return Response({"detail": "You cannot deactivate your own account."}, status=400)
        user.is_active = False
        user.save(update_fields=["is_active"])
        audit.log("update", user, {"is_active": False})
        return Response({"detail": "Account deactivated."})


class UserLookupViewSet(viewsets.ReadOnlyModelViewSet):
    """Minimal active-user list (id + name) for pickers such as delegation of authority."""

    permission_classes = [IsAuthenticated]
    search_fields = ["username", "first_name", "last_name"]

    class _S(serializers.ModelSerializer):
        full_name = serializers.CharField(source="__str__", read_only=True)

        class Meta:
            model = User
            fields = ["id", "username", "full_name"]

    serializer_class = _S

    def get_queryset(self):
        return User.objects.filter(organization=get_current_org(), is_active=True).order_by("first_name")


class LoginAttemptSerializer(serializers.ModelSerializer):
    class Meta:
        model = LoginAttempt
        fields = ["id", "username", "user", "ip_address", "user_agent", "success", "reason", "timestamp"]


class LoginAttemptViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = LoginAttemptSerializer
    permission_classes = [IsAuthenticated, require("admin.users")]
    filterset_fields = ["success", "username"]

    def get_queryset(self):
        return LoginAttempt.objects.filter(user__organization=get_current_org()) | LoginAttempt.objects.filter(
            user__isnull=True
        )
