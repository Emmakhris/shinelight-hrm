"""Payroll orchestration: builds engine inputs from HR data, persists results, and enforces the
Draft -> Calculated -> Submitted -> Approved -> Paid pipeline with maker-checker controls."""

import calendar
import datetime as dt
from decimal import Decimal

from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from apps.audit import services as audit
from apps.core.exceptions import BusinessRuleError
from apps.core.services import working_days
from apps.employees.models import Employee
from apps.notifications.services import notify

from . import engine
from .models import (
    EmployeePayElement,
    EmployeeTaxRelief,
    Loan,
    LoanRepayment,
    PayElement,
    PayrollAdjustment,
    PayrollPeriod,
    PayrollRun,
    Payslip,
    PayslipLine,
    StatutoryRateSet,
    TaxRelief,
    TaxTable,
)

D0 = Decimal("0")


# ------------------------------------------------------------------ rules
def rate_set_for(on_date) -> StatutoryRateSet:
    rs = (StatutoryRateSet.objects.filter(effective_from__lte=on_date)
          .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=on_date)).order_by("-effective_from").first())
    if rs is None:
        raise BusinessRuleError("No statutory rate set is effective for this period. Configure SSNIT/tax rates.")
    return rs


def tax_table_for(on_date) -> TaxTable:
    t = (TaxTable.objects.filter(effective_from__lte=on_date)
         .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=on_date)).order_by("-effective_from").first())
    if t is None:
        raise BusinessRuleError("No PAYE tax table is effective for this period.")
    return t


def build_rules(rs: StatutoryRateSet, table: TaxTable) -> engine.Rules:
    return engine.Rules(
        bands=[(b.width, b.rate) for b in table.bands.order_by("order")],
        ssnit_employee_rate=rs.ssnit_employee_rate, ssnit_employer_rate=rs.ssnit_employer_rate,
        tier1_rate=rs.tier1_rate, tier2_rate=rs.tier2_rate, ssnit_cap=rs.ssnit_max_insurable_monthly,
        tier3_exempt_percent=rs.tier3_tax_exempt_max_percent, bonus_rate=rs.bonus_tax_rate,
        bonus_exempt_percent=rs.bonus_exempt_percent_annual_basic,
        ot_qualifying_income=rs.overtime_qualifying_annual_income, ot_rate_low=rs.overtime_rate_low,
        ot_rate_high=rs.overtime_rate_high, ot_threshold_percent=rs.overtime_threshold_percent_basic,
        non_resident_rate=rs.non_resident_rate,
    )


# ------------------------------------------------------------------ periods
def create_period(pay_group, year: int, month: int, pay_day: int = 25) -> PayrollPeriod:
    last = calendar.monthrange(year, month)[1]
    start, end = dt.date(year, month, 1), dt.date(year, month, last)
    pay_date = dt.date(year, month, min(pay_day, last))
    period, _ = PayrollPeriod.objects.get_or_create(pay_group=pay_group, start_date=start, end_date=end,
                                                    defaults={"name": start.strftime("%B %Y"), "pay_date": pay_date})
    return period


def period_days(pay_group, start, end) -> Decimal:
    if pay_group.proration_method == "calendar":
        return Decimal((end - start).days + 1)
    if pay_group.proration_method == "fixed30":
        return Decimal(30)
    return Decimal(working_days(start, end))


def payable_days(pay_group, employee, start, end, unpaid_days: Decimal, absence_days: Decimal) -> Decimal:
    s = max(start, employee.hire_date)
    e = min(end, employee.exit_date) if employee.exit_date else end
    if e < s:
        return D0
    if pay_group.proration_method == "calendar":
        employed = Decimal((e - s).days + 1)
    elif pay_group.proration_method == "fixed30":
        full = period_days(pay_group, start, end)
        employed = full if (s == start and e == end) else Decimal(min((e - s).days + 1, 30))
    else:
        employed = Decimal(working_days(s, e))
    return max(employed - unpaid_days - absence_days, D0)


# ------------------------------------------------------------------ inputs
def _element_input(el: PayElement, assignment: EmployeePayElement | None = None, amount=None, quantity=None,
                   reference=""):
    return engine.ElementInput(
        code=el.code, name=el.name, element_type=el.element_type, category=el.category, calculation=el.calculation,
        amount=Decimal(amount if amount is not None else (assignment.amount if assignment and assignment.amount
                                                          is not None else el.default_amount)),
        percent=Decimal(assignment.percent if assignment and assignment.percent is not None else el.default_percent),
        quantity=quantity if quantity is not None else (assignment.quantity if assignment else None),
        multiplier=el.multiplier, formula=el.formula, tax_treatment=el.tax_treatment, prorate=el.prorate,
        gl_account=el.gl_account, order=el.order, show=el.show_on_payslip, element_id=el.id,
        reference=reference or (assignment.reference if assignment else ""),
    )


def ytd_totals(employee, year, before_date):
    qs = Payslip.objects.filter(employee=employee, run__status="paid", run__period__end_date__year=year,
                                run__period__end_date__lt=before_date)
    agg = qs.aggregate(gross=Sum("gross_pay"), paye=Sum("paye"), ssnit=Sum("ssnit_employee"), net=Sum("net_pay"),
                       bonus_tax=Sum("bonus_tax"))
    ytd_bonus = (PayslipLine.objects.filter(payslip__in=qs, line_type="earning", category="bonus")
                 .aggregate(s=Sum("amount"))["s"] or D0)
    return {k: (v or D0) for k, v in agg.items()} | {"bonus": ytd_bonus}


def annual_reliefs(employee, on_date) -> Decimal:
    total = D0
    claims = EmployeeTaxRelief.objects.filter(employee=employee, approved=True, start_date__lte=on_date).filter(
        Q(end_date__isnull=True) | Q(end_date__gte=on_date)).select_related("relief")
    for c in claims:
        relief = (TaxRelief.objects.filter(code=c.relief.code, effective_from__lte=on_date)
                  .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=on_date))
                  .order_by("-effective_from").first()) or c.relief
        if relief.percent_of_income:
            total += engine.pct(employee.basic_salary * 12, relief.percent_of_income)
        else:
            total += relief.annual_amount * min(c.quantity, relief.max_quantity)
    return total


def build_inputs(run: PayrollRun, employee: Employee):
    from apps.attendance.models import AttendancePeriodSummary
    from apps.leave.services import approved_unpaid_days

    period = run.period
    group = period.pay_group
    profile = employee.pay_profile
    start, end = period.start_date, period.end_date
    final = run.run_type == "final"
    supplementary = run.run_type == "supplementary"

    unpaid = approved_unpaid_days(employee, start, end)
    att = AttendancePeriodSummary.objects.filter(employee=employee, period_start=start, period_end=end).first()
    absence = att.unexcused_absence_days if att else D0
    days_total = period_days(group, start, end)
    days_pay = D0 if supplementary else payable_days(group, employee, start, end, unpaid, absence)
    messages = []
    if unpaid:
        messages.append(f"{unpaid} day(s) approved unpaid leave deducted.")
    if absence:
        messages.append(f"{absence} day(s) unexcused absence deducted.")

    elements = []
    if not supplementary:
        assigned = EmployeePayElement.objects.filter(employee=employee, start_date__lte=end).filter(
            Q(end_date__isnull=True) | Q(end_date__gte=start)).select_related("element")
        assigned_ids = set()
        for a in assigned:
            if a.element.is_active:
                elements.append(_element_input(a.element, a))
                assigned_ids.add(a.element_id)
        for el in PayElement.objects.filter(applies_to_all=True, is_active=True).exclude(id__in=assigned_ids):
            elements.append(_element_input(el))
        # concurrent/acting allowances
        for ca in employee.concurrent_assignments.filter(start_date__lte=end).filter(
                Q(end_date__isnull=True) | Q(end_date__gte=start)):
            if ca.allowance_amount:
                elements.append(engine.ElementInput(code=f"ACTING_{ca.id}", name=f"Acting allowance ({ca.position})",
                                                    element_type="earning", category="allowance",
                                                    amount=ca.allowance_amount, prorate=True))
    for adj in PayrollAdjustment.objects.filter(employee=employee, period=period).select_related("element"):
        el = adj.element
        ei = _element_input(el, amount=adj.amount, quantity=adj.quantity, reference=adj.reason[:100])
        ei.calculation = "fixed" if el.calculation not in ("hourly", "daily") or adj.quantity is None else el.calculation
        ei.prorate = False
        elements.append(ei)

    loans = []
    if not supplementary or final:
        for loan in Loan.objects.filter(employee=employee, status="active", start_date__lte=end, balance__gt=0):
            loans.append(engine.LoanInput(loan.id, loan.get_loan_type_display(), loan.installment_amount, loan.balance,
                                          "advance" if loan.loan_type == "salary_advance" else "loan"))

    leave_days = D0
    if final and employee.organization.settings.get("leave_encashment", False):
        from apps.leave.models import LeaveType
        from apps.leave.services import balance

        annual = LeaveType.objects.filter(code="annual").first()
        if annual:
            leave_days = max(balance(employee, annual, end.year)["available"], D0)

    ytd = ytd_totals(employee, end.year, start)
    inputs = engine.PayInputs(
        monthly_basic=employee.basic_salary, days_in_period=days_total, days_payable=days_pay,
        is_resident=profile.is_tax_resident, paye_exempt=profile.paye_exempt,
        ssnit_applicable=profile.ssnit_applicable and not supplementary,
        tier3_employee_percent=profile.tier3_employee_percent, tier3_employer_percent=profile.tier3_employer_percent,
        hours_per_month=group.hours_per_month,
        ot_hours_normal=att.ot_normal_hours if att and not supplementary else D0,
        ot_hours_weekend=att.ot_weekend_hours if att and not supplementary else D0,
        ot_hours_holiday=att.ot_holiday_hours if att and not supplementary else D0,
        ot_weekday_multiplier=group.ot_weekday_multiplier, ot_weekend_multiplier=group.ot_weekend_multiplier,
        ot_holiday_multiplier=group.ot_holiday_multiplier, elements=elements, loans=loans,
        annual_reliefs=annual_reliefs(employee, end), ytd_bonus=ytd["bonus"], recover_full_loans=final,
        leave_encashment_days=leave_days, min_net_percent=group.min_net_pay_percent,
    )
    return inputs, messages, ytd


def employees_for_run(run: PayrollRun):
    period = run.period
    if run.employees.exists():
        return run.employees.all()
    return (Employee.objects.filter(pay_profile__pay_group=period.pay_group, hire_date__lte=period.end_date)
            .filter(Q(exit_date__isnull=True) | Q(exit_date__gte=period.start_date))
            .exclude(status="exited", exit_date__lt=period.start_date)
            .select_related("pay_profile", "department", "job_title", "grade", "cost_center"))


# ------------------------------------------------------------------ calculation
@transaction.atomic
def calculate_run(run: PayrollRun, user) -> PayrollRun:
    run = PayrollRun.objects.select_for_update().get(pk=run.pk)
    if run.status not in ("draft", "calculated", "rejected"):
        raise BusinessRuleError("Only draft, calculated or rejected runs can be (re)calculated.")
    if run.period.status == "closed":
        raise BusinessRuleError("The payroll period is closed.")
    rs = rate_set_for(run.period.end_date)
    table = tax_table_for(run.period.end_date)
    rules = build_rules(rs, table)
    run.payslips.all().delete()
    previous = previous_payslips(run)
    for emp in employees_for_run(run):
        if not hasattr(emp, "pay_profile"):
            continue
        inputs, pre_messages, ytd = build_inputs(run, emp)
        try:
            result = engine.calculate(inputs, rules)
        except Exception as exc:  # formula errors etc. are surfaced per employee
            Payslip.objects.create(run=run, employee=emp, staff_number=emp.staff_number,
                                   employee_name=emp.full_name, status="error", messages=[str(exc)])
            continue
        _persist_payslip(run, emp, inputs, result, pre_messages, ytd, previous.get(emp.id))
    run.rate_set, run.tax_table = rs, table
    run.status = "calculated"
    run.calculated_at = timezone.now()
    run.calculated_by = user
    run.calculation_count += 1
    run.totals = run_totals(run)
    if not rs.verified or not table.verified:
        run.totals["warning"] = "Statutory rates/tax table are not marked as verified."
    run.save()
    audit.log("payroll", run, {"action": "calculated", "employees": run.totals.get("employees"),
                               "net": run.totals.get("net")})
    return run


def bank_snapshot(emp):
    acct = emp.bank_accounts.filter(is_primary=True).first()
    if not acct:
        return {"payment_method": "", "bank_name": "", "bank_branch_code": "", "account_last4": ""}
    return {"payment_method": acct.payment_method, "bank_name": acct.bank_name or acct.get_momo_network_display(),
            "bank_branch_code": acct.branch_code, "account_last4": acct.account_last4 or acct.momo_number[-4:]}


def _persist_payslip(run, emp, inputs, result, pre_messages, ytd, prev):
    messages = pre_messages + result.messages
    status = result.status
    if emp.pay_profile.payment_hold:
        status = "hold"
        messages.append(f"Payment on hold: {emp.pay_profile.hold_reason}")
    snap = bank_snapshot(emp)
    if not snap["payment_method"]:
        status = "error" if status == "ok" else status
        messages.append("No primary bank/MoMo account.")
    if prev is not None and prev.net_pay and run.run_type == "regular":
        change = (result.net - prev.net_pay) / prev.net_pay * 100
        if abs(change) >= run.period.pay_group.variance_threshold_percent:
            messages.append(f"Net pay changed {change:+.1f}% vs previous period.")
            if status == "ok":
                status = "warning"
    elif prev is None and run.run_type == "regular":
        messages.append("New on payroll this period.")
    slip = Payslip.objects.create(
        run=run, employee=emp, staff_number=emp.staff_number, employee_name=emp.full_name,
        department=emp.department.name if emp.department_id else "", job_title=emp.job_title.name if emp.job_title_id else "",
        grade=emp.grade.code if emp.grade_id else "",
        cost_center=emp.cost_center.code if emp.cost_center_id else (
            emp.department.cost_center.code if emp.department_id and emp.department.cost_center_id else ""),
        ssnit_number=emp.ssnit_number, tin=emp.tin, **snap,
        days_in_period=inputs.days_in_period, days_payable=inputs.days_payable, monthly_basic=inputs.monthly_basic,
        basic_pay=result.basic_pay, gross_pay=result.gross, taxable_income=result.taxable_income, paye=result.paye,
        bonus_tax=result.bonus_tax, overtime_tax=result.overtime_tax, ssnit_employee=result.ssnit_employee,
        ssnit_employer=result.ssnit_employer, tier1=result.tier1, tier2=result.tier2,
        tier3_employee=result.tier3_employee, tier3_employer=result.tier3_employer, reliefs=result.reliefs,
        total_deductions=result.total_deductions, net_pay=result.net, employer_cost=result.employer_cost,
        status=status, messages=messages,
        ytd={"gross": str(ytd["gross"] + result.gross), "paye": str(ytd["paye"] + result.paye + result.bonus_tax
                                                                     + result.overtime_tax),
             "ssnit": str(ytd["ssnit"] + result.ssnit_employee), "net": str(ytd["net"] + result.net)},
    )
    PayslipLine.objects.bulk_create([
        PayslipLine(organization_id=slip.organization_id, payslip=slip, element_id=ln.element_id, code=ln.code,
                    name=ln.name, line_type=ln.line_type, category=ln.category, quantity=ln.quantity, rate=ln.rate,
                    amount=ln.amount, taxable=ln.taxable, gl_account=ln.gl_account, reference=ln.reference,
                    show_on_payslip=ln.show, order=ln.order)
        for ln in result.lines
    ])
    return slip


def previous_payslips(run):
    prev_run = (PayrollRun.objects.filter(period__pay_group=run.period.pay_group, run_type="regular", status="paid",
                                          period__end_date__lt=run.period.start_date)
                .order_by("-period__end_date").first())
    if prev_run is None:
        return {}
    return {p.employee_id: p for p in prev_run.payslips.all()}


def run_totals(run):
    agg = run.payslips.aggregate(
        gross=Sum("gross_pay"), net=Sum("net_pay"), paye=Sum("paye"), bonus_tax=Sum("bonus_tax"),
        overtime_tax=Sum("overtime_tax"), ssnit_employee=Sum("ssnit_employee"), ssnit_employer=Sum("ssnit_employer"),
        tier1=Sum("tier1"), tier2=Sum("tier2"), tier3=Sum("tier3_employee"), deductions=Sum("total_deductions"),
        employer_cost=Sum("employer_cost"))
    totals = {k: str(engine.q(v or D0)) for k, v in agg.items()}
    totals["employees"] = run.payslips.count()
    totals["errors"] = run.payslips.filter(status="error").count()
    totals["warnings"] = run.payslips.filter(status="warning").count()
    totals["on_hold"] = run.payslips.filter(status="hold").count()
    return totals


# ------------------------------------------------------------------ approval pipeline
@transaction.atomic
def submit_run(run: PayrollRun, user):
    from apps.workflow import engine as wf

    if run.status != "calculated":
        raise BusinessRuleError("Calculate the payroll before submitting it.")
    if run.payslips.filter(status="error").exists():
        raise BusinessRuleError("Resolve payslip errors before submitting.")
    run.status = "submitted"
    run.submitted_at = timezone.now()
    run.submitted_by = user
    run.save(update_fields=["status", "submitted_at", "submitted_by", "updated_at"])
    wf.start(run, "payroll_run", user, extra_context={"net": float(Decimal(run.totals.get("net", "0"))),
                                                      "employees": run.totals.get("employees", 0)})
    audit.log("payroll", run, {"action": "submitted"})
    return run


def on_run_approved(run: PayrollRun, instance):
    approver_task = instance.tasks.filter(status="approved").order_by("-acted_at").first()
    approver = approver_task.acted_by if approver_task else None
    if approver and approver.id in (run.calculated_by_id, run.submitted_by_id):
        raise BusinessRuleError("Payroll must be approved by someone other than the preparer.")
    run.status = "approved"
    run.approved_at = timezone.now()
    run.approved_by = approver
    run.save(update_fields=["status", "approved_at", "approved_by", "updated_at"])
    audit.log("payroll", run, {"action": "approved"}, actor=approver)


def on_run_rejected(run: PayrollRun, instance):
    run.status = "rejected"
    run.save(update_fields=["status", "updated_at"])


@transaction.atomic
def release_run(run: PayrollRun, user, publish=True):
    """Lock the run, post loan repayments, lock attendance, and publish payslips."""
    from apps.attendance.models import AttendanceDay, AttendancePeriodSummary

    run = PayrollRun.objects.select_for_update().get(pk=run.pk)
    if run.status != "approved":
        raise BusinessRuleError("Only approved payroll can be released.")
    if user.id in (run.calculated_by_id, run.submitted_by_id) and not user.is_superuser:
        raise BusinessRuleError("The preparer cannot release payroll (segregation of duties).")
    for slip in run.payslips.select_related("employee"):
        for line in slip.lines.filter(code__startswith="LOAN_"):
            loan = Loan.objects.select_for_update().get(pk=int(line.reference))
            loan.balance = max(loan.balance - line.amount, D0)
            if loan.balance == 0:
                loan.status = "completed"
            loan.save(update_fields=["balance", "status", "updated_at"])
            LoanRepayment.objects.create(loan=loan, payslip=slip, date=run.period.pay_date, amount=line.amount,
                                         balance_after=loan.balance, note=f"Payroll {run.period.name}")
    p = run.period
    AttendancePeriodSummary.objects.filter(period_start=p.start_date, period_end=p.end_date).update(locked=True)
    AttendanceDay.objects.filter(date__range=(p.start_date, p.end_date),
                                 employee__in=run.payslips.values("employee")).update(locked=True)
    run.status = "paid"
    run.released_at = timezone.now()
    run.released_by = user
    run.save(update_fields=["status", "released_at", "released_by", "updated_at"])
    audit.log("payroll", run, {"action": "released", "net": run.totals.get("net")})
    if publish:
        publish_payslips(run)
    return run


def publish_payslips(run: PayrollRun):
    now = timezone.now()
    run.payslips.filter(published_at__isnull=True).update(published_at=now)
    run.payslips_published = True
    run.save(update_fields=["payslips_published", "updated_at"])
    users = [s.employee.user for s in run.payslips.select_related("employee__user") if s.employee.user_id]
    notify("payroll.payslip_ready", users, {"period": run.period.name, "link": "/me/payslips"})


@transaction.atomic
def reverse_run(run: PayrollRun, user, reason: str) -> PayrollRun:
    """Create a reversal run negating every payslip and restore loan balances."""
    if run.status != "paid":
        raise BusinessRuleError("Only released payroll can be reversed.")
    if not reason:
        raise BusinessRuleError("A reason is required to reverse payroll.")
    rev = PayrollRun.objects.create(period=run.period, run_type="reversal", status="paid", reversal_of=run,
                                    number=run.period.runs.count() + 1, description=f"Reversal: {reason}",
                                    rate_set=run.rate_set, tax_table=run.tax_table, calculated_by=user,
                                    calculated_at=timezone.now(), released_by=user, released_at=timezone.now())
    money_fields = ["basic_pay", "gross_pay", "taxable_income", "paye", "bonus_tax", "overtime_tax", "ssnit_employee",
                    "ssnit_employer", "tier1", "tier2", "tier3_employee", "tier3_employer", "reliefs",
                    "total_deductions", "net_pay", "employer_cost"]
    for slip in run.payslips.all():
        lines = list(slip.lines.all())
        copy = Payslip.objects.get(pk=slip.pk)
        copy.pk = None
        copy.run = rev
        for f in money_fields:
            setattr(copy, f, -getattr(slip, f))
        copy.messages = [f"Reversal of {run}"]
        copy.published_at = None
        copy.save()
        for ln in lines:
            ln.pk = None
            ln.payslip = copy
            ln.amount = -ln.amount
            ln.save()
        for rp in LoanRepayment.objects.filter(payslip=slip):
            loan = rp.loan
            loan.balance += rp.amount
            loan.status = "active"
            loan.save(update_fields=["balance", "status", "updated_at"])
            LoanRepayment.objects.create(loan=loan, payslip=copy, date=dt.date.today(), amount=-rp.amount,
                                         balance_after=loan.balance, note=f"Reversal: {reason}")
    rev.totals = run_totals(rev)
    rev.save(update_fields=["totals"])
    run.status = "reversed"
    run.save(update_fields=["status", "updated_at"])
    audit.log("payroll", run, {"action": "reversed", "reason": reason, "reversal_run": rev.id})
    return rev


# ------------------------------------------------------------------ retro / arrears
@transaction.atomic
def generate_retro_arrears(period: PayrollPeriod, user=None) -> list[PayrollAdjustment]:
    """Back-dated salary changes: compare basic paid in earlier released periods of the year with the
    basic now effective for those periods, and create arrears adjustments for the difference."""
    from apps.employees.services import as_of

    arrears_el = PayElement.objects.filter(code="ARREARS").first()
    if arrears_el is None:
        raise BusinessRuleError("Pay element ARREARS is not configured.")
    PayrollAdjustment.objects.filter(period=period, is_system=True, element=arrears_el).delete()
    created = []
    paid = Payslip.objects.filter(run__status="paid", run__run_type="regular",
                                  run__period__pay_group=period.pay_group,
                                  run__period__start_date__lt=period.start_date,
                                  run__period__start_date__year=period.start_date.year).select_related("run__period",
                                                                                                      "employee")
    diffs: dict[int, Decimal] = {}
    for slip in paid:
        rec = as_of(slip.employee, slip.run.period.end_date)
        if rec is None or rec.basic_salary == slip.monthly_basic:
            continue
        factor = (slip.days_payable / slip.days_in_period) if slip.days_in_period else Decimal(1)
        diffs[slip.employee_id] = diffs.get(slip.employee_id, D0) + engine.q((rec.basic_salary - slip.monthly_basic)
                                                                            * factor)
    for emp_id, amount in diffs.items():
        already = (PayslipLine.objects.filter(payslip__employee_id=emp_id, payslip__run__status="paid",
                                              payslip__run__period__start_date__year=period.start_date.year,
                                              code="ARREARS", line_type="earning")
                   .aggregate(s=Sum("amount"))["s"] or D0)
        amount = amount - already
        if amount:
            created.append(PayrollAdjustment.objects.create(employee_id=emp_id, period=period, element=arrears_el,
                                                            amount=amount, reason="Salary arrears (retroactive change)",
                                                            is_system=True))
    return created


# ------------------------------------------------------------------ loans
def loan_schedule(principal: Decimal, interest_rate: Decimal, installments: int):
    months = Decimal(installments)
    interest = engine.q(principal * interest_rate / 100 * months / 12)
    total = principal + interest
    installment = engine.q(total / months)
    return total, installment


@transaction.atomic
def apply_for_loan(employee, loan_type, principal, installments, start_date, purpose, user, interest_rate=D0):
    from apps.workflow import engine as wf

    principal = Decimal(principal)
    if principal <= 0 or installments < 1:
        raise BusinessRuleError("Enter a valid amount and number of instalments.")
    limits = employee.organization.settings.get("loan_limits", {})
    max_months = limits.get(loan_type, {}).get("max_installments")
    if max_months and installments > max_months:
        raise BusinessRuleError(f"Maximum of {max_months} instalments for this loan type.")
    multiple = limits.get(loan_type, {}).get("max_salary_multiple")
    if multiple and principal > employee.basic_salary * Decimal(str(multiple)):
        raise BusinessRuleError(f"Amount exceeds {multiple} x monthly basic salary.")
    if Loan.objects.filter(employee=employee, loan_type=loan_type, status__in=["pending", "active"]).exists():
        raise BusinessRuleError("You already have an active or pending loan of this type.")
    total, installment = loan_schedule(principal, Decimal(interest_rate), installments)
    if installment > employee.basic_salary * Decimal("0.5"):
        raise BusinessRuleError("Monthly instalment would exceed 50% of basic salary.")
    loan = Loan.objects.create(employee=employee, loan_type=loan_type, principal=principal,
                               interest_rate=interest_rate, installments=installments, installment_amount=installment,
                               total_repayable=total, balance=total, start_date=start_date, purpose=purpose)
    wf.start(loan, "loan_request", user, subject_employee=employee,
             extra_context={"amount": float(principal), "loan_type": loan_type})
    return loan
