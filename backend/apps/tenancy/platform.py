"""Platform operator console (/api/platform/). Operators manage organizations, plans and features; they
have no organization, so every HR endpoint refuses them, and nothing here returns HR records."""

from django.conf import settings
from rest_framework import permissions, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.audit import services as audit
from apps.core.exceptions import BusinessRuleError

from . import services
from .models import Organization, OrganizationFeature, Plan


class IsPlatformAdmin(permissions.BasePermission):
    message = "Platform operators only."

    def has_permission(self, request, view):
        return services.is_platform_admin(request.user)


class PlanSerializer(serializers.ModelSerializer):
    organizations = serializers.SerializerMethodField()

    class Meta:
        model = Plan
        fields = "__all__"

    def get_organizations(self, obj):
        return obj.organizations.count()

    def validate_features(self, value):
        known = dict(OrganizationFeature.FEATURES)
        unknown = [v for v in value if v not in known]
        if unknown:
            raise serializers.ValidationError(f"Unknown features: {', '.join(unknown)}")
        return value


class PlanViewSet(viewsets.ModelViewSet):
    queryset = Plan.objects.all()
    serializer_class = PlanSerializer
    permission_classes = [IsPlatformAdmin]
    pagination_class = None


class OrganizationAdminSerializer(serializers.ModelSerializer):
    plan_name = serializers.CharField(source="plan.name", read_only=True, default=None)
    usage = serializers.SerializerMethodField()
    login_url = serializers.SerializerMethodField()
    features = serializers.SerializerMethodField()

    class Meta:
        model = Organization
        fields = ["id", "name", "code", "legal_name", "email", "phone", "domain", "status", "is_active",
                  "suspended_reason", "plan", "plan_name", "trial_ends_at", "created_via", "created_at", "usage",
                  "login_url", "features"]
        read_only_fields = ["code", "status", "is_active", "suspended_reason", "created_via", "created_at"]

    def get_usage(self, obj):
        return services.usage(obj)

    def get_login_url(self, obj):
        return services.login_url(obj)

    def get_features(self, obj):
        enabled = dict(obj.features.values_list("code", "enabled"))
        allowed = set(obj.plan.features) if obj.plan_id else None
        return [{"code": c, "label": n, "enabled": enabled.get(c, False),
                 "in_plan": allowed is None or c in allowed} for c, n in OrganizationFeature.FEATURES]

    def validate_domain(self, value):
        value = (value or "").strip().lower()
        if value and Organization.objects.filter(domain__iexact=value).exclude(pk=getattr(self.instance, "pk", None)).exists():
            raise serializers.ValidationError("Another organization already uses this domain.")
        return value


class CreateOrganizationSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    code = serializers.CharField(max_length=40)
    admin_username = serializers.CharField(max_length=150)
    admin_email = serializers.EmailField()
    plan = serializers.PrimaryKeyRelatedField(queryset=Plan.objects.all(), required=False, allow_null=True)
    status = serializers.ChoiceField(choices=["trial", "active"], default="active")


class OrganizationAdminViewSet(viewsets.ModelViewSet):
    queryset = Organization.objects.select_related("plan").order_by("name")
    serializer_class = OrganizationAdminSerializer
    permission_classes = [IsPlatformAdmin]
    http_method_names = ["get", "post", "patch", "head", "options"]
    pagination_class = None

    def create(self, request, *args, **kwargs):
        s = CreateOrganizationSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        org, _ = services.provision(d["name"], d["code"], d["admin_username"], d["admin_email"], plan=d.get("plan"),
                                    status=d["status"], created_via="platform")
        audit.log("config", org, {"platform": "organization_created", "plan": org.plan_id},
                  organization=org, object_repr=org.name)
        return Response(OrganizationAdminSerializer(org).data, status=201)

    def perform_update(self, serializer):
        before_plan = serializer.instance.plan_id
        org = serializer.save()
        if org.plan_id != before_plan:
            services.apply_plan(org, org.plan)
        services.forget(org)
        audit.log("config", org, {"platform": "organization_updated",
                                  **{k: str(v) for k, v in serializer.validated_data.items()}},
                  organization=org, object_repr=org.name)

    @action(detail=True, methods=["post"])
    def status(self, request, pk=None):
        org = self.get_object()
        new = request.data.get("status")
        if new not in ("trial", "active", "suspended", "cancelled"):
            raise BusinessRuleError("Unknown status.")
        services.set_status(org, new, str(request.data.get("reason", ""))[:200])
        audit.log("config", org, {"platform": "status", "status": new}, organization=org, object_repr=org.name)
        return Response(OrganizationAdminSerializer(org).data)

    @action(detail=True, methods=["post"])
    def feature(self, request, pk=None):
        org = self.get_object()
        code, enabled = request.data.get("code"), bool(request.data.get("enabled"))
        if code not in dict(OrganizationFeature.FEATURES):
            raise BusinessRuleError("Unknown feature.")
        if enabled:
            services.check_feature_allowed(org, code)
        OrganizationFeature.objects.update_or_create(organization=org, code=code, defaults={"enabled": enabled})
        audit.log("config", org, {"platform": "feature", "feature": code, "enabled": enabled},
                  organization=org, object_repr=org.name)
        return Response(OrganizationAdminSerializer(org).data)


# ---------------------------------------------------------------- public
class TenantInfoView(APIView):
    """What the login page shows for this address: the organization's name, logo and whether SSO is set up."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request):
        from apps.sso.models import IdentityProvider

        org = services.request_tenant(request)
        if org is None:
            return Response({"organization": None, "signup": bool(getattr(settings, "SAAS_SIGNUP_ENABLED", False))})
        return Response({"organization": {
            "name": org.name, "code": org.code, "logo": org.logo.url if org.logo else None, "active": org.is_active,
            "sso": IdentityProvider.all_objects.filter(organization=org, is_active=True).exists()},
            "signup": False})


class SignupSerializer(serializers.Serializer):
    organization_name = serializers.CharField(max_length=200)
    code = serializers.CharField(max_length=40)
    admin_name = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(min_length=10, write_only=True, trim_whitespace=False)
    accept_terms = serializers.BooleanField()


class SignupView(APIView):
    """Self-service trial sign-up. Off unless SAAS_SIGNUP_ENABLED is set."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "apply"

    def get(self, request):
        return Response({"enabled": bool(getattr(settings, "SAAS_SIGNUP_ENABLED", False)),
                         "base_domain": getattr(settings, "SAAS_BASE_DOMAIN", "")})

    def post(self, request):
        from django.contrib.auth import password_validation

        if not getattr(settings, "SAAS_SIGNUP_ENABLED", False):
            return Response({"detail": "Sign-up is not available."}, status=404)
        s = SignupSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        if not d["accept_terms"]:
            raise BusinessRuleError("Please accept the terms of service and data processing agreement.")
        password_validation.validate_password(d["password"])
        org, admin = services.provision(d["organization_name"], d["code"], d["username"], d["email"],
                                        admin_password=d["password"], status="trial", created_via="signup")
        first, _, last = d["admin_name"].partition(" ")
        admin.first_name, admin.last_name = first, last
        admin.save(update_fields=["first_name", "last_name"])
        audit.log("config", org, {"platform": "signup"}, organization=org, actor=admin, object_repr=org.name)
        return Response({"login_url": services.login_url(org), "trial_ends_at": org.trial_ends_at}, status=201)
