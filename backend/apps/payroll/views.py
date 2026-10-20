import datetime as dt

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.audit import services as audit
from apps.core.exceptions import BusinessRuleError
from apps.core.exports import tabular_response
from apps.core.serializers import DisplayField, SensitiveFieldsMixin, TenantSerializer
from apps.core.views import TenantModelViewSet
from apps.employees.models import Employee
from apps.rbac.services import can_access_employee, has_perm

from . import exports, services
from .models import (
    EmployeePayElement,
    EmployeePayProfile,
    EmployeeTaxRelief,
    Loan,
    LoanRepayment,
    PayElement,
    PayGroup,
    PayrollAdjustment,
    PayrollPeriod,
    PayrollRun,
    Payslip,
    PayslipLine,
    StatutoryRateSet,
    TaxBand,
    TaxRelief,
    TaxTable,
)


def ser(model_cls, extra=None, read_only=()):
    meta = type("Meta", (TenantSerializer.Meta,), {"model": model_cls,
                                                   "read_only_fields": TenantSerializer.Meta.read_only_fields
                                                   + list(read_only)})
    return type(f"{model_cls.__name__}Serializer", (TenantSerializer,), {"Meta": meta, **(extra or {})})


class PayrollConfigViewSet(TenantModelViewSet):
    perm_module = "payroll"
    perm_read = "payroll.view"
    perm_write = "payroll.manage"
    pagination_class = None


class PayGroupViewSet(PayrollConfigViewSet):
    queryset = PayGroup.objects.all()
    serializer_class = ser(PayGroup)


class RateSetViewSet(PayrollConfigViewSet):
    queryset = StatutoryRateSet.objects.all()
    serializer_class = ser(StatutoryRateSet)


class TaxBandSerializer(TenantSerializer):
    class Meta(TenantSerializer.Meta):
        model = TaxBand
        exclude = ["organization", "table"]


class TaxTableSerializer(TenantSerializer):
    bands = TaxBandSerializer(many=True)

    class Meta(TenantSerializer.Meta):
        model = TaxTable

    def _save_bands(self, table, bands):
        table.bands.all().delete()
        for i, b in enumerate(bands, start=1):
            TaxBand.objects.create(table=table, order=b.get("order") or i, width=b.get("width"), rate=b["rate"])

    def create(self, validated):
        bands = validated.pop("bands", [])
        table = TaxTable.objects.create(**validated)
        self._save_bands(table, bands)
        return table

    def update(self, instance, validated):
        bands = validated.pop("bands", None)
        for k, v in validated.items():
            setattr(instance, k, v)
        instance.save()
        if bands is not None:
            self._save_bands(instance, bands)
        return instance


class TaxTableViewSet(PayrollConfigViewSet):
    queryset = TaxTable.objects.prefetch_related("bands")
    serializer_class = TaxTableSerializer

    @action(detail=True, methods=["post"])
    def compute(self, request, pk=None):
        """Quick calculator: PAYE for a chargeable monthly income."""
        from decimal import Decimal

        from .engine import graduated_tax

        table = self.get_object()
        amount = Decimal(str(request.data.get("amount", "0")))
        return Response({"chargeable": amount, "paye": graduated_tax(amount, [(b.width, b.rate)
                                                                              for b in table.bands.order_by("order")])})


class ReliefViewSet(PayrollConfigViewSet):
    queryset = TaxRelief.objects.all()
    serializer_class = ser(TaxRelief)


class ElementViewSet(PayrollConfigViewSet):
    queryset = PayElement.objects.all()
    serializer_class = ser(PayElement)
    filterset_fields = ["element_type", "category", "is_active"]

    def perform_destroy(self, instance):
        if instance.is_system:
            raise BusinessRuleError("System pay elements cannot be deleted.")
        instance.is_active = False
        instance.save(update_fields=["is_active"])


class PayProfileSerializer(TenantSerializer):
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    pay_group_name = serializers.CharField(source="pay_group.name", read_only=True)

    class Meta(TenantSerializer.Meta):
        model = EmployeePayProfile


class PayProfileViewSet(TenantModelViewSet):
    queryset = EmployeePayProfile.objects.select_related("employee", "pay_group")
    serializer_class = PayProfileSerializer
    perm_module = "payroll"
    perm_read = "payroll.view"
    perm_write = "payroll.prepare"
    filterset_fields = ["employee", "pay_group", "payment_hold"]

    @action(detail=False, methods=["post"], url_path="bulk-assign")
    def bulk_assign(self, request):
        group = PayGroup.objects.get(pk=request.data["pay_group"])
        n = 0
        for emp in Employee.objects.exclude(status="exited").filter(pay_profile__isnull=True):
            EmployeePayProfile.objects.create(employee=emp, pay_group=group)
            n += 1
        return Response({"created": n})


class EmployeeElementSerializer(SensitiveFieldsMixin, TenantSerializer):
    sensitive_fields = {"amount": "employees.view_salary"}
    element_name = serializers.CharField(source="element.name", read_only=True)
    element_type = serializers.CharField(source="element.element_type", read_only=True)
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)

    class Meta(TenantSerializer.Meta):
        model = EmployeePayElement


class EmployeeElementViewSet(TenantModelViewSet):
    queryset = EmployeePayElement.objects.select_related("element", "employee")
    serializer_class = EmployeeElementSerializer
    perm_module = "payroll"
    perm_read = "payroll.view"
    perm_write = "payroll.prepare"
    filterset_fields = ["employee", "element"]


class ReliefClaimViewSet(TenantModelViewSet):
    queryset = EmployeeTaxRelief.objects.select_related("relief", "employee")
    serializer_class = ser(EmployeeTaxRelief, {"relief_name": serializers.CharField(source="relief.name", read_only=True)})
    perm_module = "payroll"
    perm_read = "payroll.view"
    perm_write = "payroll.prepare"
    filterset_fields = ["employee", "approved"]


class PeriodViewSet(TenantModelViewSet):
    queryset = PayrollPeriod.objects.select_related("pay_group")
    serializer_class = ser(PayrollPeriod, {"pay_group_name": serializers.CharField(source="pay_group.name",
                                                                                   read_only=True)})
    perm_module = "payroll"
    perm_read = "payroll.view"
    perm_write = "payroll.prepare"
    filterset_fields = ["pay_group", "status"]
    perm_map = {"generate": "payroll.prepare", "close": "payroll.release", "retro_arrears": "payroll.prepare"}

    @action(detail=False, methods=["post"])
    def generate(self, request):
        group = PayGroup.objects.get(pk=request.data["pay_group"])
        period = services.create_period(group, int(request.data["year"]), int(request.data["month"]),
                                        int(request.data.get("pay_day", 25)))
        return Response(self.get_serializer(period).data, status=201)

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        period = self.get_object()
        if period.runs.exclude(status__in=["paid", "reversed"]).exists():
            raise BusinessRuleError("All runs in the period must be released or reversed before closing.")
        period.status = "closed"
        period.save(update_fields=["status", "updated_at"])
        audit.log("payroll", period, {"action": "period_closed"})
        return Response({"detail": "Period closed."})

    @action(detail=True, methods=["post"], url_path="retro-arrears")
    def retro_arrears(self, request, pk=None):
        created = services.generate_retro_arrears(self.get_object(), request.user)
        return Response({"created": len(created), "total": str(sum(a.amount for a in created))})


class AdjustmentViewSet(TenantModelViewSet):
    queryset = PayrollAdjustment.objects.select_related("employee", "element", "period")
    serializer_class = ser(PayrollAdjustment, {
        "employee_name": serializers.CharField(source="employee.full_name", read_only=True),
        "element_name": serializers.CharField(source="element.name", read_only=True)}, read_only=["is_system"])
    perm_module = "payroll"
    perm_read = "payroll.view"
    perm_write = "payroll.prepare"
    filterset_fields = ["period", "employee", "element"]

    def perform_create(self, serializer):
        if serializer.validated_data["period"].status == "closed":
            raise BusinessRuleError("Period is closed.")
        serializer.save()


class RunSerializer(TenantSerializer):
    period_name = serializers.CharField(source="period.name", read_only=True)
    pay_date = serializers.DateField(source="period.pay_date", read_only=True)
    run_type_label = serializers.CharField(source="get_run_type_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    calculated_by_name = DisplayField("calculated_by")
    approved_by_name = DisplayField("approved_by")
    released_by_name = DisplayField("released_by")

    class Meta(TenantSerializer.Meta):
        model = PayrollRun
        read_only_fields = TenantSerializer.Meta.read_only_fields + [
            "status", "number", "rate_set", "tax_table", "calculated_at", "calculated_by", "calculation_count",
            "submitted_at", "submitted_by", "approved_at", "approved_by", "released_at", "released_by",
            "reversal_of", "totals", "payslips_published"]


class LineSerializer(serializers.ModelSerializer):
    class Meta:
        model = PayslipLine
        fields = ["id", "code", "name", "line_type", "category", "quantity", "rate", "amount", "taxable",
                  "show_on_payslip", "reference"]


class PayslipSerializer(serializers.ModelSerializer):
    lines = LineSerializer(many=True, read_only=True)
    period_name = serializers.CharField(source="run.period.name", read_only=True)
    pay_date = serializers.DateField(source="run.period.pay_date", read_only=True)
    run_type = serializers.CharField(source="run.run_type", read_only=True)

    class Meta:
        model = Payslip
        exclude = ["organization"]


class PayslipBriefSerializer(serializers.ModelSerializer):
    period_name = serializers.CharField(source="run.period.name", read_only=True)
    pay_date = serializers.DateField(source="run.period.pay_date", read_only=True)

    class Meta:
        model = Payslip
        fields = ["id", "run", "employee", "staff_number", "employee_name", "department", "grade", "days_payable",
                  "basic_pay", "gross_pay", "paye", "ssnit_employee", "total_deductions", "net_pay", "employer_cost",
                  "status", "messages", "period_name", "pay_date", "published_at"]


class RunViewSet(TenantModelViewSet):
    queryset = PayrollRun.objects.select_related("period__pay_group", "calculated_by", "approved_by", "released_by")
    serializer_class = RunSerializer
    perm_module = "payroll"
    perm_read = "payroll.view"
    perm_write = "payroll.prepare"
    filterset_fields = ["period", "status", "run_type"]
    http_method_names = ["get", "post", "patch", "delete"]
    perm_map = {"calculate": "payroll.prepare", "submit": "payroll.prepare", "release": "payroll.release",
                "reverse": "payroll.release", "publish": "payroll.release", "payslips": "payroll.view",
                "report": "payroll.view", "bank_file": "payroll.release"}

    def perform_create(self, serializer):
        period = serializer.validated_data["period"]
        if period.status == "closed":
            raise BusinessRuleError("Period is closed.")
        rtype = serializer.validated_data.get("run_type", "regular")
        if rtype == "regular" and period.runs.filter(run_type="regular").exclude(status="reversed").exists():
            raise BusinessRuleError("A regular run already exists for this period. Use a supplementary run.")
        if rtype == "reversal":
            raise BusinessRuleError("Reversals are created from a released run.")
        serializer.save(number=period.runs.count() + 1)

    def perform_update(self, serializer):
        if serializer.instance.is_locked:
            raise BusinessRuleError("This run is locked.")
        serializer.save()

    def perform_destroy(self, instance):
        if instance.status not in ("draft", "calculated", "rejected"):
            raise BusinessRuleError("Only unsubmitted runs can be deleted.")
        instance.delete()

    @action(detail=True, methods=["post"])
    def calculate(self, request, pk=None):
        run = services.calculate_run(self.get_object(), request.user)
        return Response(self.get_serializer(run).data)

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        run = services.submit_run(self.get_object(), request.user)
        return Response(self.get_serializer(run).data)

    @action(detail=True, methods=["post"])
    def release(self, request, pk=None):
        run = services.release_run(self.get_object(), request.user, publish=request.data.get("publish", True))
        return Response(self.get_serializer(run).data)

    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        run = self.get_object()
        if run.status != "paid":
            raise BusinessRuleError("Payslips can be published after release.")
        services.publish_payslips(run)
        return Response({"detail": "Payslips published."})

    @action(detail=True, methods=["post"])
    def reverse(self, request, pk=None):
        rev = services.reverse_run(self.get_object(), request.user, request.data.get("reason", ""))
        return Response(self.get_serializer(rev).data, status=201)

    @action(detail=True)
    def payslips(self, request, pk=None):
        # bypass the run-level filters: ?status= here filters payslips, not runs
        run = get_object_or_404(self.get_queryset(), pk=pk)
        qs = run.payslips.all()
        if request.query_params.get("status"):
            qs = qs.filter(status=request.query_params["status"])
        if request.query_params.get("search"):
            s = request.query_params["search"]
            qs = qs.filter(employee_name__icontains=s) | qs.filter(staff_number__icontains=s, run=run)
        page = self.paginate_queryset(qs.order_by("staff_number"))
        return self.get_paginated_response(PayslipBriefSerializer(page, many=True).data)

    @action(detail=True, url_path=r"report/(?P<kind>[a-z_]+)")
    def report(self, request, pk=None, kind=None):
        run = self.get_object()
        builders = {"register": exports.payroll_register, "paye": exports.paye_schedule, "ssnit": exports.ssnit_report,
                    "journal": exports.gl_journal, "variance": exports.variance_report}
        if kind not in builders:
            raise BusinessRuleError("Unknown report.")
        headers, rows, money_cols = builders[kind](run)
        fmt = request.query_params.get("format")
        if fmt in ("xlsx", "csv"):
            if not has_perm(request.user, "reports.export") and not has_perm(request.user, "payroll.prepare"):
                raise PermissionDenied("Export permission is required.")
            audit.log("export", run, {"report": kind, "rows": len(rows)})
            return tabular_response(headers, rows, f"{kind}-{run.period.name.replace(' ', '-')}", fmt, kind.title(),
                                    totals_for=money_cols)
        return Response({"headers": headers, "rows": rows, "money_columns": money_cols})

    @action(detail=True, url_path="bank-file")
    def bank_file(self, request, pk=None):
        run = self.get_object()
        if run.status not in ("approved", "paid"):
            raise BusinessRuleError("Bank files are available only for approved payroll.")
        method = request.query_params.get("method", "bank")
        headers, rows = exports.bank_file_rows(run, method)
        audit.log("export", run, {"bank_file": method, "rows": len(rows)})
        return tabular_response(headers, rows, f"{method}-payments-{run.period.name.replace(' ', '-')}",
                                request.query_params.get("format", "csv"), "Payments", totals_for=[6])


class PayslipViewSet(TenantModelViewSet):
    """Payslips: payroll staff see all; employees see their own published payslips."""

    queryset = Payslip.objects.select_related("run__period__pay_group", "employee").prefetch_related("lines")
    serializer_class = PayslipSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get"]
    filterset_fields = ["run", "employee", "status"]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if has_perm(user, "payroll.view") and self.request.query_params.get("mine") != "1":
            return qs
        emp = getattr(user, "employee", None)
        if emp is None:
            return qs.none()
        return qs.filter(employee=emp, published_at__isnull=False).exclude(run__run_type="reversal")

    def retrieve(self, request, *args, **kwargs):
        slip = self.get_object()
        if slip.employee == getattr(request.user, "employee", None) and not slip.first_viewed_at:
            slip.first_viewed_at = timezone.now()
            slip.save(update_fields=["first_viewed_at"])
        return Response(self.get_serializer(slip).data)

    @action(detail=True)
    def pdf(self, request, pk=None):
        slip = self.get_object()
        own = slip.employee == getattr(request.user, "employee", None)
        pdf = exports.payslip_pdf(slip, encrypt=own)
        audit.log("download", slip, {"payslip_pdf": True})
        resp = HttpResponse(pdf, content_type="application/pdf")
        resp["Content-Disposition"] = f'inline; filename="payslip-{slip.staff_number}-{slip.run.period.name}.pdf"'
        return resp


class LoanSerializer(SensitiveFieldsMixin, TenantSerializer):
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    loan_type_label = serializers.CharField(source="get_loan_type_display", read_only=True)
    repaid = serializers.SerializerMethodField()

    class Meta(TenantSerializer.Meta):
        model = Loan
        read_only_fields = TenantSerializer.Meta.read_only_fields + [
            "installment_amount", "total_repayable", "balance", "status", "employee"]

    def get_repaid(self, obj):
        return obj.total_repayable - obj.balance


class LoanViewSet(TenantModelViewSet):
    queryset = Loan.objects.select_related("employee")
    serializer_class = LoanSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["status", "loan_type", "employee"]
    http_method_names = ["get", "post"]

    def get_queryset(self):
        qs = super().get_queryset()
        if has_perm(self.request.user, "payroll.view") and self.request.query_params.get("mine") != "1":
            return qs
        return qs.filter(employee=getattr(self.request.user, "employee", None))

    def create(self, request, *args, **kwargs):
        emp_id = request.data.get("employee")
        own = getattr(request.user, "employee", None)
        emp = Employee.objects.get(pk=emp_id) if emp_id else own
        if emp is None or (emp != own and not has_perm(request.user, "payroll.prepare")):
            raise PermissionDenied("Not permitted.")
        loan = services.apply_for_loan(emp, request.data["loan_type"], request.data["principal"],
                                       int(request.data.get("installments", 1)),
                                       dt.date.fromisoformat(request.data["start_date"]),
                                       request.data.get("purpose", ""), request.user,
                                       request.data.get("interest_rate", 0) if has_perm(request.user, "payroll.prepare")
                                       else 0)
        return Response(self.get_serializer(loan).data, status=201)

    @action(detail=True)
    def schedule(self, request, pk=None):
        loan = self.get_object()
        reps = LoanRepayment.objects.filter(loan=loan)
        return Response({"repayments": [{"date": r.date, "amount": r.amount, "balance_after": r.balance_after,
                                         "note": r.note} for r in reps],
                         "projected_months_remaining": int((loan.balance / loan.installment_amount).to_integral_value(
                             rounding="ROUND_CEILING")) if loan.installment_amount else 0})

    @action(detail=True, methods=["post"], url_path="write-off")
    def write_off(self, request, pk=None):
        loan = self.get_object()
        if not has_perm(request.user, "payroll.approve"):
            raise PermissionDenied("Not permitted.")
        loan.status = "written_off"
        loan.save(update_fields=["status", "updated_at"])
        audit.log("payroll", loan, {"action": "written_off", "balance": loan.balance,
                                    "reason": request.data.get("reason", "")})
        return Response({"detail": "Loan written off."})


class SimulateViewSet(TenantModelViewSet):
    """Dry-run a single employee's payslip for a period without saving (what-if / salary review)."""

    perm_module = "payroll"
    perm_read = "payroll.prepare"
    http_method_names = ["post"]

    def create(self, request, *args, **kwargs):
        from decimal import Decimal

        from . import engine

        emp = Employee.objects.get(pk=request.data["employee"])
        if not can_access_employee(request.user, "employees.view_salary", emp):
            raise PermissionDenied("Not permitted.")
        period = PayrollPeriod.objects.get(pk=request.data["period"])
        run = PayrollRun(period=period, run_type="regular", organization=period.organization)
        if request.data.get("basic_salary"):
            emp.basic_salary = Decimal(str(request.data["basic_salary"]))
        inputs, messages, _ = services.build_inputs(run, emp)
        result = engine.calculate(inputs, services.build_rules(services.rate_set_for(period.end_date),
                                                               services.tax_table_for(period.end_date)))
        return Response({
            "messages": messages + result.messages, "gross": result.gross, "taxable_income": result.taxable_income,
            "paye": result.paye, "ssnit_employee": result.ssnit_employee, "net": result.net,
            "employer_cost": result.employer_cost, "total_deductions": result.total_deductions,
            "lines": [{"code": ln.code, "name": ln.name, "type": ln.line_type, "amount": ln.amount}
                      for ln in result.lines]})
