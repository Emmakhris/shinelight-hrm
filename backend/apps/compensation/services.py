"""Salary reviews, bonuses, benefits eligibility/enrolment, total rewards and benefits cost analysis."""

import datetime as dt
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from apps.audit import services as audit
from apps.core.exceptions import BusinessRuleError
from apps.employees.models import ACTIVE_STATUSES, Employee

from .models import (
    BenefitEnrollment,
    BenefitPlan,
    SalaryReviewLine,
)

D0 = Decimal("0")


def q(x):
    return Decimal(x).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ------------------------------------------------------------------ salary review
def _guideline_entry(cycle, employee):
    """Most specific guideline for the employee's grade level and latest performance rating.
    Entries may carry "rating" (e.g. {"min_level": 1, "max_level": 9, "rating": 5, "min": 8, "max": 12,
    "default": 10}); entries without a rating apply to everyone in the grade band."""
    from apps.performance.services import latest_rating

    level = employee.grade.level if employee.grade_id else 0
    rating = latest_rating(employee, before=cycle.effective_date)
    match = None
    for g in cycle.guidelines or []:
        if not g.get("min_level", 0) <= level <= g.get("max_level", 99):
            continue
        if "rating" in g:
            if rating is not None and int(g["rating"]) == rating:
                return g
        elif match is None:
            match = g
    return match


def guideline_for(cycle, employee):
    g = _guideline_entry(cycle, employee)
    return (Decimal(str(g.get("min", 0))), Decimal(str(g.get("max", 100)))) if g else None


def cycle_population(cycle):
    qs = Employee.objects.filter(status__in=ACTIVE_STATUSES, hire_date__lt=cycle.effective_date)
    if cycle.departments.exists():
        from apps.rbac.services import department_descendants

        ids = set()
        for d in cycle.departments.all():
            ids.update(department_descendants(d.id))
        qs = qs.filter(department_id__in=ids)
    return qs


@transaction.atomic
def populate_cycle(cycle):
    if cycle.status not in ("draft", "open", "returned"):
        raise BusinessRuleError("Proposals can only be prepared while the cycle is draft/open.")
    created = 0
    for emp in cycle_population(cycle):
        g = _guideline_entry(cycle, emp)
        default = Decimal(str(g["default"])) if g and "default" in g else cycle.default_increase_percent
        line, was_created = SalaryReviewLine.objects.get_or_create(
            cycle=cycle, employee=emp, defaults={"current_basic": emp.basic_salary, "increase_percent": default})
        if was_created:
            recalc_line(line)
            created += 1
    cycle.status = "open"
    cycle.save(update_fields=["status", "updated_at"])
    return created


def recalc_line(line, increase_percent=None, proposed_basic=None):
    if proposed_basic is not None:
        line.proposed_basic = q(proposed_basic)
        line.increase_percent = (q((line.proposed_basic / line.current_basic - 1) * 100)
                                 if line.current_basic else D0)
    else:
        if increase_percent is not None:
            line.increase_percent = Decimal(str(increase_percent))
        line.proposed_basic = q(line.current_basic * (1 + line.increase_percent / 100))
    rng = guideline_for(line.cycle, line.employee)
    line.outside_guideline = bool(rng and not (rng[0] <= line.increase_percent <= rng[1]))
    if line.outside_guideline and not line.justification:
        line.justification = ""
    line.save()
    return line


def cycle_summary(cycle):
    lines = cycle.lines.filter(excluded=False)
    current = lines.aggregate(s=Sum("current_basic"))["s"] or D0
    proposed = lines.aggregate(s=Sum("proposed_basic"))["s"] or D0
    budget = q(current * cycle.budget_percent / 100)
    increase = proposed - current
    return {"employees": lines.count(), "current_monthly": q(current), "proposed_monthly": q(proposed),
            "monthly_increase": q(increase), "annual_increase": q(increase * 12),
            "average_percent": q(increase / current * 100) if current else D0,
            "budget_monthly": budget, "within_budget": increase <= budget if cycle.budget_percent else True,
            "outside_guideline": lines.filter(outside_guideline=True).count(),
            "missing_justification": lines.filter(outside_guideline=True, justification="").count()}


@transaction.atomic
def submit_cycle(cycle, user):
    from apps.workflow import engine

    if cycle.status not in ("open", "returned"):
        raise BusinessRuleError("Prepare proposals before submitting.")
    s = cycle_summary(cycle)
    if s["missing_justification"]:
        raise BusinessRuleError(f"{s['missing_justification']} proposal(s) outside guidelines need a justification.")
    resubmit = cycle.status == "returned"
    cycle.status = "pending"
    cycle.save(update_fields=["status", "updated_at"])
    if resubmit:
        inst = _instance(cycle)
        if inst and inst.status == "returned":
            engine.resubmit(inst, user)
            return cycle
    engine.start(cycle, "salary_review", user, extra_context={"amount": float(s["annual_increase"]),
                                                              "within_budget": s["within_budget"]})
    return cycle


@transaction.atomic
def apply_cycle(cycle, user):
    """Apply approved proposals as effective-dated salary changes."""
    from apps.employees.services import apply_change

    if cycle.status != "approved":
        raise BusinessRuleError("Only approved reviews can be applied.")
    n = 0
    for line in cycle.lines.filter(excluded=False, applied=False).select_related("employee"):
        if line.proposed_basic == line.current_basic and not line.proposed_grade_step_id:
            continue
        changes = {"basic_salary": line.proposed_basic}
        if line.proposed_grade_step_id:
            changes["grade_step"] = line.proposed_grade_step
            changes["grade"] = line.proposed_grade_step.grade
        apply_change(line.employee, "salary_change", cycle.effective_date, changes,
                     reason=f"{cycle.name}: {line.increase_percent}%", reference=f"SRC-{cycle.id}", user=user)
        line.applied = True
        line.save(update_fields=["applied"])
        n += 1
    cycle.status = "applied"
    cycle.applied_at = timezone.now()
    cycle.applied_by = user
    cycle.save()
    audit.log("update", cycle, {"applied_lines": n})
    return n


def _instance(obj):
    from django.contrib.contenttypes.models import ContentType

    from apps.workflow.models import WorkflowInstance

    return WorkflowInstance.objects.filter(content_type=ContentType.objects.get_for_model(obj),
                                           object_id=obj.pk).order_by("-id").first()


# ------------------------------------------------------------------ bonuses
def bonus_amount(scheme, employee, value=None):
    v = Decimal(str(value if value is not None else scheme.default_value))
    if scheme.basis == "percent_basic":
        return q(employee.basic_salary * v / 100)
    if scheme.basis == "months_basic":
        return q(employee.basic_salary * v)
    return q(v)


@transaction.atomic
def submit_bonus(scheme, user):
    from apps.workflow import engine

    if scheme.status not in ("draft", "open", "returned"):
        raise BusinessRuleError("Scheme is not editable.")
    if not scheme.awards.exists():
        raise BusinessRuleError("Add awards before submitting.")
    total = scheme.awards.aggregate(s=Sum("amount"))["s"] or D0
    resubmit = scheme.status == "returned"
    scheme.status = "pending"
    scheme.save(update_fields=["status", "updated_at"])
    if resubmit:
        inst = _instance(scheme)
        if inst and inst.status == "returned":
            engine.resubmit(inst, user)
            return scheme
    engine.start(scheme, "bonus_scheme", user, extra_context={"amount": float(total)})
    return scheme


@transaction.atomic
def post_bonus_to_payroll(scheme):
    """On approval: each award becomes a BONUS payroll adjustment (bonus tax treatment applies)."""
    from apps.payroll.models import PayElement, PayrollAdjustment

    if scheme.pay_period is None:
        raise BusinessRuleError("Set the payroll period in which the bonus is paid.")
    el = PayElement.objects.filter(code="BONUS").first()
    if el is None:
        raise BusinessRuleError("Pay element BONUS is not configured.")
    for award in scheme.awards.filter(payroll_adjustment__isnull=True):
        award.payroll_adjustment = PayrollAdjustment.objects.create(
            employee=award.employee, period=scheme.pay_period, element=el, amount=award.amount,
            reason=f"{scheme.name}"[:255], is_system=True)
        award.save(update_fields=["payroll_adjustment"])


# ------------------------------------------------------------------ benefits
def eligibility(plan: BenefitPlan, employee) -> list[str]:
    """Reasons the employee is NOT eligible (empty = eligible)."""
    reasons = []
    if not plan.is_active:
        reasons.append("Plan is closed.")
    if plan.categories.exists() and not plan.categories.filter(pk=employee.category_id).exists():
        reasons.append("Not available to your employee category.")
    level = employee.grade.level if employee.grade_id else 0
    if plan.min_grade_level and level < plan.min_grade_level:
        reasons.append("Requires a higher grade.")
    if plan.employment_types and employee.employment_type not in plan.employment_types:
        reasons.append("Not available to your employment type.")
    if plan.min_service_months:
        today = dt.date.today()
        months = (today.year - employee.hire_date.year) * 12 + today.month - employee.hire_date.month
        if months < plan.min_service_months:
            reasons.append(f"Requires {plan.min_service_months} months of service.")
    return reasons


@transaction.atomic
def enroll(plan, employee, user, start_date, dependants=None):
    from apps.workflow import engine

    reasons = eligibility(plan, employee)
    if reasons:
        raise BusinessRuleError(" ".join(reasons))
    dependants = dependants or []
    if len(dependants) > plan.max_dependants:
        raise BusinessRuleError(f"This plan covers at most {plan.max_dependants} dependant(s).")
    if BenefitEnrollment.objects.filter(plan=plan, employee=employee, status__in=["pending", "active"]).exists():
        raise BusinessRuleError("Already enrolled (or pending) in this plan.")
    e = BenefitEnrollment.objects.create(plan=plan, employee=employee, start_date=start_date, dependants=dependants)
    if plan.requires_approval:
        engine.start(e, "benefit_enrollment", user, subject_employee=employee,
                     extra_context={"plan_type": plan.plan_type, "amount": float(e.employee_cost)})
    else:
        activate(e)
    return e


@transaction.atomic
def activate(enrollment):
    from apps.payroll.models import EmployeePayElement

    enrollment.status = "active"
    plan = enrollment.plan
    if plan.deduction_element_id and enrollment.employee_cost > 0:
        enrollment.pay_element = EmployeePayElement.objects.create(
            employee=enrollment.employee, element=plan.deduction_element, amount=enrollment.employee_cost,
            start_date=enrollment.start_date, end_date=enrollment.end_date, reference=f"BEN-{enrollment.id}",
            note=plan.name)
    enrollment.save()


@transaction.atomic
def end_enrollment(enrollment, end_date, user=None):
    if enrollment.status != "active":
        raise BusinessRuleError("Only active enrolments can be ended.")
    enrollment.end_date = end_date
    enrollment.status = "ended" if end_date <= dt.date.today() else "active"
    enrollment.save()
    if enrollment.pay_element_id:
        pe = enrollment.pay_element
        pe.end_date = end_date
        pe.save(update_fields=["end_date"])
    return enrollment


def auto_enroll(plan, start_date=None):
    start_date = start_date or dt.date.today()
    n = 0
    for emp in Employee.objects.filter(status__in=ACTIVE_STATUSES):
        if eligibility(plan, emp):
            continue
        if BenefitEnrollment.objects.filter(plan=plan, employee=emp, status__in=["pending", "active"]).exists():
            continue
        e = BenefitEnrollment.objects.create(plan=plan, employee=emp, start_date=start_date)
        activate(e)
        n += 1
    return n


def active_enrollments(on_date=None):
    on_date = on_date or dt.date.today()
    return BenefitEnrollment.objects.filter(status="active", start_date__lte=on_date).filter(
        Q(end_date__isnull=True) | Q(end_date__gte=on_date))


def benefits_cost(months_ahead=12):
    """Monthly and annual cost by plan, with a simple forecast (current enrolment × months)."""
    rows = []
    for plan in BenefitPlan.objects.filter(is_active=True):
        enr = list(active_enrollments().filter(plan=plan))
        employer = plan.employer_monthly_cost * len(enr)
        employee = sum((e.employee_cost for e in enr), D0)
        rows.append({"plan": plan.name, "type": plan.get_plan_type_display(), "members": len(enr),
                     "dependants": sum(len(e.dependants or []) for e in enr),
                     "employer_monthly": q(employer), "employee_monthly": q(employee),
                     "employer_forecast": q(employer * months_ahead), "total_forecast": q((employer + employee) * months_ahead)})
    return rows


# ------------------------------------------------------------------ total rewards
def total_rewards(employee, year=None):
    """Annual value of salary, allowances, employer contributions and benefits (from released payroll,
    annualised from the latest payslip where the year is incomplete)."""
    from apps.payroll.models import Payslip, PayslipLine

    year = year or dt.date.today().year
    slips = Payslip.objects.filter(employee=employee, run__status="paid", run__period__end_date__year=year)\
        .exclude(run__run_type="reversal")
    months = slips.filter(run__run_type="regular").count()
    lines = PayslipLine.objects.filter(payslip__in=slips)
    by_cat = {}
    for ln in lines.values("line_type", "category", "name").annotate(total=Sum("amount")):
        if ln["line_type"] == "earning":
            key = {"basic": "Basic salary", "overtime": "Overtime", "bonus": "Bonuses", "arrears": "Arrears"}.get(
                ln["category"], "Allowances")
            by_cat[key] = by_cat.get(key, D0) + ln["total"]
    employer = {"SSNIT (employer 13%)": slips.aggregate(s=Sum("ssnit_employer"))["s"] or D0,
                "Provident fund (employer)": slips.aggregate(s=Sum("tier3_employer"))["s"] or D0}
    benefits = []
    for e in active_enrollments().filter(employee=employee).select_related("plan"):
        start = max(e.start_date, dt.date(year, 1, 1))
        end = min(e.end_date or dt.date(year, 12, 31), dt.date(year, 12, 31))
        m = max((end.year - start.year) * 12 + end.month - start.month + 1, 0)
        benefits.append({"plan": e.plan.name, "employer_value": q(e.plan.employer_monthly_cost * m),
                         "your_contribution": q(e.employee_cost * m)})
    cash = sum(by_cat.values(), D0)
    emp_total = sum(employer.values(), D0)
    ben_total = sum((b["employer_value"] for b in benefits), D0)
    projected = None
    if 0 < months < 12:
        projected = q((cash + emp_total) / months * 12 + ben_total)
    return {"employee": employee.full_name, "staff_number": employee.staff_number, "year": year,
            "months_paid": months, "cash": {k: q(v) for k, v in by_cat.items()}, "cash_total": q(cash),
            "employer_contributions": {k: q(v) for k, v in employer.items()}, "employer_total": q(emp_total),
            "benefits": benefits, "benefits_total": q(ben_total), "total": q(cash + emp_total + ben_total),
            "projected_annual_total": projected}
