"""Exit, retirement and offboarding (features.txt §20): separation requests and approval, notice tracking,
multi-department clearance with automatic checks (assets, loans, advances, exit interview, final pay),
access revocation tied to the final working day with approved extensions, certificates and exit analytics."""

import datetime as dt
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Q, Sum
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from apps.audit import services as audit
from apps.core.context import get_current_org
from apps.core.exceptions import BusinessRuleError
from apps.core.services import next_number
from apps.rbac.services import has_perm

from .models import ClearanceItem, ExitInterview, Separation

OPEN = ["draft", "pending", "returned", "clearance"]
OWNER_ROLES = {"hr": "hr_officer", "it": "it_support", "admin": "admin_officer", "finance": "finance_officer",
               "payroll": "payroll_officer"}
CLEARANCE = [
    ("supervisor", "Handover of duties, files and work in progress", ""),
    ("admin", "Return of property, uniforms, keys and access card", "assets_admin"),
    ("it", "Return of IT equipment; email and system accounts closed", "assets_it"),
    ("finance", "Loans, advances and claims settled or set for recovery from final pay", "loans"),
    ("hr", "Exit interview completed", "exit_interview"),
    ("payroll", "Final salary, leave pay and deductions processed", "final_pay"),
    ("hr", "Personnel file closed and archived; certificate of service issued", ""),
]


def _notify(users, title, body, link):
    from apps.notifications.services import notify

    users = [u for u in users if u is not None]
    if users:
        notify("generic", users, {"title": title, "body": body, "link": link})


def _instance(obj):
    from apps.recruitment.services import _instance as inst

    return inst(obj)


def notice_days(employee, on_date=None):
    """Ghana Labour Act defaults (s.17): one month for 3+ years' service, two weeks below that, one week on
    probation. Override per organization with settings["notice_days"] = {"probation": 7, "short": 14, "long": 30}."""
    cfg = {"probation": 7, "short": 14, "long": 30}
    cfg.update((employee.organization.settings or {}).get("notice_days", {}))
    if employee.status == "probation":
        return cfg["probation"]
    start = employee.original_hire_date or employee.hire_date
    years = ((on_date or dt.date.today()) - start).days / 365.25
    return cfg["long"] if years >= 3 else cfg["short"]


def access_extended(employee, today=None):
    today = today or dt.date.today()
    return Separation.objects.filter(employee=employee, access_extension_until__gte=today).exclude(
        status__in=["withdrawn", "rejected"]).exists()


# ---------------------------------------------------------------- separation
@transaction.atomic
def initiate(user, employee, data: dict) -> Separation:
    from apps.rbac.services import can_access_employee
    from apps.workflow import engine

    own = getattr(user, "employee", None) == employee
    exit_type = data.get("exit_type") or "resignation"
    if own and exit_type != "resignation":
        raise PermissionDenied("Employees can submit a resignation; other exits are recorded by HR.")
    if not own and not can_access_employee(user, "offboarding.manage", employee):
        raise PermissionDenied("You cannot record an exit for this employee.")
    if employee.status == "exited":
        raise BusinessRuleError("This employee has already exited.")
    if Separation.objects.filter(employee=employee, status__in=OPEN).exists():
        raise BusinessRuleError("There is already an exit in progress for this employee.")
    notice = data.get("notice_date") or dt.date.today()
    lwd = data.get("last_working_day")
    if not lwd or lwd < notice:
        raise BusinessRuleError("The last working day must be on or after the notice date.")
    if exit_type in Separation.INVOLUNTARY and not data.get("details"):
        raise BusinessRuleError("Record the grounds for an involuntary exit.")
    req = notice_days(employee, notice)
    sep = Separation.objects.create(
        employee=employee, exit_type=exit_type, reason=data.get("reason") or "", details=data.get("details") or "",
        notice_date=notice, last_working_day=lwd, notice_required_days=req,
        notice_shortfall_days=max(0, req - (lwd - notice).days), rehire_eligible=data.get("rehire_eligible", True),
        handover_to=data.get("handover_to"), submitted_by=user,
        reference=next_number("separation", default_prefix="EX", default_pattern="{prefix}-{year}-{seq:04d}"))
    engine.start(sep, "separation", user, subject_employee=employee,
                 extra_context={"exit_type": exit_type, "involuntary": exit_type in Separation.INVOLUNTARY,
                                "shortfall": sep.notice_shortfall_days})
    return sep


@transaction.atomic
def approve(sep: Separation, user=None):
    """Called when the separation is approved: record the exit and open clearance."""
    from apps.employees import services as emp_services

    sep.status, sep.approved_at = "clearance", timezone.now()
    sep.save(update_fields=["status", "approved_at", "updated_at"])
    emp_services.separate(sep.employee, sep.last_working_day, sep.exit_type, notes=sep.details,
                          rehire_eligible=sep.rehire_eligible, user=user)
    for i, (owner, title, check) in enumerate(CLEARANCE):
        if check == "exit_interview" and sep.exit_type == "death":
            continue
        ClearanceItem.objects.create(separation=sep, order=i, owner=owner, title=title, auto_check=check)
    ExitInterview.objects.get_or_create(separation=sep)
    for owner in {o for o, _, _ in CLEARANCE}:
        _notify(owner_users(sep, owner), f"Exit clearance: {sep.employee.full_name}",
                f"{sep.employee.full_name} leaves on {sep.last_working_day:%d/%m/%Y}. Please complete your clearance.",
                f"/offboarding/{sep.id}")
    if sep.employee.user_id and sep.exit_type != "death":
        _notify([sep.employee.user], "Your exit has been confirmed",
                f"Your last working day is {sep.last_working_day:%d/%m/%Y}. Please complete the short exit "
                "interview and return any company property.", "/offboarding/my")
    audit.log("update", sep, {"action": "approved", "last_working_day": str(sep.last_working_day)})
    return sep


def separation_from_case(action):
    """A dismissal decided in an employee-relations case starts offboarding directly (already approved)."""
    emp = action.employee
    if Separation.objects.filter(employee=emp, status__in=OPEN).exists():
        return None
    sep = Separation.objects.create(
        employee=emp, exit_type="dismissal", reason="conduct", details=action.details,
        notice_date=action.effective_date, last_working_day=action.effective_date, notice_required_days=0,
        rehire_eligible=False, er_action=action, status="pending",
        reference=next_number("separation", default_prefix="EX", default_pattern="{prefix}-{year}-{seq:04d}"))
    return approve(sep)


def withdraw(sep: Separation, user, reason=""):
    own = sep.employee.user_id == user.pk
    if not (own or has_perm(user, "offboarding.manage")):
        raise PermissionDenied()
    if sep.status not in ("pending", "returned", "draft") and not (sep.status == "clearance" and
                                                                   has_perm(user, "offboarding.manage")
                                                                   and sep.last_working_day > dt.date.today()):
        raise BusinessRuleError("This exit can no longer be withdrawn.")
    inst = _instance(sep)
    if inst and inst.status in ("pending", "returned"):
        from apps.workflow import engine

        engine.cancel(inst, user, reason or "Withdrawn")
    if sep.status == "clearance":  # reverse the recorded exit before the last day
        emp = sep.employee
        emp.exit_date, emp.exit_reason = None, ""
        emp.save(update_fields=["exit_date", "exit_reason", "updated_at"])
        sep.clearance.all().delete()
    sep.status = "withdrawn"
    sep.save(update_fields=["status", "updated_at"])
    audit.log("update", sep, {"action": "withdrawn", "reason": reason})
    return sep


def extend_access(sep: Separation, user, until, reason):
    if not has_perm(user, "offboarding.manage"):
        raise PermissionDenied()
    if until <= sep.last_working_day or until > sep.last_working_day + dt.timedelta(days=30):
        raise BusinessRuleError("Extend access by 1 to 30 days after the last working day.")
    if not reason:
        raise BusinessRuleError("Give the reason (e.g. handover).")
    sep.access_extension_until = until
    sep.handover_notes = "\n".join(x for x in (sep.handover_notes, f"Access extended to {until:%d/%m/%Y}: {reason}") if x)
    sep.save(update_fields=["access_extension_until", "handover_notes", "updated_at"])
    if sep.employee.user_id and not sep.employee.user.is_active and until >= dt.date.today():
        u = sep.employee.user
        u.is_active = True
        u.save(update_fields=["is_active"])
    audit.log("update", sep, {"action": "access_extended", "until": str(until), "reason": reason})
    return sep


# ---------------------------------------------------------------- clearance
def owner_users(sep, owner):
    from apps.onboarding.services import _role_users

    if owner == "supervisor":
        sup = sep.employee.supervisor
        return [sup.user] if sup and sup.user_id else _role_users("hr_officer", sep.organization_id)
    users = _role_users(OWNER_ROLES[owner], sep.organization_id)
    return users or _role_users("hr_officer", sep.organization_id)


def can_clear(item, user):
    return has_perm(user, "offboarding.manage") or user in owner_users(item.separation, item.owner)


def check_status(item):
    """Automatic check result: {"ok": bool, "info": str}."""
    from apps.assets.services import outstanding

    emp = item.separation.employee
    c = item.auto_check
    if c in ("assets_admin", "assets_it"):
        owner = "admin" if c == "assets_admin" else "it"
        items = [a for a in outstanding(emp).select_related("category", "asset") if a.category.owner == owner]
        return {"ok": not items, "info": "; ".join(f"{a.item}{f' ({a.asset.tag})' if a.asset_id else ''}"
                                                   for a in items) or "Nothing outstanding."}
    if c == "loans":
        from apps.expenses.models import TravelRequest
        from apps.payroll.models import Loan

        loans = Loan.objects.filter(employee=emp, status__in=["approved", "active"]).aggregate(s=Sum("balance"))["s"]
        adv = (TravelRequest.objects.filter(employee=emp, advance_paid__gt=0, status__in=["approved", "completed"])
               .aggregate(s=Sum("advance_paid"))["s"])
        loans, adv = loans or Decimal("0"), adv or Decimal("0")
        info = []
        if loans:
            info.append(f"Loan balance GHS {loans:,.2f} (recovered in the final payroll run)")
        if adv:
            info.append(f"Unretired travel advances GHS {adv:,.2f}")
        return {"ok": not adv, "info": "; ".join(info) or "Nothing outstanding."}
    if c == "exit_interview":
        ei = ExitInterview.objects.filter(separation_id=item.separation_id).first()
        return {"ok": bool(ei and ei.completed_at), "info": "Completed." if ei and ei.completed_at else "Not yet done."}
    if c == "final_pay":
        from apps.payroll.models import Payslip

        slip = (Payslip.objects.filter(employee=emp, run__run_type="final")
                .exclude(run__status__in=["draft", "reversed"]).order_by("-id").first())
        return {"ok": bool(slip), "info": f"Final run payslip, net GHS {slip.net_pay:,.2f}." if slip
                else "No final payroll run yet (use a 'final' run for the exit month)."}
    return {"ok": True, "info": ""}


def clear(item, user, notes="", waive=False):
    sep = item.separation
    sep.refresh_from_db(fields=["status"])  # never act on a stale copy
    if sep.status != "clearance":
        raise BusinessRuleError("Clearance is not open for this exit.")
    if item.status != "pending":
        raise BusinessRuleError("Already cleared.")
    if not can_clear(item, user):
        raise PermissionDenied("This clearance item belongs to another team.")
    if waive:
        if not has_perm(user, "offboarding.manage") or not notes:
            raise BusinessRuleError("Only HR can waive an item, with a reason.")
    else:
        st = check_status(item)
        if not st["ok"]:
            raise BusinessRuleError(f"Not yet clear: {st['info']}")
    item.status = "waived" if waive else "cleared"
    item.notes, item.cleared_by, item.cleared_at = notes, user, timezone.now()
    item.save()
    if not sep.clearance.filter(status="pending").exists():
        complete(sep, user)
    return item


@transaction.atomic
def complete(sep: Separation, user=None):
    from apps.documents.models import LetterTemplate
    from apps.documents.services import generate_letter

    sep.status, sep.completed_at = "completed", timezone.now()
    tpl = LetterTemplate.objects.filter(code="service_certificate", is_active=True).first()
    if tpl is not None and sep.exit_type != "death":
        try:
            sep.certificate = generate_letter(tpl, sep.employee, {"separation": sep}, reference=sep.reference)
        except Exception:  # never block closing the exit on a letter template problem
            sep.certificate = None
    sep.save()
    audit.log("update", sep, {"action": "clearance_completed"})
    return sep


def submit_exit_interview(sep: Separation, user, data):
    own = sep.employee.user_id == user.pk
    if not (own or has_perm(user, "offboarding.manage")):
        raise PermissionDenied()
    ei, _ = ExitInterview.objects.get_or_create(separation=sep)
    if ei.completed_at:
        raise BusinessRuleError("The exit interview has already been completed.")
    ratings = {}
    for qn in ExitInterview.QUESTIONS:
        v = (data.get("ratings") or {}).get(qn)
        if v not in (None, ""):
            v = int(v)
            if not 1 <= v <= 5:
                raise BusinessRuleError("Ratings are 1 to 5.")
            ratings[qn] = v
    if not ratings:
        raise BusinessRuleError("Answer at least one question.")
    ei.ratings, ei.primary_reason = ratings, data.get("primary_reason") or sep.reason
    ei.what_went_well, ei.what_to_improve = data.get("what_went_well", ""), data.get("what_to_improve", "")
    ei.would_recommend, ei.would_return = data.get("would_recommend"), data.get("would_return")
    ei.conducted_by = None if own else user
    ei.completed_at = timezone.now()
    ei.save()
    if ei.primary_reason and not sep.reason:
        sep.reason = ei.primary_reason
        sep.save(update_fields=["reason", "updated_at"])
    return ei


# ---------------------------------------------------------------- analytics & housekeeping
def analytics(months=12, today=None):
    from apps.employees.models import Employee

    today = today or dt.date.today()
    since = today - dt.timedelta(days=int(months * 30.4))
    exits = Separation.objects.filter(last_working_day__gte=since, last_working_day__lte=today).exclude(
        status__in=["withdrawn", "rejected", "pending", "returned", "draft"]).select_related("employee")
    n = exits.count()
    active = Employee.objects.filter(status__in=["active", "probation", "on_leave"]).count()
    avg_headcount = active + n / 2 or 1
    types, reasons = dict(Separation.TYPES), dict(Separation.REASONS)
    bands = {"< 1 year": 0, "1-3 years": 0, "3-5 years": 0, "5+ years": 0}
    for s in exits:
        yrs = (s.last_working_day - (s.employee.original_hire_date or s.employee.hire_date)).days / 365.25
        bands["< 1 year" if yrs < 1 else "1-3 years" if yrs < 3 else "3-5 years" if yrs < 5 else "5+ years"] += 1
    voluntary = exits.filter(exit_type__in=["resignation", "retirement", "mutual"]).count()
    ei = ExitInterview.objects.filter(separation__in=exits, completed_at__isnull=False)
    averages = {}
    for e in ei:
        for k, v in e.ratings.items():
            averages.setdefault(k, []).append(v)
    regretted = exits.filter(exit_type="resignation", rehire_eligible=True).count()
    return {
        "exits": n, "turnover_percent": round(100 * n / avg_headcount, 1),
        "voluntary": voluntary, "involuntary": n - voluntary, "regretted_resignations": regretted,
        "early_attrition": bands["< 1 year"],
        "by_type": [{"label": types[k], "value": v} for k, v in
                    exits.values_list("exit_type").annotate(c=Count("id")).order_by("-c")],
        "by_reason": [{"label": reasons.get(k, k), "value": v} for k, v in
                      exits.exclude(reason="").values_list("reason").annotate(c=Count("id")).order_by("-c")],
        "by_tenure": [{"label": k, "value": v} for k, v in bands.items()],
        "by_department": [{"label": k or "—", "value": v} for k, v in
                          exits.values_list("employee__department__name").annotate(c=Count("id")).order_by("-c")[:10]],
        "exit_interviews": ei.count(),
        "exit_ratings": [{"label": k, "value": round(sum(v) / len(v), 2)} for k, v in averages.items()],
        "would_recommend_percent": round(100 * ei.filter(would_recommend=True).count() / ei.exclude(
            would_recommend=None).count(), 1) if ei.exclude(would_recommend=None).exists() else None,
        "in_clearance": Separation.objects.filter(status="clearance").count(),
        "avg_clearance_days": _avg_clearance_days(),
    }


def _avg_clearance_days():
    rows = Separation.objects.filter(status="completed", completed_at__isnull=False, approved_at__isnull=False)         .values_list("approved_at", "completed_at")
    days = [(c - a).days for a, c in rows]
    return round(sum(days) / len(days), 1) if days else None


def upcoming_exits(days=90, today=None):
    """Retirements and contract ends coming up with no exit recorded yet."""
    from apps.employees.models import Employee

    today = today or dt.date.today()
    horizon = today + dt.timedelta(days=days)
    has_sep = Separation.objects.filter(status__in=OPEN + ["completed"]).values("employee")
    qs = (Employee.objects.filter(status__in=["active", "probation", "on_leave"])
          .filter(Q(retirement_date__range=(today, horizon)) | Q(contract_end_date__range=(today, horizon)))
          .exclude(pk__in=has_sep).select_related("department"))
    return [{"employee": e.id, "name": e.full_name, "department": e.department.name if e.department_id else None,
             "kind": "retirement" if e.retirement_date and e.retirement_date <= horizon else "contract_end",
             "date": e.retirement_date if e.retirement_date and e.retirement_date <= horizon else e.contract_end_date}
            for e in qs]


def housekeeping(today=None):
    """Daily: revoke access when an approved extension ends; remind HR about upcoming retirements."""
    from apps.employees.services import revoke_access
    from apps.onboarding.services import _role_users

    today = today or dt.date.today()
    n = 0
    for sep in Separation.objects.filter(access_extension_until__lt=today, employee__user__is_active=True,
                                         last_working_day__lt=today).select_related("employee__user"):
        revoke_access(sep.employee, force=True)
        n += 1
    soon = [u for u in upcoming_exits(90, today) if u["kind"] == "retirement" and (u["date"] - today).days in (90, 60, 30)]
    org = get_current_org()
    if soon and org is not None:
        for u in soon:
            _notify(_role_users("hr_officer", org.id),
                    f"Upcoming retirement: {u['name']}", f"Compulsory retirement on {u['date']:%d/%m/%Y}. Start the "
                    "exit and pension (SSNIT) process.", "/offboarding")
    return n
