from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import BusinessRuleError
from apps.core.serializers import DisplayField, TenantSerializer
from apps.core.views import TenantModelViewSet
from apps.employees.models import Employee
from apps.organization.models import Location
from apps.rbac.services import has_perm

from . import services
from .models import Asset, AssetCategory, Assignment


class CategorySerializer(TenantSerializer):
    class Meta(TenantSerializer.Meta):
        model = AssetCategory


class CategoryViewSet(TenantModelViewSet):
    queryset = AssetCategory.objects.all()
    serializer_class = CategorySerializer
    perm_module = "assets"
    perm_write = "assets.manage"
    pagination_class = None


class AssetSerializer(TenantSerializer):
    category = serializers.PrimaryKeyRelatedField(queryset=AssetCategory.objects)
    location = serializers.PrimaryKeyRelatedField(queryset=Location.objects, required=False, allow_null=True)
    category_name = DisplayField("category")
    holder_name = DisplayField("holder")
    location_name = DisplayField("location")
    history = serializers.SerializerMethodField()

    class Meta(TenantSerializer.Meta):
        model = Asset
        read_only_fields = TenantSerializer.Meta.read_only_fields + ["holder"]

    def get_history(self, obj):
        if self.context.get("view") and self.context["view"].action != "retrieve":
            return None
        return [{"employee": a.employee.full_name, "issued_on": a.issued_on, "returned_on": a.returned_on,
                 "condition_in": a.condition_in} for a in obj.assignments.select_related("employee")]


class AssetViewSet(TenantModelViewSet):
    queryset = Asset.objects.select_related("category", "holder", "location")
    serializer_class = AssetSerializer
    perm_module = "assets"
    perm_write = "assets.manage"
    filterset_fields = ["status", "category", "holder", "location"]
    search_fields = ["tag", "serial_number", "description", "holder__first_name", "holder__last_name",
                     "external_ref"]

    def perform_update(self, serializer):
        if serializer.instance.status == "assigned" and serializer.validated_data.get("status") not in (None,
                                                                                                         "assigned"):
            raise BusinessRuleError("Receive the asset back before changing its status.")
        serializer.save()


class AssignmentSerializer(TenantSerializer):
    asset = serializers.PrimaryKeyRelatedField(queryset=Asset.objects, required=False, allow_null=True)
    category = serializers.PrimaryKeyRelatedField(queryset=AssetCategory.objects, required=False)
    employee = serializers.PrimaryKeyRelatedField(queryset=Employee.objects)
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    department_name = serializers.CharField(source="employee.department.name", read_only=True, default=None)
    category_name = DisplayField("category")
    tag = serializers.CharField(source="asset.tag", read_only=True, default=None)
    serial_number = serializers.CharField(source="asset.serial_number", read_only=True, default=None)
    issued_by_name = DisplayField("issued_by")
    is_mine = serializers.SerializerMethodField()
    returnable = serializers.BooleanField(source="category.is_returnable", read_only=True)

    class Meta(TenantSerializer.Meta):
        model = Assignment
        read_only_fields = TenantSerializer.Meta.read_only_fields + [
            "issued_on", "issued_by", "acknowledged_at", "returned_on", "condition_in", "received_by",
            "incident_report", "recovery_amount", "recovery_status"]

    def get_is_mine(self, obj):
        return obj.employee.user_id == self.context["request"].user.pk


class AssignmentViewSet(TenantModelViewSet):
    queryset = Assignment.objects.select_related("employee__department", "asset", "category", "issued_by")
    serializer_class = AssignmentSerializer
    perm_module = "assets"
    perm_write = "assets.manage"
    perm_map = {"list": None, "retrieve": None, "acknowledge": None, "report": None}
    http_method_names = ["get", "post", "head", "options"]
    filterset_fields = ["employee", "category", "recovery_status"]
    search_fields = ["item", "asset__tag", "employee__first_name", "employee__last_name"]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if self.request.query_params.get("mine") == "1" or not has_perm(user, "assets.view"):
            qs = qs.filter(employee__user=user)
        if self.request.query_params.get("open") == "1":
            qs = qs.filter(returned_on__isnull=True)
        return qs

    def perform_create(self, serializer):
        d = serializer.validated_data
        serializer.instance = services.issue(self.request.user, d["employee"], asset=d.get("asset"),
                                             category=d.get("category"), item=d.get("item", ""),
                                             quantity=d.get("quantity", 1), due_back=d.get("due_back"),
                                             condition=d.get("condition_out", "good"), notes=d.get("notes", ""))

    @action(detail=True, methods=["post"])
    def acknowledge(self, request, pk=None):
        return Response(self.get_serializer(services.acknowledge(self.get_object(), request.user)).data)

    @action(detail=True, methods=["post"])
    def report(self, request, pk=None):
        a = services.report_incident(self.get_object(), request.user, request.data.get("kind", ""),
                                     request.data.get("description", ""))
        return Response(self.get_serializer(a).data)

    @action(detail=True, methods=["post"])
    def receive(self, request, pk=None):
        a = services.receive(self.get_object(), request.user, request.data.get("condition", ""),
                             request.data.get("recovery_amount"), request.data.get("notes", ""),
                             bool(request.data.get("to_payroll")))
        return Response(self.get_serializer(a).data)

    @action(detail=True, methods=["post"])
    def transfer(self, request, pk=None):
        emp = Employee.objects.filter(pk=request.data.get("employee")).first()
        if emp is None:
            raise NotFound()
        a = services.transfer(self.get_object(), request.user, emp, request.data.get("notes", ""))
        return Response(self.get_serializer(a).data)

    @action(detail=True, methods=["post"], url_path="set-recovery")
    def set_recovery(self, request, pk=None):
        a = self.get_object()
        status = request.data.get("recovery_status")
        if status not in ("paid", "waived") or a.recovery_status != "pending":
            raise BusinessRuleError("Mark a pending recovery as paid or waived.")
        a.recovery_status = status
        a.notes = "\n".join(x for x in (a.notes, request.data.get("notes", "")) if x)
        a.save(update_fields=["recovery_status", "notes", "updated_at"])
        return Response(self.get_serializer(a).data)


class DashboardView(APIView):
    def get(self, request):
        if not has_perm(request.user, "assets.view"):
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied()
        return Response(services.recovery_dashboard())
