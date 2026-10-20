from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.permissions import BasePermission
from rest_framework.response import Response

from apps.core.serializers import TenantSerializer
from apps.core.views import TenantModelViewSet
from apps.employees.models import Employee

from . import services
from .models import CompetencyRecord, CompetencyRequirement, ProfessionalLicense


class HospitalFeature(BasePermission):
    message = "The hospital module is not enabled for this organization."

    def has_permission(self, request, view):
        org = request.user.organization
        return bool(org and org.has_feature("hospital"))


class HospitalViewSet(TenantModelViewSet):
    perm_module = "hospital"
    perm_write = "hospital.manage"

    def get_permissions(self):
        return super().get_permissions() + [HospitalFeature()]


class LicenseSerializer(TenantSerializer):
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    regulator_label = serializers.CharField(source="get_regulator_display", read_only=True)

    class Meta(TenantSerializer.Meta):
        model = ProfessionalLicense
        read_only_fields = TenantSerializer.Meta.read_only_fields + ["verified_by", "verified_at"]


class LicenseViewSet(HospitalViewSet):
    queryset = ProfessionalLicense.objects.select_related("employee")
    serializer_class = LicenseSerializer
    scope_prefix = "employee__"
    filterset_fields = ["employee", "status", "regulator"]
    search_fields = ["registration_number", "employee__first_name", "employee__last_name"]

    @action(detail=True, methods=["post"])
    def verify(self, request, pk=None):
        lic = self.get_object()
        lic.status = "active"
        lic.verified_by = request.user
        lic.verified_at = timezone.now()
        lic.verification_note = request.data.get("note", "")
        lic.save()
        return Response(self.get_serializer(lic).data)


class RequirementViewSet(HospitalViewSet):
    queryset = CompetencyRequirement.objects.prefetch_related("job_titles")
    serializer_class = type("ReqSer", (TenantSerializer,), {"Meta": type("Meta", (TenantSerializer.Meta,),
                                                                         {"model": CompetencyRequirement})})
    pagination_class = None


class RecordViewSet(HospitalViewSet):
    queryset = CompetencyRecord.objects.select_related("employee", "requirement")
    serializer_class = type("RecSer", (TenantSerializer,), {
        "Meta": type("Meta", (TenantSerializer.Meta,), {"model": CompetencyRecord}),
        "requirement_name": serializers.CharField(source="requirement.name", read_only=True),
        "employee_name": serializers.CharField(source="employee.full_name", read_only=True)})
    scope_prefix = "employee__"
    filterset_fields = ["employee", "requirement"]


class CredentialViewSet(HospitalViewSet):
    http_method_names = ["get"]

    def list(self, request):
        dept = request.query_params.get("department")
        from apps.organization.models import Department

        return Response(services.competency_matrix(Department.objects.filter(pk=dept).first() if dept else None))

    @action(detail=False)
    def check(self, request):
        emp = Employee.objects.get(pk=request.query_params["employee"])
        return Response({"employee": emp.full_name, "issues": services.credential_issues(emp)})
