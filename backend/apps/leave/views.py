import datetime as dt
from decimal import Decimal

from django.db.models import Q, Sum
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.core.exceptions import BusinessRuleError
from apps.core.exports import tabular_response
from apps.core.serializers import TenantSerializer
from apps.core.views import TenantModelViewSet
from apps.employees.models import ACTIVE_STATUSES, Employee
from apps.rbac.services import can_access_employee, has_perm, scope_queryset

from . import services
from .models import LeaveLedgerEntry, LeavePolicy, LeaveRequest, LeaveType


class LeaveTypeSerializer(TenantSerializer):
    class Meta(TenantSerializer.Meta):
        model = LeaveType


class LeaveTypeViewSet(TenantModelViewSet):
    queryset = LeaveType.objects.all()
    serializer_class = LeaveTypeSerializer
    perm_module = "leave"
    perm_write = "leave.manage"
    perm_map = {"list": None, "retrieve": None}
    pagination_class = None


class LeavePolicySerializer(TenantSerializer):
    leave_type_name = serializers.CharField(source="leave_type.name", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True, default=None)

    class Meta(TenantSerializer.Meta):
        model = LeavePolicy


class LeavePolicyViewSet(TenantModelViewSet):
    queryset = LeavePolicy.objects.select_related("leave_type", "category")
    serializer_class = LeavePolicySerializer
    perm_module = "leave"
    perm_read = "leave.manage"
    perm_write = "leave.manage"
    filterset_fields = ["leave_type"]
    pagination_class = None


class LeaveRequestSerializer(TenantSerializer):
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    staff_number = serializers.CharField(source="employee.staff_number", read_only=True)
    department_name = serializers.CharField(source="employee.department.name", read_only=True, default=None)
    leave_type_name = serializers.CharField(source="leave_type.name", read_only=True)
    color = serializers.CharField(source="leave_type.color", read_only=True)
    relief_officer_name = serializers.CharField(source="relief_officer.full_name", read_only=True, default=None)
    workflow_instance = serializers.SerializerMethodField()
    employee = serializers.PrimaryKeyRelatedField(queryset=Employee.objects, required=False)
    submit = serializers.BooleanField(write_only=True, default=True)

    class Meta(TenantSerializer.Meta):
        model = LeaveRequest
        read_only_fields = TenantSerializer.Meta.read_only_fields + [
            "days", "status", "submitted_at", "decided_at", "recall_date", "recall_reason", "expected_return_date",
            "actual_return_date", "return_notes", "warnings"]

    def get_workflow_instance(self, obj):
        inst = services.workflow_instance(obj)
        return inst.id if inst else None

    def to_representation(self, obj):
        data = super().to_representation(obj)
        user = self.context["request"].user
        own = getattr(user, "employee", None) and user.employee.id == obj.employee_id
        if obj.leave_type.is_confidential and not own and not has_perm(user, "leave.manage"):
            data["reason"] = "(confidential)"
            data["attachment"] = None
        return data


class LeaveRequestViewSet(TenantModelViewSet):
    queryset = LeaveRequest.objects.select_related("employee__department", "leave_type", "relief_officer")
    serializer_class = LeaveRequestSerializer
    perm_module = "leave"
    scope_prefix = "employee__"
    perm_map = {"create": None, "update": None, "partial_update": None, "destroy": None, "submit": None,
                "cancel": None, "preview": None, "recall": "leave.approve", "confirm_return": None}
    filterset_fields = ["employee", "leave_type", "status", "employee__department"]
    search_fields = ["employee__first_name", "employee__last_name", "employee__staff_number"]
    ordering_fields = ["start_date", "created_at"]

    def _resolve_employee(self, requested):
        user = self.request.user
        own = getattr(user, "employee", None)
        if requested is None or requested == own:
            if own is None:
                raise BusinessRuleError("Your account is not linked to an employee record.")
            return own
        if not can_access_employee(user, "leave.manage", requested):
            raise PermissionDenied("You cannot apply for leave on behalf of this employee.")
        return requested

    def perform_create(self, serializer):
        submit = serializer.validated_data.pop("submit", True)
        emp = self._resolve_employee(serializer.validated_data.get("employee"))
        req = serializer.save(employee=emp, status="draft")
        req.days = services.calculate_days(req.leave_type, req.start_date, req.end_date, req.start_half, req.end_half)
        req.save(update_fields=["days"])
        if submit:
            services.submit(req, self.request.user)

    def perform_update(self, serializer):
        req = serializer.instance
        if req.status not in ("draft", "returned"):
            raise BusinessRuleError("Only draft or returned requests can be edited.")
        if req.employee != getattr(self.request.user, "employee", None) and \
                not can_access_employee(self.request.user, "leave.manage", req.employee):
            raise PermissionDenied("Not permitted.")
        serializer.validated_data.pop("submit", None)
        serializer.validated_data.pop("employee", None)
        req = serializer.save()
        req.days = services.calculate_days(req.leave_type, req.start_date, req.end_date, req.start_half, req.end_half)
        req.save(update_fields=["days"])

    def perform_destroy(self, instance):
        if instance.status != "draft":
            raise BusinessRuleError("Only drafts can be deleted. Cancel the request instead.")
        instance.delete()

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        req = self.get_object()
        if req.employee != getattr(request.user, "employee", None) and \
                not can_access_employee(request.user, "leave.manage", req.employee):
            raise PermissionDenied("Not permitted.")
        services.submit(req, request.user)
        return Response(self.get_serializer(req).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        req = self.get_object()
        if req.employee != getattr(request.user, "employee", None) and \
                not can_access_employee(request.user, "leave.manage", req.employee):
            raise PermissionDenied("Not permitted.")
        services.cancel(req, request.user, request.data.get("reason", ""))
        return Response(self.get_serializer(req).data)

    @action(detail=True, methods=["post"])
    def recall(self, request, pk=None):
        req = self.get_object()
        if not can_access_employee(request.user, "leave.approve", req.employee):
            raise PermissionDenied("Not permitted.")
        reason = request.data.get("reason", "").strip()
        if not reason:
            raise BusinessRuleError("A reason is required to recall an employee from leave.")
        unused = services.recall(req, dt.date.fromisoformat(request.data["recall_date"]), reason, request.user)
        return Response({"detail": f"Employee recalled; {unused} day(s) credited back."})

    @action(detail=True, methods=["post"])
    def confirm_return(self, request, pk=None):
        req = self.get_object()
        services.confirm_return(req, dt.date.fromisoformat(request.data.get("return_date") or
                                                           dt.date.today().isoformat()),
                                request.data.get("notes", ""))
        return Response(self.get_serializer(req).data)

    @action(detail=False, methods=["post"])
    def preview(self, request):
        """Calculate days, balance and warnings before submitting."""
        lt = LeaveType.objects.get(pk=request.data["leave_type"])
        emp_id = request.data.get("employee")
        emp = self._resolve_employee(Employee.objects.get(pk=emp_id) if emp_id else None)
        req = LeaveRequest(employee=emp, leave_type=lt, start_date=dt.date.fromisoformat(request.data["start_date"]),
                           end_date=dt.date.fromisoformat(request.data["end_date"]),
                           start_half=bool(request.data.get("start_half")), end_half=bool(request.data.get("end_half")),
                           attachment_id=request.data.get("attachment") or None,
                           relief_officer_id=request.data.get("relief_officer") or None)
        try:
            warnings = services.validate(req)
            error = None
        except BusinessRuleError as exc:
            warnings, error = [], exc.message
            try:
                req.days = services.calculate_days(lt, req.start_date, req.end_date, req.start_half, req.end_half)
            except BusinessRuleError:
                req.days = Decimal("0")
        bal = services.balance(emp, lt, req.start_date.year) if lt.tracks_balance else None
        return Response({"days": req.days, "warnings": warnings, "error": error, "balance": bal,
                         "expected_return_date": services.expected_return(req) if not error else None})

    @action(detail=False, permission_classes=[IsAuthenticated])
    def balances(self, request):
        emp_id = request.query_params.get("employee")
        year = int(request.query_params.get("year", dt.date.today().year))
        emp = Employee.objects.get(pk=emp_id) if emp_id else getattr(request.user, "employee", None)
        if emp is None:
            return Response([])
        if emp != getattr(request.user, "employee", None) and not can_access_employee(request.user, "leave.view", emp):
            raise PermissionDenied("Not permitted.")
        return Response(services.all_balances(emp, year))

    @action(detail=False, permission_classes=[IsAuthenticated])
    def ledger(self, request):
        emp = Employee.objects.get(pk=request.query_params.get("employee") or request.user.employee.id)
        if emp != getattr(request.user, "employee", None) and not can_access_employee(request.user, "leave.view", emp):
            raise PermissionDenied("Not permitted.")
        year = int(request.query_params.get("year", dt.date.today().year))
        qs = LeaveLedgerEntry.objects.filter(employee=emp, year=year).select_related("leave_type")
        if request.query_params.get("leave_type"):
            qs = qs.filter(leave_type_id=request.query_params["leave_type"])
        return Response([{"id": e.id, "date": e.date, "leave_type": e.leave_type.name, "entry_type": e.entry_type,
                          "entry_label": e.get_entry_type_display(), "days": e.days, "note": e.note,
                          "request": e.request_id} for e in qs])

    @action(detail=False, methods=["post"], permission_classes=[IsAuthenticated])
    def adjust(self, request):
        emp = Employee.objects.get(pk=request.data["employee"])
        if not can_access_employee(request.user, "leave.manage", emp):
            raise PermissionDenied("Not permitted.")
        note = request.data.get("note", "").strip()
        if not note:
            raise BusinessRuleError("A reason is required for balance adjustments.")
        entry = services.adjust(emp, LeaveType.objects.get(pk=request.data["leave_type"]), request.data["days"], note,
                                int(request.data.get("year") or dt.date.today().year))
        return Response({"id": entry.id, "detail": "Balance adjusted."}, status=201)

    @action(detail=False)
    def calendar(self, request):
        start = dt.date.fromisoformat(request.query_params.get("start", dt.date.today().replace(day=1).isoformat()))
        end = dt.date.fromisoformat(request.query_params.get("end", (start + dt.timedelta(days=41)).isoformat()))
        qs = self.get_queryset().filter(status__in=["approved", "pending", "recalled"], start_date__lte=end,
                                        end_date__gte=start)
        user = request.user
        own = getattr(user, "employee", None)
        if request.query_params.get("scope") == "department" and own and own.department_id:
            # colleagues may see approved absences in their own department (no reasons)
            qs = LeaveRequest.objects.filter(employee__department=own.department_id, status__in=["approved", "recalled"],
                                             start_date__lte=end, end_date__gte=start)
        if request.query_params.get("department"):
            qs = qs.filter(employee__department=request.query_params["department"])
        return Response([{"id": r.id, "employee": r.employee_id, "employee_name": r.employee.full_name,
                          "leave_type": r.leave_type.name, "color": r.leave_type.color,
                          "start": r.start_date, "end": r.recall_date - dt.timedelta(days=1) if r.recall_date else r.end_date,
                          "status": r.status, "days": r.days} for r in qs.select_related("employee", "leave_type")])

    @action(detail=False, url_path="report/balances")
    def report_balances(self, request):
        if not has_perm(request.user, "reports.view"):
            raise PermissionDenied("Not permitted.")
        year = int(request.query_params.get("year", dt.date.today().year))
        emps = scope_queryset(request.user, Employee.objects.filter(status__in=ACTIVE_STATUSES), "leave.view")
        types = list(LeaveType.objects.filter(is_active=True, tracks_balance=True))
        headers = ["Staff No", "Name", "Department"] + [f"{t.name} available" for t in types]
        rows = []
        for e in emps.select_related("department"):
            rows.append([e.staff_number, e.full_name, e.department.name if e.department_id else ""]
                        + [services.balance(e, t, year)["available"] for t in types])
        if request.query_params.get("format") in ("xlsx", "csv"):
            return tabular_response(headers, rows, f"leave-balances-{year}", request.query_params["format"])
        return Response({"headers": headers, "rows": rows})

    @action(detail=False, url_path="report/utilization")
    def report_utilization(self, request):
        if not has_perm(request.user, "reports.view"):
            raise PermissionDenied("Not permitted.")
        year = int(request.query_params.get("year", dt.date.today().year))
        qs = self.get_queryset().filter(status__in=["approved", "recalled"], start_date__year=year)
        by_type = qs.values("leave_type__name").annotate(days=Sum("days")).order_by("-days")
        by_month = {}
        for r in qs:
            by_month[r.start_date.month] = by_month.get(r.start_date.month, Decimal("0")) + r.days
        by_dept = qs.values("employee__department__name").annotate(days=Sum("days")).order_by("-days")
        sick = qs.filter(Q(leave_type__code="sick")).aggregate(d=Sum("days"))["d"] or 0
        return Response({"by_type": list(by_type), "by_month": [{"month": m, "days": d} for m, d in sorted(by_month.items())],
                         "by_department": list(by_dept), "sick_days": sick})
