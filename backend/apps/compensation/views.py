import datetime as dt

from django.http import HttpResponse
from django.template.loader import render_to_string
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit import services as audit
from apps.core.exceptions import BusinessRuleError
from apps.core.pdf import BASE_CSS, html_to_pdf
from apps.core.serializers import TenantSerializer
from apps.core.views import TenantModelViewSet
from apps.employees.models import Employee
from apps.rbac.services import can_access_employee, has_perm

from . import services
from .models import (
    BenefitEnrollment,
    BenefitPlan,
    BonusAward,
    BonusScheme,
    SalaryReviewCycle,
    SalaryReviewLine,
)


class CycleSerializer(TenantSerializer):
    summary = serializers.SerializerMethodField()

    class Meta(TenantSerializer.Meta):
        model = SalaryReviewCycle
        read_only_fields = TenantSerializer.Meta.read_only_fields + ["status", "applied_at", "applied_by"]

    def get_summary(self, obj):
        return services.cycle_summary(obj)


class LineSerializer(TenantSerializer):
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    staff_number = serializers.CharField(source="employee.staff_number", read_only=True)
    department = serializers.CharField(source="employee.department.name", read_only=True, default=None)
    grade = serializers.CharField(source="employee.grade.code", read_only=True, default=None)
    guideline = serializers.SerializerMethodField()
    performance_rating = serializers.SerializerMethodField()

    class Meta(TenantSerializer.Meta):
        model = SalaryReviewLine
        read_only_fields = TenantSerializer.Meta.read_only_fields + [
            "cycle", "employee", "current_basic", "outside_guideline", "applied"]

    def get_guideline(self, obj):
        g = services.guideline_for(obj.cycle, obj.employee)
        return {"min": g[0], "max": g[1]} if g else None

    def get_performance_rating(self, obj):
        from apps.performance.services import latest_rating

        return latest_rating(obj.employee, before=obj.cycle.effective_date)


class CycleViewSet(TenantModelViewSet):
    queryset = SalaryReviewCycle.objects.prefetch_related("departments")
    serializer_class = CycleSerializer
    perm_module = "compensation"
    perm_write = "compensation.manage"
    perm_map = {"populate": "compensation.manage", "submit": "compensation.manage", "apply": "compensation.manage",
                "lines": "compensation.view", "update_line": "compensation.manage"}
    pagination_class = None

    def perform_update(self, serializer):
        if serializer.instance.status not in ("draft", "open", "returned"):
            raise BusinessRuleError("This review is locked.")
        serializer.save()

    @action(detail=True, methods=["post"])
    def populate(self, request, pk=None):
        return Response({"added": services.populate_cycle(self.get_object())})

    @action(detail=True)
    def lines(self, request, pk=None):
        cycle = self.get_object()
        qs = cycle.lines.select_related("employee__department", "employee__grade", "cycle")
        return Response(LineSerializer(qs, many=True, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["patch"], url_path=r"lines/(?P<line_id>\d+)")
    def update_line(self, request, pk=None, line_id=None):
        cycle = self.get_object()
        if cycle.status not in ("open", "returned"):
            raise BusinessRuleError("Proposals are locked.")
        line = cycle.lines.select_related("employee__grade").get(pk=line_id)
        if line.employee == getattr(request.user, "employee", None):
            raise PermissionDenied("You cannot set your own salary proposal.")
        for f in ("justification", "excluded", "proposed_grade_step"):
            if f in request.data:
                val = request.data[f]
                if f == "proposed_grade_step":
                    from apps.organization.models import GradeStep

                    line.proposed_grade_step = GradeStep.objects.get(pk=val) if val else None
                    if line.proposed_grade_step:
                        services.recalc_line(line, proposed_basic=line.proposed_grade_step.basic_salary)
                else:
                    setattr(line, f, val)
        if "proposed_basic" in request.data and request.data["proposed_basic"] not in ("", None):
            services.recalc_line(line, proposed_basic=request.data["proposed_basic"])
        elif "increase_percent" in request.data:
            services.recalc_line(line, increase_percent=request.data["increase_percent"])
        else:
            line.save()
        return Response(LineSerializer(line, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        cycle = services.submit_cycle(self.get_object(), request.user)
        return Response(self.get_serializer(cycle).data)

    @action(detail=True, methods=["post"])
    def apply(self, request, pk=None):
        n = services.apply_cycle(self.get_object(), request.user)
        return Response({"detail": f"{n} salary change(s) recorded effective from the review date."})


class AwardSerializer(TenantSerializer):
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)

    class Meta(TenantSerializer.Meta):
        model = BonusAward
        read_only_fields = TenantSerializer.Meta.read_only_fields + ["payroll_adjustment"]


class SchemeSerializer(TenantSerializer):
    total = serializers.SerializerMethodField()
    award_count = serializers.IntegerField(source="awards.count", read_only=True)
    period_name = serializers.CharField(source="pay_period.name", read_only=True, default=None)

    class Meta(TenantSerializer.Meta):
        model = BonusScheme
        read_only_fields = TenantSerializer.Meta.read_only_fields + ["status"]

    def get_total(self, obj):
        from django.db.models import Sum

        return obj.awards.aggregate(s=Sum("amount"))["s"] or 0


class SchemeViewSet(TenantModelViewSet):
    queryset = BonusScheme.objects.select_related("pay_period")
    serializer_class = SchemeSerializer
    perm_module = "compensation"
    perm_write = "compensation.manage"
    perm_map = {"populate": "compensation.manage", "submit": "compensation.manage"}
    pagination_class = None

    @action(detail=True, methods=["post"])
    def populate(self, request, pk=None):
        scheme = self.get_object()
        if scheme.status not in ("draft", "open", "returned"):
            raise BusinessRuleError("Scheme is locked.")
        ids = request.data.get("employees") or list(Employee.objects.exclude(status="exited").values_list("id", flat=True))
        n = 0
        for emp in Employee.objects.filter(pk__in=ids):
            _, created = BonusAward.objects.get_or_create(scheme=scheme, employee=emp,
                                                          defaults={"amount": services.bonus_amount(scheme, emp)})
            n += int(created)
        return Response({"added": n})

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        return Response(self.get_serializer(services.submit_bonus(self.get_object(), request.user)).data)


class AwardViewSet(TenantModelViewSet):
    queryset = BonusAward.objects.select_related("employee", "scheme")
    serializer_class = AwardSerializer
    perm_module = "compensation"
    perm_write = "compensation.manage"
    filterset_fields = ["scheme"]
    pagination_class = None

    def perform_create(self, serializer):
        if serializer.validated_data["scheme"].status not in ("draft", "open", "returned"):
            raise BusinessRuleError("Scheme is locked.")
        serializer.save()

    def perform_update(self, serializer):
        if serializer.instance.scheme.status not in ("draft", "open", "returned"):
            raise BusinessRuleError("Scheme is locked.")
        if serializer.instance.employee == getattr(self.request.user, "employee", None):
            raise PermissionDenied("You cannot set your own bonus.")
        serializer.save()


class PlanSerializer(TenantSerializer):
    members = serializers.SerializerMethodField()
    eligible = serializers.SerializerMethodField()
    my_enrollment = serializers.SerializerMethodField()

    class Meta(TenantSerializer.Meta):
        model = BenefitPlan

    def get_members(self, obj):
        return services.active_enrollments().filter(plan=obj).count()

    def get_eligible(self, obj):
        emp = getattr(self.context["request"].user, "employee", None)
        return services.eligibility(obj, emp) if emp else ["No employee record."]

    def get_my_enrollment(self, obj):
        emp = getattr(self.context["request"].user, "employee", None)
        e = obj.enrollments.filter(employee=emp, status__in=["pending", "active"]).first() if emp else None
        return {"id": e.id, "status": e.status} if e else None


class PlanViewSet(TenantModelViewSet):
    queryset = BenefitPlan.objects.prefetch_related("categories")
    serializer_class = PlanSerializer
    perm_module = "benefits"
    perm_map = {"list": None, "retrieve": None, "auto_enroll": "benefits.manage", "cost": "benefits.manage"}
    perm_write = "benefits.manage"
    pagination_class = None

    @action(detail=True, methods=["post"], url_path="auto-enroll")
    def auto_enroll(self, request, pk=None):
        return Response({"enrolled": services.auto_enroll(self.get_object())})

    @action(detail=False)
    def cost(self, request):
        return Response(services.benefits_cost(int(request.query_params.get("months", 12))))


class EnrollmentSerializer(TenantSerializer):
    plan_name = serializers.CharField(source="plan.name", read_only=True)
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    employee_cost = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    employee = serializers.PrimaryKeyRelatedField(queryset=Employee.objects, required=False)

    class Meta(TenantSerializer.Meta):
        model = BenefitEnrollment
        read_only_fields = TenantSerializer.Meta.read_only_fields + ["status", "pay_element"]


class EnrollmentViewSet(TenantModelViewSet):
    queryset = BenefitEnrollment.objects.select_related("plan", "employee")
    serializer_class = EnrollmentSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["plan", "status", "employee"]
    http_method_names = ["get", "post", "patch"]

    def get_queryset(self):
        qs = super().get_queryset()
        if has_perm(self.request.user, "benefits.manage") and self.request.query_params.get("mine") != "1":
            return qs
        return qs.filter(employee=getattr(self.request.user, "employee", None))

    def create(self, request, *args, **kwargs):
        s = self.get_serializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        own = getattr(request.user, "employee", None)
        emp = d.get("employee") or own
        if emp is None or (emp != own and not can_access_employee(request.user, "benefits.manage", emp)):
            raise PermissionDenied()
        e = services.enroll(d["plan"], emp, request.user, d.get("start_date") or dt.date.today(), d.get("dependants"))
        return Response(self.get_serializer(e).data, status=201)

    def partial_update(self, request, *args, **kwargs):
        e = self.get_object()
        if not has_perm(request.user, "benefits.manage"):
            raise PermissionDenied()
        if "member_number" in request.data:
            e.member_number = request.data["member_number"]
            e.save(update_fields=["member_number"])
        return Response(self.get_serializer(e).data)

    @action(detail=True, methods=["post"])
    def end(self, request, pk=None):
        e = self.get_object()
        if e.employee != getattr(request.user, "employee", None) and not has_perm(request.user, "benefits.manage"):
            raise PermissionDenied()
        end = dt.date.fromisoformat(request.data.get("end_date") or dt.date.today().isoformat())
        services.end_enrollment(e, end, request.user)
        return Response(self.get_serializer(e).data)


class TotalRewardsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        emp_id = request.query_params.get("employee")
        own = getattr(request.user, "employee", None)
        emp = Employee.objects.get(pk=emp_id) if emp_id else own
        if emp is None:
            raise BusinessRuleError("No employee record.")
        if emp != own and not can_access_employee(request.user, "employees.view_salary", emp):
            raise PermissionDenied()
        year = int(request.query_params.get("year", dt.date.today().year))
        data = services.total_rewards(emp, year)
        if request.query_params.get("format") == "pdf":
            org = emp.organization
            html = render_to_string("pdf/total_rewards.html", {"d": data, "org": org, "css": BASE_CSS})
            audit.log("download", emp, {"total_rewards": year})
            resp = HttpResponse(html_to_pdf(html), content_type="application/pdf")
            resp["Content-Disposition"] = f'inline; filename="total-rewards-{emp.staff_number}-{year}.pdf"'
            return resp
        return Response(data)
