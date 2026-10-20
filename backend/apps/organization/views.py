from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.serializers import TenantSerializer
from apps.core.views import TenantModelViewSet

from .models import Branch, CostCenter, Department, Grade, GradeStep, JobFamily, JobTitle, Location, Position


def simple_serializer(model_cls, extra_fields=None, read_only=None):
    attrs = {"Meta": type("Meta", (TenantSerializer.Meta,), {"model": model_cls})}
    attrs.update(extra_fields or {})
    return type(f"{model_cls.__name__}Serializer", (TenantSerializer,), attrs)


class OrgViewSet(TenantModelViewSet):
    perm_module = "organization"
    perm_write = "organization.manage"


class BranchViewSet(OrgViewSet):
    queryset = Branch.objects.all()
    serializer_class = simple_serializer(Branch)
    search_fields = ["name", "code", "region"]
    pagination_class = None


class LocationViewSet(OrgViewSet):
    queryset = Location.objects.select_related("branch")
    serializer_class = simple_serializer(Location, {"branch_name": serializers.CharField(source="branch.name",
                                                                                         read_only=True, default="")})
    search_fields = ["name"]
    pagination_class = None


class CostCenterViewSet(OrgViewSet):
    queryset = CostCenter.objects.all()
    serializer_class = simple_serializer(CostCenter)
    search_fields = ["code", "name"]
    pagination_class = None


class DepartmentSerializer(TenantSerializer):
    parent_name = serializers.CharField(source="parent.name", read_only=True, default=None)
    head_name = serializers.CharField(source="head.full_name", read_only=True, default=None)
    headcount = serializers.SerializerMethodField()

    class Meta(TenantSerializer.Meta):
        model = Department

    def get_headcount(self, obj):
        return getattr(obj, "_headcount", None) if hasattr(obj, "_headcount") else obj.employees.exclude(
            status="exited").count()

    def validate_parent(self, parent):
        if parent and self.instance and (parent == self.instance or self.instance in parent.ancestors()):
            raise serializers.ValidationError("A department cannot be its own ancestor.")
        return parent


class DepartmentViewSet(OrgViewSet):
    queryset = Department.objects.select_related("parent", "head", "branch")
    serializer_class = DepartmentSerializer
    search_fields = ["name", "code"]
    filterset_fields = ["parent", "branch", "unit_type", "is_active"]
    pagination_class = None

    @action(detail=False)
    def tree(self, request):
        depts = list(self.get_queryset())
        nodes = {d.id: {"id": d.id, "name": d.name, "code": d.code, "unit_type": d.unit_type,
                        "head": d.head.full_name if d.head_id else None, "children": []} for d in depts}
        roots = []
        for d in depts:
            (nodes[d.parent_id]["children"] if d.parent_id in nodes else roots).append(nodes[d.id])
        return Response(roots)


class JobFamilyViewSet(OrgViewSet):
    queryset = JobFamily.objects.all()
    serializer_class = simple_serializer(JobFamily)
    pagination_class = None


class GradeStepSerializer(TenantSerializer):
    grade_code = serializers.CharField(source="grade.code", read_only=True)

    class Meta(TenantSerializer.Meta):
        model = GradeStep


class GradeSerializer(TenantSerializer):
    steps = GradeStepSerializer(many=True, read_only=True)

    class Meta(TenantSerializer.Meta):
        model = Grade


class GradeViewSet(OrgViewSet):
    queryset = Grade.objects.prefetch_related("steps")
    serializer_class = GradeSerializer
    pagination_class = None


class GradeStepViewSet(OrgViewSet):
    queryset = GradeStep.objects.select_related("grade")
    serializer_class = GradeStepSerializer
    filterset_fields = ["grade"]
    pagination_class = None


class JobTitleViewSet(OrgViewSet):
    queryset = JobTitle.objects.select_related("family", "default_grade")
    serializer_class = simple_serializer(JobTitle, {
        "family_name": serializers.CharField(source="family.name", read_only=True, default=None)})
    search_fields = ["name", "code"]
    filterset_fields = ["family", "is_clinical"]
    pagination_class = None


class PositionSerializer(TenantSerializer):
    job_title_name = serializers.CharField(source="job_title.name", read_only=True)
    department_name = serializers.CharField(source="department.name", read_only=True)
    grade_code = serializers.CharField(source="grade.code", read_only=True, default=None)
    reports_to_code = serializers.CharField(source="reports_to.code", read_only=True, default=None)
    occupied = serializers.IntegerField(source="occupied_count", read_only=True)
    vacancies = serializers.IntegerField(read_only=True)
    incumbents = serializers.SerializerMethodField()

    class Meta(TenantSerializer.Meta):
        model = Position

    def get_incumbents(self, obj):
        return [{"id": e.id, "name": e.full_name, "staff_number": e.staff_number}
                for e in obj.employees.exclude(status="exited")]


class PositionViewSet(OrgViewSet):
    queryset = Position.objects.select_related("job_title", "department", "grade", "reports_to")
    serializer_class = PositionSerializer
    search_fields = ["code", "job_title__name"]
    filterset_fields = ["department", "status", "grade", "employment_type", "is_critical", "branch"]

    @action(detail=False)
    def establishment(self, request):
        """Approved vs occupied establishment by department (workforce planning foundation)."""
        rows = {}
        for p in self.get_queryset().filter(status__in=["approved", "frozen"]):
            r = rows.setdefault(p.department_id, {"department": p.department.name, "approved": 0, "frozen": 0,
                                                  "occupied": 0, "vacant": 0, "budget": 0})
            if p.status == "frozen":
                r["frozen"] += p.headcount
                continue
            occ = p.occupied_count
            r["approved"] += p.headcount
            r["occupied"] += min(occ, p.headcount)
            r["vacant"] += max(p.headcount - occ, 0)
            r["budget"] += float(p.budgeted_annual_cost)
        return Response(sorted(rows.values(), key=lambda r: r["department"]))


class OrgChartViewSet(TenantModelViewSet):
    """Live reporting chart from supervisor relationships."""

    perm_module = "organization"
    http_method_names = ["get"]

    def list(self, request):
        from apps.employees.models import ACTIVE_STATUSES, Employee

        emps = list(Employee.objects.filter(status__in=ACTIVE_STATUSES)
                    .select_related("job_title", "department").only(
                        "id", "first_name", "middle_name", "last_name", "supervisor_id", "photo", "job_title__name",
                        "department__name", "staff_number"))
        nodes = {e.id: {"id": e.id, "name": e.full_name, "title": e.job_title.name if e.job_title_id else "",
                        "department": e.department.name if e.department_id else "",
                        "photo": e.photo.url if e.photo else None, "children": []} for e in emps}
        roots = []
        for e in emps:
            parent = nodes.get(e.supervisor_id)
            (parent["children"] if parent and e.supervisor_id != e.id else roots).append(nodes[e.id])
        root_id = request.query_params.get("root")
        if root_id and int(root_id) in nodes:
            return Response([nodes[int(root_id)]])
        return Response(roots)
