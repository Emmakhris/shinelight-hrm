import datetime as dt

from django.db import transaction
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from apps.core.exceptions import BusinessRuleError
from apps.core.exports import tabular_response
from apps.core.serializers import TenantSerializer
from apps.core.views import TenantModelViewSet
from apps.employees.models import Employee
from apps.rbac.services import can_access_employee, has_perm

from . import services
from .models import ExpenseBudget, ExpenseClaim, ExpenseItem, PerDiemRate, TravelRequest


def _own_or_scoped(user, employee, code="expenses.view"):
    return employee == getattr(user, "employee", None) or can_access_employee(user, code, employee)


class PerDiemSerializer(TenantSerializer):
    class Meta(TenantSerializer.Meta):
        model = PerDiemRate


class PerDiemViewSet(TenantModelViewSet):
    queryset = PerDiemRate.objects.all()
    serializer_class = PerDiemSerializer
    perm_module = "expenses"
    perm_map = {"list": None, "retrieve": None}
    perm_write = "expenses.manage"
    pagination_class = None


class BudgetSerializer(TenantSerializer):
    department_name = serializers.CharField(source="department.name", read_only=True)
    status = serializers.SerializerMethodField()

    class Meta(TenantSerializer.Meta):
        model = ExpenseBudget

    def get_status(self, obj):
        return services.budget_status(obj.department, obj.year, obj.category)


class BudgetViewSet(TenantModelViewSet):
    queryset = ExpenseBudget.objects.select_related("department")
    serializer_class = BudgetSerializer
    perm_module = "expenses"
    perm_read = "expenses.view"
    perm_write = "expenses.manage"
    filterset_fields = ["year", "department"]
    pagination_class = None


class TravelSerializer(TenantSerializer):
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    department_name = serializers.CharField(source="employee.department.name", read_only=True, default=None)
    employee = serializers.PrimaryKeyRelatedField(queryset=Employee.objects, required=False)
    claim_status = serializers.SerializerMethodField()
    submit = serializers.BooleanField(write_only=True, default=True)

    class Meta(TenantSerializer.Meta):
        model = TravelRequest
        read_only_fields = TenantSerializer.Meta.read_only_fields + [
            "reference", "per_diem_days", "per_diem_rate", "total_estimate", "advance_paid", "advance_paid_on",
            "advance_reference", "retirement_due", "status", "warnings", "currency"]

    def get_claim_status(self, obj):
        c = obj.claims.exclude(status__in=["rejected", "cancelled"]).first()
        return {"id": c.id, "status": c.status, "net_payable": str(c.net_payable)} if c else None


class TravelViewSet(TenantModelViewSet):
    queryset = TravelRequest.objects.select_related("employee__department").prefetch_related("claims")
    serializer_class = TravelSerializer
    perm_module = "expenses"
    scope_prefix = "employee__"
    perm_map = {"create": None, "update": None, "partial_update": None, "destroy": None, "submit": None,
                "estimate": None, "pay_advance": "expenses.pay", "outstanding_advances": "expenses.view"}
    filterset_fields = ["status", "employee", "destination_class", "employee__department"]
    search_fields = ["reference", "destination", "employee__first_name", "employee__last_name"]

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get("mine") == "1":
            qs = qs.filter(employee=getattr(self.request.user, "employee", None))
        return qs

    def _employee(self, requested):
        own = getattr(self.request.user, "employee", None)
        if requested is None or requested == own:
            if own is None:
                raise BusinessRuleError("Your account is not linked to an employee record.")
            return own
        if not can_access_employee(self.request.user, "expenses.manage", requested):
            raise PermissionDenied("You cannot raise travel for this employee.")
        return requested

    def perform_create(self, serializer):
        submit = serializer.validated_data.pop("submit", True)
        emp = self._employee(serializer.validated_data.get("employee"))
        tr = serializer.save(employee=emp, status="draft")
        services.compute_travel(tr)
        tr.save()
        if submit:
            services.submit_travel(tr, self.request.user)

    def perform_update(self, serializer):
        if serializer.instance.status not in ("draft", "returned"):
            raise BusinessRuleError("Only draft or returned requests can be edited.")
        if not _own_or_scoped(self.request.user, serializer.instance.employee, "expenses.manage"):
            raise PermissionDenied()
        serializer.validated_data.pop("submit", None)
        serializer.validated_data.pop("employee", None)
        tr = serializer.save()
        services.compute_travel(tr)
        tr.save()

    def perform_destroy(self, instance):
        if instance.status != "draft":
            raise BusinessRuleError("Only drafts can be deleted.")
        instance.delete()

    @action(detail=False, methods=["post"])
    def estimate(self, request):
        s = self.get_serializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = dict(s.validated_data)
        d.pop("submit", None)
        d["employee"] = self._employee(d.get("employee"))
        tr = TravelRequest(**d)
        services.compute_travel(tr)
        return Response({"per_diem_days": tr.per_diem_days, "per_diem_rate": tr.per_diem_rate, "currency": tr.currency,
                         "total_estimate": tr.total_estimate, "warnings": tr.warnings})

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        tr = self.get_object()
        if not _own_or_scoped(request.user, tr.employee, "expenses.manage"):
            raise PermissionDenied()
        services.submit_travel(tr, request.user)
        return Response(self.get_serializer(tr).data)

    @action(detail=True, methods=["post"], url_path="pay-advance")
    def pay_advance(self, request, pk=None):
        tr = self.get_object()
        services.pay_advance(tr, request.user, request.data.get("amount") or tr.advance_requested,
                             request.data.get("reference", ""), via_payroll=bool(request.data.get("via_payroll")))
        return Response(self.get_serializer(tr).data)

    @action(detail=False, url_path="outstanding-advances")
    def outstanding_advances(self, request):
        qs = TravelRequest.objects.filter(advance_paid__gt=0, status__in=["approved", "completed"]).select_related(
            "employee__department")
        overdue = set(services.overdue_retirements().values_list("id", flat=True))
        headers = ["Reference", "Employee", "Department", "Destination", "Returned", "Advance", "Retire by", "Overdue"]
        rows = [[t.reference, t.employee.full_name, t.employee.department.name if t.employee.department_id else "",
                 t.destination, t.return_date.strftime("%d/%m/%Y"), t.advance_paid,
                 t.retirement_due.strftime("%d/%m/%Y") if t.retirement_due else "", "Yes" if t.id in overdue else ""]
                for t in qs]
        if request.query_params.get("format") in ("xlsx", "csv"):
            return tabular_response(headers, rows, "outstanding-advances", request.query_params["format"],
                                    totals_for=[5])
        return Response({"headers": headers, "rows": rows})


class ItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExpenseItem
        fields = ["id", "date", "category", "description", "amount", "receipt", "receipt_missing_reason"]


class ClaimSerializer(TenantSerializer):
    items = ItemSerializer(many=True)
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    travel_reference = serializers.CharField(source="travel_request.reference", read_only=True, default=None)
    employee = serializers.PrimaryKeyRelatedField(queryset=Employee.objects, required=False)
    submit = serializers.BooleanField(write_only=True, default=True)

    class Meta(TenantSerializer.Meta):
        model = ExpenseClaim
        read_only_fields = TenantSerializer.Meta.read_only_fields + [
            "reference", "total", "advance_offset", "net_payable", "status", "submitted_at", "paid_at", "paid_by",
            "payment_reference", "payroll_adjustment", "warnings"]

    def _save_items(self, claim, items):
        claim.items.all().delete()
        for it in items:
            ExpenseItem.objects.create(claim=claim, **it)

    @transaction.atomic
    def create(self, validated):
        items = validated.pop("items", [])
        claim = ExpenseClaim.objects.create(**validated)
        self._save_items(claim, items)
        return claim

    @transaction.atomic
    def update(self, instance, validated):
        items = validated.pop("items", None)
        for k, v in validated.items():
            setattr(instance, k, v)
        instance.save()
        if items is not None:
            self._save_items(instance, items)
        return instance


class ClaimViewSet(TenantModelViewSet):
    queryset = ExpenseClaim.objects.select_related("employee", "travel_request").prefetch_related("items")
    serializer_class = ClaimSerializer
    perm_module = "expenses"
    scope_prefix = "employee__"
    perm_map = {"create": None, "update": None, "partial_update": None, "destroy": None, "submit": None,
                "settle": "expenses.pay", "export": "expenses.view"}
    filterset_fields = ["status", "employee", "payment_method", "travel_request"]
    search_fields = ["reference", "title", "employee__first_name", "employee__last_name"]

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get("mine") == "1":
            qs = qs.filter(employee=getattr(self.request.user, "employee", None))
        return qs

    def perform_create(self, serializer):
        submit = serializer.validated_data.pop("submit", True)
        requested = serializer.validated_data.get("employee")
        own = getattr(self.request.user, "employee", None)
        emp = requested or own
        if emp is None:
            raise BusinessRuleError("Your account is not linked to an employee record.")
        if emp != own and not can_access_employee(self.request.user, "expenses.manage", emp):
            raise PermissionDenied("You cannot claim for this employee.")
        claim = serializer.save(employee=emp, status="draft")
        services.validate_claim(claim)
        claim.save()
        if submit:
            services.submit_claim(claim, self.request.user)

    def perform_update(self, serializer):
        if serializer.instance.status not in ("draft", "returned"):
            raise BusinessRuleError("Only draft or returned claims can be edited.")
        if not _own_or_scoped(self.request.user, serializer.instance.employee, "expenses.manage"):
            raise PermissionDenied()
        serializer.validated_data.pop("submit", None)
        serializer.validated_data.pop("employee", None)
        claim = serializer.save()
        services.validate_claim(claim)
        claim.save()

    def perform_destroy(self, instance):
        if instance.status != "draft":
            raise BusinessRuleError("Only drafts can be deleted.")
        instance.delete()

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        claim = self.get_object()
        if not _own_or_scoped(request.user, claim.employee, "expenses.manage"):
            raise PermissionDenied()
        services.submit_claim(claim, request.user)
        return Response(self.get_serializer(claim).data)

    @action(detail=True, methods=["post"])
    def settle(self, request, pk=None):
        claim = self.get_object()
        services.settle_claim(claim, request.user, request.data.get("method"), request.data.get("reference", ""))
        return Response(self.get_serializer(claim).data)

    @action(detail=False)
    def export(self, request):
        qs = self.filter_queryset(self.get_queryset())
        start = request.query_params.get("start")
        if start:
            qs = qs.filter(created_at__date__gte=dt.date.fromisoformat(start))
        headers = ["Reference", "Employee", "Title", "Total", "Advance offset", "Net payable", "Status", "Payment", "Paid"]
        rows = [[c.reference, c.employee.full_name, c.title, c.total, c.advance_offset, c.net_payable, c.status,
                 c.payment_method, c.paid_at.strftime("%d/%m/%Y") if c.paid_at else ""] for c in qs]
        if not has_perm(request.user, "reports.export") and not has_perm(request.user, "expenses.pay"):
            raise PermissionDenied("Export permission is required.")
        return tabular_response(headers, rows, "expense-claims", request.query_params.get("format", "xlsx"),
                                totals_for=[3, 4, 5])
