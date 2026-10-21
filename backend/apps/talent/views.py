from django.db.models import Q
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import BusinessRuleError
from apps.core.serializers import DisplayField, TenantSerializer
from apps.core.views import TenantModelViewSet
from apps.employees.models import Employee
from apps.learning.models import Course
from apps.organization.models import Department, JobTitle, Position
from apps.rbac.services import has_perm, scope_queryset

from . import services
from .models import (
    POTENTIAL_CRITERIA,
    CareerPath,
    PlanLine,
    Scenario,
    SuccessionPlan,
    Successor,
    TalentAssessment,
    TalentProfile,
    WorkforcePlan,
)


def _visible_employees(user):
    """Employees whose talent data the user may see: own team (as supervisor) plus talent.view scope."""
    qs = Employee.objects.all()
    cond = Q(supervisor__user=user)
    if has_perm(user, "talent.view"):
        cond |= Q(pk__in=scope_queryset(user, qs, "talent.view", "").values("pk"))
    return qs.filter(cond)


# ---------------------------------------------------------------- profiles
class ProfileSerializer(TenantSerializer):
    preferred_roles = serializers.PrimaryKeyRelatedField(queryset=JobTitle.objects, many=True, required=False)
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    job_title = serializers.CharField(source="employee.job_title.name", read_only=True, default=None)

    class Meta(TenantSerializer.Meta):
        model = TalentProfile
        read_only_fields = TenantSerializer.Meta.read_only_fields + ["employee", "updated_by_employee_at"]


class MyProfileView(APIView):
    def _profile(self, request):
        emp = getattr(request.user, "employee", None)
        if emp is None:
            raise BusinessRuleError("Your account is not linked to an employee record.")
        return TalentProfile.objects.get_or_create(employee=emp)[0]

    def get(self, request):
        p = self._profile(request)
        return Response({"profile": ProfileSerializer(p).data,
                         "eligibility": services.promotion_eligibility(p.employee),
                         "years_in_role": services.years_in_role(p.employee)})

    def patch(self, request):
        p = self._profile(request)
        s = ProfileSerializer(p, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        s.save()
        services.touch_profile(p)
        return Response(ProfileSerializer(p).data)


class EmployeeTalentView(APIView):
    """A person's talent picture for their supervisor or the talent team."""

    def get(self, request, employee_id):
        emp = _visible_employees(request.user).filter(pk=employee_id).first()
        if emp is None:
            raise NotFound()
        profile = TalentProfile.objects.filter(employee=emp).first()
        return Response({
            "employee": {"id": emp.id, "name": emp.full_name, "job_title": emp.job_title.name if emp.job_title_id
                         else None, "years_in_role": services.years_in_role(emp)},
            "profile": ProfileSerializer(profile).data if profile else None,
            "suggested_performance": services.suggested_performance(emp),
            "assessments": AssessmentSerializer(emp.talent_assessments.all(), many=True).data,
            "eligibility": services.promotion_eligibility(emp),
            "succession_slots": [{"position": s.plan.position.code, "title": s.plan.position.job_title.name,
                                  "readiness": s.get_readiness_display()}
                                 for s in emp.succession_slots.select_related("plan__position__job_title")],
        })


# ---------------------------------------------------------------- talent reviews
class AssessmentSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    department = serializers.CharField(source="employee.department.name", read_only=True, default=None)
    box = serializers.IntegerField(read_only=True)
    box_label = serializers.SerializerMethodField()
    assessed_by_name = DisplayField("assessed_by")

    class Meta:
        model = TalentAssessment
        fields = ["id", "employee", "employee_name", "department", "period", "performance", "potential", "box",
                  "box_label", "criteria", "rationale", "flight_risk", "assessed_by_name", "calibrated", "created_at"]

    def get_box_label(self, obj):
        return services.BOX_LABELS[obj.box]


class AssessmentViewSet(TenantModelViewSet):
    queryset = TalentAssessment.objects.select_related("employee__department", "assessed_by")
    serializer_class = AssessmentSerializer
    perm_module = "talent"
    perm_map = {k: None for k in ("list", "retrieve", "create", "grid", "criteria")}
    perm_map.update({"calibrate": "talent.manage"})
    http_method_names = ["get", "post", "head", "options"]
    filterset_fields = ["period", "employee", "performance", "potential", "flight_risk"]

    def get_queryset(self):
        return super().get_queryset().filter(employee__in=_visible_employees(self.request.user))

    def create(self, request, *args, **kwargs):
        emp = Employee.objects.filter(pk=request.data.get("employee")).first()
        if emp is None:
            raise BusinessRuleError("Choose the employee.")
        a = services.assess(request.user, emp, request.data.get("period", ""), request.data.get("performance", 0),
                            request.data.get("potential", 0), request.data.get("criteria") or {},
                            request.data.get("rationale", ""), request.data.get("flight_risk", "low"))
        return Response(self.get_serializer(a).data, status=201)

    @action(detail=False)
    def grid(self, request):
        period = request.query_params.get("period")
        if not period:
            latest = self.get_queryset().order_by("-created_at").first()
            period = latest.period if latest else ""
        return Response({"period": period, "boxes": services.nine_box(period, self.get_queryset()),
                         "periods": sorted(set(self.get_queryset().values_list("period", flat=True)), reverse=True)})

    @action(detail=False)
    def criteria(self, request):
        return Response([{"key": k, "label": v} for k, v in POTENTIAL_CRITERIA])

    @action(detail=True, methods=["post"])
    def calibrate(self, request, pk=None):
        a = self.get_object()
        for f in ("performance", "potential"):
            if request.data.get(f) not in (None, ""):
                setattr(a, f, int(request.data[f]))
        if request.data.get("note"):
            a.rationale += f"\n\nCalibration: {request.data['note']}"
        a.calibrated = True
        a.save()
        return Response(self.get_serializer(a).data)


# ---------------------------------------------------------------- succession
class SuccessorSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    job_title = serializers.CharField(source="employee.job_title.name", read_only=True, default=None)
    readiness_label = serializers.CharField(source="get_readiness_display", read_only=True)

    class Meta:
        model = Successor
        fields = ["id", "employee", "employee_name", "job_title", "readiness", "readiness_label",
                  "development_actions", "rank"]


class PlanSerializer(TenantSerializer):
    position = serializers.PrimaryKeyRelatedField(queryset=Position.objects)
    position_label = DisplayField("position")
    successors = SuccessorSerializer(many=True, read_only=True)

    class Meta(TenantSerializer.Meta):
        model = SuccessionPlan
        read_only_fields = TenantSerializer.Meta.read_only_fields + ["last_reviewed"]


class SuccessionViewSet(TenantModelViewSet):
    queryset = SuccessionPlan.objects.select_related("position__job_title").prefetch_related("successors__employee")
    serializer_class = PlanSerializer
    perm_module = "talent"
    perm_read = "talent.view"
    perm_write = "talent.manage"
    perm_map = {"risk": "talent.view"}
    pagination_class = None

    @action(detail=True, methods=["post"], url_path="successors")
    def add(self, request, pk=None):
        plan = self.get_object()
        emp = Employee.objects.filter(pk=request.data.get("employee")).first()
        if emp is None:
            raise BusinessRuleError("Choose the successor.")
        services.add_successor(request.user, plan, emp, request.data.get("readiness", ""),
                               request.data.get("development_actions", ""), int(request.data.get("rank") or 1))
        return Response(self.get_serializer(plan).data)

    @action(detail=True, methods=["post"], url_path=r"successors/(?P<sid>\d+)/remove")
    def remove(self, request, pk=None, sid=None):
        plan = self.get_object()
        plan.successors.filter(pk=sid).delete()
        return Response(self.get_serializer(plan).data)

    @action(detail=False)
    def risk(self, request):
        return Response(services.succession_risk())


class CareerPathSerializer(TenantSerializer):
    from_title = serializers.PrimaryKeyRelatedField(queryset=JobTitle.objects)
    to_title = serializers.PrimaryKeyRelatedField(queryset=JobTitle.objects)
    required_courses = serializers.PrimaryKeyRelatedField(queryset=Course.objects, many=True, required=False)
    from_title_name = DisplayField("from_title")
    to_title_name = DisplayField("to_title")

    class Meta(TenantSerializer.Meta):
        model = CareerPath

    def validate(self, data):
        if data.get("from_title") and data.get("from_title") == data.get("to_title"):
            raise serializers.ValidationError("A path must lead to a different role.")
        return data


class CareerPathViewSet(TenantModelViewSet):
    """Published progression requirements - readable by everyone (transparency)."""

    queryset = CareerPath.objects.select_related("from_title", "to_title").prefetch_related("required_courses")
    serializer_class = CareerPathSerializer
    perm_module = "talent"
    perm_map = {"list": None, "retrieve": None}
    perm_write = "talent.manage"
    filterset_fields = ["from_title", "to_title"]
    pagination_class = None


# ---------------------------------------------------------------- workforce planning
class LineSerializer(TenantSerializer):
    plan = serializers.PrimaryKeyRelatedField(queryset=WorkforcePlan.objects)
    department = serializers.PrimaryKeyRelatedField(queryset=Department.objects)
    job_title = serializers.PrimaryKeyRelatedField(queryset=JobTitle.objects, required=False, allow_null=True)
    department_name = DisplayField("department")
    job_title_name = DisplayField("job_title", fallback="All roles")

    class Meta(TenantSerializer.Meta):
        model = PlanLine


class ScenarioSerializer(TenantSerializer):
    plan = serializers.PrimaryKeyRelatedField(queryset=WorkforcePlan.objects)

    class Meta(TenantSerializer.Meta):
        model = Scenario


class WorkforcePlanSerializer(TenantSerializer):
    lines = LineSerializer(many=True, read_only=True)
    scenarios = ScenarioSerializer(many=True, read_only=True)

    class Meta(TenantSerializer.Meta):
        model = WorkforcePlan
        read_only_fields = TenantSerializer.Meta.read_only_fields + ["status"]


class WorkforcePlanViewSet(TenantModelViewSet):
    queryset = WorkforcePlan.objects.prefetch_related("lines__department", "lines__job_title", "scenarios")
    serializer_class = WorkforcePlanSerializer
    perm_module = "planning"
    perm_read = "planning.view"
    perm_write = "planning.manage"
    perm_map = {"project": "planning.view"}

    def perform_update(self, serializer):
        if serializer.instance.status == "approved":
            raise BusinessRuleError("Approved plans are read-only; copy it to make changes.")
        serializer.save()

    @action(detail=True)
    def project(self, request, pk=None):
        plan = self.get_object()
        sid = request.query_params.get("scenario")
        scenario = plan.scenarios.filter(pk=sid).first() if sid else None
        return Response(services.run_scenario(plan, scenario))

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        from apps.workflow import engine

        plan = self.get_object()
        if plan.status != "draft" or not plan.lines.exists():
            raise BusinessRuleError("Add plan lines to a draft plan before submitting.")
        engine.start(plan, "workforce_plan", request.user)
        return Response({"detail": "Submitted for approval."})


class LineViewSet(TenantModelViewSet):
    queryset = PlanLine.objects.select_related("department", "job_title")
    serializer_class = LineSerializer
    perm_module = "planning"
    perm_read = "planning.view"
    perm_write = "planning.manage"
    filterset_fields = ["plan"]
    pagination_class = None

    def perform_create(self, serializer):
        if serializer.validated_data["plan"].status == "approved":
            raise BusinessRuleError("Approved plans are read-only.")
        serializer.save()


class ScenarioViewSet(TenantModelViewSet):
    queryset = Scenario.objects.all()
    serializer_class = ScenarioSerializer
    perm_module = "planning"
    perm_read = "planning.view"
    perm_write = "planning.manage"
    filterset_fields = ["plan"]
    pagination_class = None


class EstablishmentView(APIView):
    def get(self, request):
        if not has_perm(request.user, "planning.view"):
            raise PermissionDenied()
        return Response({**services.establishment_summary(), "shortages": services.skills_shortages()
                         if has_perm(request.user, "talent.view") else None})
