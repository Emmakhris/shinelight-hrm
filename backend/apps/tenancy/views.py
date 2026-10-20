"""Organization settings and system configuration (admin.settings)."""

from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit import services as audit
from apps.core.context import get_current_org
from apps.core.models import ConfigChange, CustomFieldDefinition, NumberSequence, PublicHoliday
from apps.core.serializers import TenantSerializer
from apps.core.views import TenantModelViewSet
from apps.rbac.permissions import require

from .models import Organization, OrganizationFeature


class OrganizationSerializer(serializers.ModelSerializer):
    features = serializers.SerializerMethodField()

    class Meta:
        model = Organization
        exclude = ["is_active", "domain"]
        read_only_fields = ["code", "created_at"]

    def get_features(self, obj):
        enabled = dict(obj.features.values_list("code", "enabled"))
        return [{"code": c, "label": n, "enabled": enabled.get(c, False)} for c, n in OrganizationFeature.FEATURES]


class OrganizationView(APIView):
    def get_permissions(self):
        if self.request.method == "GET":
            return [IsAuthenticated()]
        return [IsAuthenticated(), require("admin.settings")()]

    def get(self, request):
        return Response(OrganizationSerializer(get_current_org()).data)

    def patch(self, request):
        org = get_current_org()
        before = OrganizationSerializer(org).data
        s = OrganizationSerializer(org, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        s.save()
        if "settings" in request.data:
            org.settings = {**before.get("settings", {}), **request.data["settings"]}
            org.save(update_fields=["settings"])
        ConfigChange.objects.create(area="organization", object_repr=org.name, before=before,
                                    after=OrganizationSerializer(org).data)
        return Response(OrganizationSerializer(org).data)


class FeatureToggleView(APIView):
    permission_classes = [IsAuthenticated, require("admin.settings")]

    def post(self, request):
        org = get_current_org()
        code = request.data["code"]
        if code not in dict(OrganizationFeature.FEATURES):
            return Response({"detail": "Unknown feature."}, status=400)
        feat, _ = OrganizationFeature.objects.get_or_create(organization=org, code=code)
        feat.enabled = bool(request.data.get("enabled"))
        feat.save()
        audit.log("config", feat, {"feature": code, "enabled": feat.enabled})
        return Response({"code": code, "enabled": feat.enabled})


def ser(model_cls):
    return type(f"{model_cls.__name__}Serializer", (TenantSerializer,),
                {"Meta": type("Meta", (TenantSerializer.Meta,), {"model": model_cls})})


class HolidayViewSet(TenantModelViewSet):
    queryset = PublicHoliday.objects.all()
    serializer_class = ser(PublicHoliday)
    perm_module = "admin"
    perm_map = {"list": None, "retrieve": None}
    perm_write = "admin.settings"
    pagination_class = None

    def get_queryset(self):
        qs = super().get_queryset()
        year = self.request.query_params.get("year")
        if year:
            qs = qs.filter(date__year=year) | qs.filter(is_recurring=True)
        return qs

    @action(detail=False, methods=["post"], url_path="seed-ghana")
    def seed_ghana(self, request):
        from apps.core.ghana import seed_public_holidays

        n = seed_public_holidays(int(request.data.get("year")))
        return Response({"created": n})


class NumberSequenceViewSet(TenantModelViewSet):
    queryset = NumberSequence.objects.all()
    serializer_class = ser(NumberSequence)
    perm_module = "admin"
    perm_read = "admin.settings"
    perm_write = "admin.settings"
    pagination_class = None


class CustomFieldViewSet(TenantModelViewSet):
    queryset = CustomFieldDefinition.objects.all()
    serializer_class = ser(CustomFieldDefinition)
    perm_module = "admin"
    perm_map = {"list": None, "retrieve": None}
    perm_write = "admin.settings"
    filterset_fields = ["entity"]
    pagination_class = None


class ConfigChangeViewSet(TenantModelViewSet):
    queryset = ConfigChange.objects.all()
    serializer_class = ser(ConfigChange)
    perm_module = "admin"
    perm_read = "admin.settings"
    http_method_names = ["get"]
