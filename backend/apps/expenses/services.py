"""Travel requests, advances, expense claims, retirement and reimbursement.

Finance keeps control of disbursement: approval happens in the workflow, but only users with
`expenses.pay` (separate from the approver) can record payments or push items to payroll."""

import datetime as dt
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from apps.audit import services as audit
from apps.core.exceptions import BusinessRuleError
from apps.core.services import next_number

from .models import ExpenseBudget, ExpenseClaim, PerDiemRate, TravelRequest

D0 = Decimal("0")
RETIREMENT_DAYS = 14   # days after return to retire an advance
RECEIPT_THRESHOLD = Decimal("50")  # items above this need a receipt (or a reason)


def q(x):
    return Decimal(x).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def per_diem_rate(employee, destination_class, on_date, location=""):
    level = employee.grade.level if employee.grade_id else 0
    qs = PerDiemRate.objects.filter(destination_class=destination_class, is_active=True, effective_from__lte=on_date,
                                    min_grade_level__lte=level, max_grade_level__gte=level).order_by("-effective_from")
    if location:
        specific = qs.filter(location__iexact=location).first()
        if specific:
            return specific
    return qs.filter(location="").first() or qs.first()


def compute_travel(tr: TravelRequest):
    if tr.return_date < tr.departure_date:
        raise BusinessRuleError("Return date cannot be before departure.")
    nights = (tr.return_date - tr.departure_date).days
    tr.per_diem_days = Decimal(nights + 1) if nights else Decimal("1")
    rate = per_diem_rate(tr.employee, tr.destination_class, tr.departure_date, tr.destination.split(",")[0].strip())
    tr.warnings = []
    if rate:
        tr.per_diem_rate = rate.daily_allowance
        tr.currency = rate.currency
        cap = rate.accommodation_cap * nights
        if tr.accommodation_estimate > cap > 0:
            tr.warnings.append(f"Accommodation estimate exceeds the approved cap of {rate.currency} {cap:,.2f}.")
    else:
        tr.warnings.append("No per diem rate configured for this destination and grade.")
    tr.total_estimate = q(tr.per_diem_days * tr.per_diem_rate + tr.accommodation_estimate + tr.transport_estimate
                          + tr.other_estimate)
    if tr.advance_requested > tr.total_estimate:
        raise BusinessRuleError("The advance cannot exceed the total trip estimate.")
    outstanding = TravelRequest.objects.filter(employee=tr.employee, advance_paid__gt=0,
                                               status__in=["approved", "completed"]).exclude(pk=tr.pk)
    if tr.advance_requested and outstanding.exists():
        tr.warnings.append("Employee has an unretired travel advance.")
    tr.warnings += budget_warnings(tr.employee, "travel", tr.total_estimate, tr.departure_date.year)
    return tr


def budget_status(department, year, category="travel"):
    budget = ExpenseBudget.objects.filter(department=department, year=year, category=category).first()
    if budget is None:
        return None
    spent_claims = (ExpenseClaim.objects.filter(employee__department=department, status__in=["approved", "paid"],
                                                created_at__year=year)
                    .aggregate(s=Sum("total"))["s"] or D0)
    committed = (TravelRequest.objects.filter(employee__department=department, status="approved",
                                              departure_date__year=year, claims__isnull=True)
                 .aggregate(s=Sum("total_estimate"))["s"] or D0)
    return {"budget": budget.amount, "spent": spent_claims, "committed": committed,
            "available": budget.amount - spent_claims - committed}


def budget_warnings(employee, category, amount, year):
    if not employee.department_id:
        return []
    st = budget_status(employee.department, year, category) or budget_status(employee.department, year, "travel")
    if st and amount > st["available"]:
        return [f"Exceeds remaining {employee.department.name} budget (available {st['available']:,.2f})."]
    return []


@transaction.atomic
def submit_travel(tr: TravelRequest, user):
    from apps.workflow import engine

    if tr.status not in ("draft", "returned"):
        raise BusinessRuleError("Only draft or returned requests can be submitted.")
    compute_travel(tr)
    if not tr.reference:
        tr.reference = next_number("travel", default_prefix="TR", default_pattern="{prefix}-{year}-{seq:04d}")
    resubmit = tr.status == "returned"
    tr.status = "pending"
    tr.save()
    if resubmit:
        inst = _instance(tr)
        if inst and inst.status == "returned":
            engine.resubmit(inst, user)
            return tr
    engine.start(tr, "travel_request", user, subject_employee=tr.employee,
                 extra_context={"amount": float(tr.total_estimate), "advance": float(tr.advance_requested),
                                "destination_class": tr.destination_class})
    return tr


def _instance(obj):
    from django.contrib.contenttypes.models import ContentType

    from apps.workflow.models import WorkflowInstance

    return WorkflowInstance.objects.filter(content_type=ContentType.objects.get_for_model(obj),
                                           object_id=obj.pk).order_by("-id").first()


@transaction.atomic
def pay_advance(tr: TravelRequest, user, amount, reference, paid_on=None, via_payroll=False):
    if tr.status != "approved":
        raise BusinessRuleError("Advances can only be paid on approved travel.")
    amount = q(amount)
    if amount <= 0 or amount > tr.advance_requested:
        raise BusinessRuleError("Advance must be positive and not exceed the approved amount.")
    if via_payroll:
        _payroll_adjustment(tr.employee, "TRAVEL_ADVANCE", amount, f"Travel advance {tr.reference}")
    tr.advance_paid = amount
    tr.advance_paid_on = paid_on or dt.date.today()
    tr.advance_reference = reference
    tr.retirement_due = tr.return_date + dt.timedelta(days=RETIREMENT_DAYS)
    tr.save()
    audit.log("payroll", tr, {"action": "advance_paid", "amount": amount, "reference": reference})
    return tr


def validate_claim(claim: ExpenseClaim):
    items = list(claim.items.all())
    if not items:
        raise BusinessRuleError("Add at least one expense item.")
    claim.warnings = []
    for it in items:
        if it.amount <= 0:
            raise BusinessRuleError(f"Item '{it.description}' must have a positive amount.")
        if it.amount > RECEIPT_THRESHOLD and not it.receipt_id and not it.receipt_missing_reason:
            raise BusinessRuleError(f"Attach a receipt for '{it.description}' or explain why it is missing.")
        if it.receipt_missing_reason:
            claim.warnings.append(f"No receipt: {it.description} ({it.receipt_missing_reason})")
        if it.date > dt.date.today():
            raise BusinessRuleError("Expense dates cannot be in the future.")
        if (dt.date.today() - it.date).days > 90:
            claim.warnings.append(f"'{it.description}' is more than 90 days old.")
    claim.total = q(sum((it.amount for it in items), D0))
    tr = claim.travel_request
    if tr is not None:
        if tr.employee_id != claim.employee_id:
            raise BusinessRuleError("Travel request belongs to another employee.")
        other = ExpenseClaim.objects.filter(travel_request=tr).exclude(pk=claim.pk).exclude(
            status__in=["rejected", "cancelled"])
        if other.exists():
            raise BusinessRuleError("This trip already has an expense/retirement claim.")
        claim.advance_offset = tr.advance_paid
        trip_dates = [it.date for it in items if not (tr.departure_date - dt.timedelta(days=1) <= it.date
                                                       <= tr.return_date + dt.timedelta(days=1))]
        if trip_dates:
            claim.warnings.append("Some items fall outside the travel dates.")
    else:
        claim.advance_offset = D0
    claim.net_payable = q(claim.total - claim.advance_offset)
    claim.warnings += budget_warnings(claim.employee, items[0].category, claim.total, dt.date.today().year)
    return claim


@transaction.atomic
def submit_claim(claim: ExpenseClaim, user):
    from apps.workflow import engine

    if claim.status not in ("draft", "returned"):
        raise BusinessRuleError("Only draft or returned claims can be submitted.")
    validate_claim(claim)
    if not claim.reference:
        claim.reference = next_number("expense_claim", default_prefix="EC", default_pattern="{prefix}-{year}-{seq:05d}")
    resubmit = claim.status == "returned"
    claim.status = "pending"
    claim.submitted_at = timezone.now()
    claim.save()
    if resubmit:
        inst = _instance(claim)
        if inst and inst.status == "returned":
            engine.resubmit(inst, user)
            return claim
    engine.start(claim, "expense_claim", user, subject_employee=claim.employee,
                 extra_context={"amount": float(claim.total), "has_advance": bool(claim.advance_offset)})
    return claim


def _payroll_adjustment(employee, element_code, amount, reason):
    """Queue an amount into the next open payroll period (reimbursement/advance as earning, recovery as deduction)."""
    from apps.payroll.models import PayElement, PayrollAdjustment, PayrollPeriod

    element = PayElement.objects.filter(code=element_code).first()
    if element is None:
        raise BusinessRuleError(f"Pay element {element_code} is not configured.")
    profile = getattr(employee, "pay_profile", None)
    if profile is None:
        raise BusinessRuleError("Employee has no pay profile.")
    period = (PayrollPeriod.objects.filter(pay_group=profile.pay_group, status="open")
              .exclude(runs__status__in=["submitted", "approved", "paid"]).order_by("start_date").first())
    if period is None:
        raise BusinessRuleError("No open payroll period available. Create the next period first.")
    return PayrollAdjustment.objects.create(employee=employee, period=period, element=element, amount=amount,
                                            reason=reason[:255], is_system=True)


@transaction.atomic
def settle_claim(claim: ExpenseClaim, user, method=None, reference=""):
    """Finance settles an approved claim: positive net → reimburse; negative net → recover the unspent advance."""
    if claim.status != "approved":
        raise BusinessRuleError("Only approved claims can be settled.")
    method = method or claim.payment_method
    approver_ids = _approver_ids(claim)
    if user.id in approver_ids and not user.is_superuser:
        raise BusinessRuleError("The approver of a claim cannot also record its payment (segregation of duties).")
    net = claim.net_payable
    if method == "payroll" and net != 0:
        if net > 0:
            claim.payroll_adjustment = _payroll_adjustment(claim.employee, "REIMBURSEMENT", net,
                                                           f"Expense claim {claim.reference}")
        else:
            claim.payroll_adjustment = _payroll_adjustment(claim.employee, "ADVANCE_RECOVERY", -net,
                                                           f"Unspent advance {claim.reference}")
    elif method in ("bank", "cash") and not reference and net != 0:
        raise BusinessRuleError("Enter the payment / receipt reference.")
    claim.payment_method = method
    claim.payment_reference = reference or ("payroll" if method == "payroll" else "")
    claim.status = "paid"
    claim.paid_at = timezone.now()
    claim.paid_by = user
    claim.save()
    if claim.travel_request_id:
        tr = claim.travel_request
        tr.status = "retired"
        tr.save(update_fields=["status", "updated_at"])
    audit.log("payroll", claim, {"action": "settled", "method": method, "net": net})
    return claim


def _approver_ids(obj):
    inst = _instance(obj)
    if inst is None:
        return set()
    return set(inst.tasks.filter(status="approved").values_list("acted_by_id", flat=True))


def overdue_retirements(today=None):
    today = today or dt.date.today()
    return TravelRequest.objects.filter(advance_paid__gt=0, retirement_due__lt=today,
                                        status__in=["approved", "completed"]).filter(
        Q(claims__isnull=True) | Q(claims__status__in=["draft", "rejected", "cancelled", "returned"])).distinct()


def mark_completed_trips(today=None):
    today = today or dt.date.today()
    return TravelRequest.objects.filter(status="approved", return_date__lt=today).update(status="completed")
