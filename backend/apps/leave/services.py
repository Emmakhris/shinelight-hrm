"""Leave entitlement, balance, validation, approval, cancellation and recall."""

import datetime as dt
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from apps.core.exceptions import BusinessRuleError
from apps.core.services import daterange, holiday_dates, working_days
from apps.notifications.services import notify

from .models import LeaveLedgerEntry, LeavePolicy, LeaveRequest, LeaveType

D0 = Decimal("0")
HALF = Decimal("0.5")


def q2(x) -> Decimal:
    return Decimal(x).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def get_policy(employee, leave_type) -> LeavePolicy | None:
    for p in LeavePolicy.objects.filter(leave_type=leave_type, is_active=True).order_by("priority", "id"):
        if p.matches(employee):
            return p
    return None


def years_of_service(employee, on_date):
    start = employee.original_hire_date or employee.hire_date
    years = on_date.year - start.year - ((on_date.month, on_date.day) < (start.month, start.day))
    return max(years, 0)


def annual_entitlement(employee, policy: LeavePolicy, year: int, prorate=True) -> Decimal:
    days = Decimal(policy.entitlement_days)
    yos = years_of_service(employee, dt.date(year, 12, 31))
    for tier in sorted(policy.service_bonus or [], key=lambda t: t.get("years", 0)):
        if yos >= tier.get("years", 0):
            days = Decimal(policy.entitlement_days) + Decimal(str(tier.get("days", 0)))
    if prorate and policy.prorate_first_year and employee.hire_date.year == year:
        months = 12 - employee.hire_date.month + (1 if employee.hire_date.day <= 15 else 0)
        days = days * Decimal(months) / Decimal(12)
    return q2(days)


def _sum(qs) -> Decimal:
    return qs.aggregate(s=Sum("days"))["s"] or D0


@transaction.atomic
def ensure_year(employee, leave_type, year: int):
    """Initialise entitlement and carry-over for a leave year (idempotent)."""
    if not leave_type.tracks_balance:
        return
    ledger = LeaveLedgerEntry.objects.filter(employee=employee, leave_type=leave_type, year=year)
    policy = get_policy(employee, leave_type)
    if policy is None:
        return
    if not ledger.filter(entry_type__in=["entitlement", "carryover", "opening"]).exists() and \
            not ledger.filter(entry_type="accrual").exists():
        if policy.accrual_method == "upfront":
            LeaveLedgerEntry.objects.create(employee=employee, leave_type=leave_type, year=year,
                                            entry_type="entitlement", days=annual_entitlement(employee, policy, year),
                                            date=max(dt.date(year, 1, 1), employee.hire_date),
                                            note=f"Annual entitlement ({policy.name})")
        # carry over from previous year
        prev = LeaveLedgerEntry.objects.filter(employee=employee, leave_type=leave_type, year=year - 1)
        if prev.exists() and policy.carryover_max_days > 0:
            remaining = _sum(prev)
            carry = min(max(remaining, D0), Decimal(policy.carryover_max_days))
            if carry > 0:
                LeaveLedgerEntry.objects.create(employee=employee, leave_type=leave_type, year=year,
                                                entry_type="carryover", days=carry, date=dt.date(year, 1, 1),
                                                note=f"Carried over from {year - 1}")


def balance(employee, leave_type, year: int | None = None) -> dict:
    year = year or dt.date.today().year
    ensure_year(employee, leave_type, year)
    ledger = LeaveLedgerEntry.objects.filter(employee=employee, leave_type=leave_type, year=year)
    by_type = {t: _sum(ledger.filter(entry_type=t)) for t, _ in LeaveLedgerEntry.TYPES}
    pending = _sum(LeaveRequest.objects.filter(employee=employee, leave_type=leave_type, status="pending",
                                               start_date__year=year))
    total = _sum(ledger)
    return {
        "leave_type": leave_type.id,
        "leave_type_name": leave_type.name,
        "code": leave_type.code,
        "color": leave_type.color,
        "year": year,
        "tracks_balance": leave_type.tracks_balance,
        "opening": by_type["opening"] + by_type["carryover"],
        "entitlement": by_type["entitlement"] + by_type["accrual"],
        "adjustments": by_type["adjustment"] + by_type["expiry"],
        "taken": -(by_type["taken"] + by_type["reversal"]),
        "pending": pending,
        "balance": total,
        "available": total - pending,
    }


def all_balances(employee, year=None):
    types = LeaveType.objects.filter(is_active=True)
    out = []
    for lt in types:
        if lt.gender and employee.gender and lt.gender != employee.gender:
            continue
        out.append(balance(employee, lt, year))
    return out


def calculate_days(leave_type: LeaveType, start: dt.date, end: dt.date, start_half=False, end_half=False) -> Decimal:
    if end < start:
        raise BusinessRuleError("End date cannot be before start date.")
    if leave_type.count_working_days:
        days = Decimal(working_days(start, end))
        holidays = holiday_dates(start, end)

        def is_working(d):
            return d.weekday() < 5 and d not in holidays
    else:
        days = Decimal((end - start).days + 1)

        def is_working(d):
            return True
    if start_half and is_working(start):
        days -= HALF
    if end_half and is_working(end) and (end != start or not start_half):
        days -= HALF
    return max(days, D0)


def overlapping(employee, start, end, exclude_id=None):
    qs = LeaveRequest.objects.filter(employee=employee, status__in=["pending", "approved"],
                                     start_date__lte=end, end_date__gte=start)
    if exclude_id:
        qs = qs.exclude(pk=exclude_id)
    return qs


def staffing_conflicts(request: LeaveRequest) -> list[str]:
    """Warn when colleagues in the same department are away on the same days and staffing drops below minimum."""
    emp = request.employee
    if not emp.department_id:
        return []
    from apps.employees.models import ACTIVE_STATUSES, Employee

    dept = emp.department
    headcount = Employee.objects.filter(department=dept, status__in=ACTIVE_STATUSES).count()
    others = LeaveRequest.objects.filter(employee__department=dept, status__in=["approved", "pending"],
                                         start_date__lte=request.end_date, end_date__gte=request.start_date
                                         ).exclude(employee=emp).select_related("employee")
    warnings = []
    if others:
        names = sorted({o.employee.full_name for o in others})
        warnings.append(f"{len(names)} colleague(s) in {dept.name} also away: {', '.join(names[:5])}"
                        + ("..." if len(names) > 5 else ""))
    if dept.min_staffing:
        worst = 0
        for d in daterange(request.start_date, request.end_date):
            away = sum(1 for o in others if o.start_date <= d <= o.end_date) + 1
            worst = max(worst, away)
        if headcount - worst < dept.min_staffing:
            warnings.append(f"Staffing in {dept.name} would fall to {headcount - worst}, below the minimum of "
                            f"{dept.min_staffing}.")
    if request.relief_officer_id:
        if overlapping(request.relief_officer, request.start_date, request.end_date).exists():
            warnings.append("The relief officer is also on leave during this period.")
    return warnings


def validate(request: LeaveRequest) -> list[str]:
    """Raise for hard rule violations; return soft warnings."""
    lt, emp = request.leave_type, request.employee
    today = dt.date.today()
    if not lt.is_active:
        raise BusinessRuleError("This leave type is not available.")
    if emp.status == "exited":
        raise BusinessRuleError("Exited employees cannot apply for leave.")
    if lt.gender and emp.gender and lt.gender != emp.gender:
        raise BusinessRuleError(f"{lt.name} is not applicable.")
    if not lt.allow_half_day and (request.start_half or request.end_half):
        raise BusinessRuleError(f"Half days are not allowed for {lt.name}.")
    if emp.status == "probation" and not lt.allow_during_probation:
        raise BusinessRuleError(f"{lt.name} is not available during probation.")
    if lt.min_service_months:
        months = (today.year - emp.hire_date.year) * 12 + today.month - emp.hire_date.month
        if months < lt.min_service_months:
            raise BusinessRuleError(f"{lt.name} requires {lt.min_service_months} months of service.")
    request.days = calculate_days(lt, request.start_date, request.end_date, request.start_half, request.end_half)
    if request.days <= 0:
        raise BusinessRuleError("The selected dates contain no working days.")
    if lt.max_days_per_request and request.days > lt.max_days_per_request:
        raise BusinessRuleError(f"Maximum of {lt.max_days_per_request} days per request for {lt.name}.")
    if overlapping(emp, request.start_date, request.end_date, exclude_id=request.pk).exists():
        raise BusinessRuleError("You already have leave booked or pending for some of these dates.")
    needs_doc = lt.requires_attachment and request.days > lt.attachment_after_days
    if needs_doc and not request.attachment_id:
        raise BusinessRuleError(f"A supporting document is required for {lt.name} of more than "
                                f"{lt.attachment_after_days} day(s).")
    warnings = []
    if lt.notice_days and (request.start_date - today).days < lt.notice_days:
        warnings.append(f"Less than the required {lt.notice_days} days' notice.")
    if request.start_date < today:
        warnings.append("Leave start date is in the past (retrospective application).")
    if lt.tracks_balance and not lt.allow_negative_balance:
        if request.start_date.year != request.end_date.year:
            raise BusinessRuleError("Leave spanning two leave years must be split into two requests.")
        bal = balance(emp, lt, request.start_date.year)
        pending_self = request.days if request.status == "pending" and request.pk else D0
        if bal["available"] + pending_self < request.days:
            raise BusinessRuleError(f"Insufficient {lt.name} balance: {bal['available']} day(s) available, "
                                    f"{request.days} requested.", code="insufficient_balance")
    warnings += staffing_conflicts(request)
    return warnings


def expected_return(request: LeaveRequest) -> dt.date:
    d = request.end_date + dt.timedelta(days=1)
    holidays = holiday_dates(d, d + dt.timedelta(days=14))
    while d.weekday() >= 5 or d in holidays:
        d += dt.timedelta(days=1)
    return d


@transaction.atomic
def submit(request: LeaveRequest, user) -> LeaveRequest:
    from apps.workflow import engine

    if request.status not in ("draft", "returned"):
        raise BusinessRuleError("Only draft or returned requests can be submitted.")
    resubmitting = request.status == "returned"
    request.warnings = validate(request)
    request.status = "pending"
    request.submitted_at = timezone.now()
    request.expected_return_date = expected_return(request)
    request.save()
    if resubmitting:
        instance = workflow_instance(request)
        if instance and instance.status == "returned":
            engine.resubmit(instance, user)
            return request
    engine.start(request, "leave_request", user, subject_employee=request.employee)
    return request


def workflow_instance(request):
    from django.contrib.contenttypes.models import ContentType

    from apps.workflow.models import WorkflowInstance

    return WorkflowInstance.objects.filter(content_type=ContentType.objects.get_for_model(request),
                                           object_id=request.pk).order_by("-id").first()


@transaction.atomic
def on_approved(request: LeaveRequest):
    request.status = "approved"
    request.decided_at = timezone.now()
    request.save(update_fields=["status", "decided_at", "updated_at"])
    if request.leave_type.tracks_balance:
        LeaveLedgerEntry.objects.create(employee=request.employee, leave_type=request.leave_type,
                                        year=request.start_date.year, entry_type="taken", days=-request.days,
                                        date=request.start_date, request=request, note="Approved leave")


@transaction.atomic
def cancel(request: LeaveRequest, user, reason=""):
    from apps.workflow import engine

    if request.status == "pending" or request.status == "returned":
        instance = workflow_instance(request)
        if instance and instance.status in ("in_progress", "returned"):
            engine.cancel(instance, user, reason)
        request.status = "cancelled"
        request.save(update_fields=["status", "updated_at"])
        return request
    if request.status == "approved":
        if request.start_date <= dt.date.today():
            raise BusinessRuleError("Leave has already started; ask your supervisor or HR to record a recall.")
        _reverse_ledger(request, request.days, f"Cancelled: {reason}")
        request.status = "cancelled"
        request.save(update_fields=["status", "updated_at"])
        return request
    raise BusinessRuleError("This request cannot be cancelled.")


def _reverse_ledger(request, days, note):
    if request.leave_type.tracks_balance and days > 0:
        LeaveLedgerEntry.objects.create(employee=request.employee, leave_type=request.leave_type,
                                        year=request.start_date.year, entry_type="reversal", days=days,
                                        date=dt.date.today(), request=request, note=note[:255])


@transaction.atomic
def recall(request: LeaveRequest, recall_date: dt.date, reason: str, user):
    """Recall an employee from approved leave; unused days from recall_date are credited back."""
    if request.status != "approved":
        raise BusinessRuleError("Only approved leave can be recalled.")
    if not (request.start_date <= recall_date <= request.end_date):
        raise BusinessRuleError("Recall date must fall within the leave period.")
    unused = calculate_days(request.leave_type, recall_date, request.end_date, False, request.end_half)
    _reverse_ledger(request, unused, f"Recall from {recall_date:%d/%m/%Y}: {reason}")
    request.recall_date = recall_date
    request.recall_reason = reason
    request.status = "recalled"
    request.days = request.days - unused
    request.save()
    if request.employee.user_id:
        notify("leave.recalled", [request.employee.user], {"title": str(request.leave_type), "date": recall_date,
                                                           "reason": reason})
    return unused


def confirm_return(request: LeaveRequest, return_date: dt.date, notes=""):
    if request.status not in ("approved", "recalled"):
        raise BusinessRuleError("Return can only be recorded for approved leave.")
    request.actual_return_date = return_date
    request.return_notes = notes
    request.save(update_fields=["actual_return_date", "return_notes", "updated_at"])
    return request


@transaction.atomic
def adjust(employee, leave_type, days, note, year=None):
    year = year or dt.date.today().year
    ensure_year(employee, leave_type, year)
    return LeaveLedgerEntry.objects.create(employee=employee, leave_type=leave_type, year=year,
                                           entry_type="adjustment", days=Decimal(days), date=dt.date.today(),
                                           note=note)


def run_monthly_accrual(on_date=None, organization=None):
    """Credit 1/12 of the annual entitlement for monthly-accrual policies (idempotent per month)."""
    from apps.employees.models import ACTIVE_STATUSES, Employee

    on_date = on_date or dt.date.today()
    created = 0
    policies = LeavePolicy.all_objects.filter(accrual_method="monthly", is_active=True).select_related("leave_type")
    if organization is not None:
        policies = policies.filter(organization=organization)
    for policy in policies:
        employees = Employee.all_objects.filter(organization_id=policy.organization_id, status__in=ACTIVE_STATUSES,
                                                hire_date__lte=on_date)
        for emp in employees:
            if not policy.matches(emp) or get_policy(emp, policy.leave_type) != policy:
                continue
            exists = LeaveLedgerEntry.all_objects.filter(employee=emp, leave_type=policy.leave_type,
                                                         year=on_date.year, entry_type="accrual",
                                                         date__year=on_date.year, date__month=on_date.month).exists()
            if exists:
                continue
            ensure_year(emp, policy.leave_type, on_date.year)
            # accrual starts from hire, so first-year proration happens naturally
            amount = q2(annual_entitlement(emp, policy, on_date.year, prorate=False) / 12)
            LeaveLedgerEntry.all_objects.create(organization_id=policy.organization_id, employee=emp,
                                                leave_type=policy.leave_type, year=on_date.year,
                                                entry_type="accrual", days=amount, date=on_date,
                                                note=f"Accrual {on_date:%b %Y}")
            created += 1
    return created


def expire_carryover(on_date=None, organization=None):
    """Expire unused carried-over days after the policy's carryover_expiry_months."""
    on_date = on_date or dt.date.today()
    n = 0
    entries = LeaveLedgerEntry.all_objects.filter(entry_type="carryover", year=on_date.year)
    if organization is not None:
        entries = entries.filter(organization=organization)
    for entry in entries.select_related("employee", "leave_type"):
        policy = get_policy(entry.employee, entry.leave_type)
        if not policy or not policy.carryover_expiry_months:
            continue
        expiry = dt.date(entry.year, 1, 1).replace(month=min(1 + policy.carryover_expiry_months, 12))
        if on_date < expiry:
            continue
        if LeaveLedgerEntry.all_objects.filter(employee=entry.employee, leave_type=entry.leave_type,
                                               year=entry.year, entry_type="expiry").exists():
            continue
        taken_before = -_sum(LeaveLedgerEntry.all_objects.filter(
            employee=entry.employee, leave_type=entry.leave_type, year=entry.year,
            entry_type__in=["taken", "reversal"], date__lt=expiry))
        unused = entry.days - min(max(taken_before, D0), entry.days)
        if unused > 0:
            LeaveLedgerEntry.all_objects.create(organization_id=entry.organization_id, employee=entry.employee,
                                                leave_type=entry.leave_type, year=entry.year, entry_type="expiry",
                                                days=-unused, date=on_date, note="Unused carried-over days expired")
            n += 1
    return n


def approved_unpaid_days(employee, start: dt.date, end: dt.date) -> Decimal:
    """Unpaid leave days (approved only) inside a payroll period - payroll uses this, never pending data."""
    total = D0
    for req in LeaveRequest.objects.filter(employee=employee, leave_type__is_paid=False,
                                           status__in=["approved", "recalled"],
                                           start_date__lte=end, end_date__gte=start).select_related("leave_type"):
        s, e = max(req.start_date, start), min(req.end_date, req.recall_date - dt.timedelta(days=1)
                                               if req.recall_date else req.end_date, end)
        if e >= s:
            total += calculate_days(req.leave_type, s, e, req.start_half and s == req.start_date,
                                    req.end_half and e == req.end_date)
    return total


def on_leave_on(on_date: dt.date):
    return LeaveRequest.objects.filter(status="approved", start_date__lte=on_date, end_date__gte=on_date).filter(
        Q(recall_date__isnull=True) | Q(recall_date__gt=on_date))
