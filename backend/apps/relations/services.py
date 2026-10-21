"""Employee relations: confidential grievance, harassment, misconduct and disciplinary cases (features.txt §15).

Access is by case assignment, not by line management. Natural justice is enforced: formal sanctions need a
hearing first, serious sanctions need HR Director approval, and every sanction can be appealed to someone
other than the case officer."""

import datetime as dt
from collections import Counter

from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from apps.audit import services as audit
from apps.core.exceptions import BusinessRuleError
from apps.core.services import next_number
from apps.rbac.models import RoleAssignment
from apps.rbac.services import has_perm

from .models import Appeal, Case, CaseAction, CaseMeeting, CaseNote

DEADLINE_DAYS = {"critical": 7, "high": 14, "medium": 21, "low": 30}
APPEAL_DAYS = 14
WARNING_MONTHS = {"verbal_warning": 6, "written_warning": 12, "final_warning": 12}
FORMAL = ["written_warning", "final_warning", "suspension", "demotion", "dismissal"]  # need a hearing first
EMPLOYEE_TYPES = ["grievance", "harassment", "whistleblowing", "conflict"]
OPEN = ["reported", "investigating", "hearing", "pending_decision", "appeal"]


def _notify(users, title, body, link):
    from apps.notifications.services import notify

    users = [u for u in users if u is not None]
    if users:
        notify("generic", users, {"title": title, "body": body, "link": link}, channels=("in_app", "email"))


def _perm_users(code):
    """Active users holding a permission through any role."""
    users = {}
    for ra in RoleAssignment.objects.filter(user__is_active=True).select_related("user", "role"):
        if has_perm(ra.user, code):
            users[ra.user_id] = ra.user
    return list(users.values())


def _party_user_ids(case):
    ids = set(case.respondents.exclude(user=None).values_list("user_id", flat=True))
    if case.complainant_id and case.complainant.user_id:
        ids.add(case.complainant.user_id)
    return ids


def is_handler(case, user):
    return case.case_officer_id == user.pk or case.investigators.filter(pk=user.pk).exists()


def can_access(case, user):
    """Full case access: case officer, investigators, or relations.view_all - never a party to the case."""
    if user.pk in _party_user_ids(case):
        return False
    return is_handler(case, user) or has_perm(user, "relations.view_all")


def _pick_officer(case):
    """Least-loaded case handler who is not a party."""
    parties = _party_user_ids(case)
    load = dict(Case.objects.filter(status__in=OPEN).order_by().values_list("case_officer").annotate(n=Count("id")))
    candidates = [u for u in _perm_users("relations.manage") if u.pk not in parties]
    candidates.sort(key=lambda u: (has_perm(u, "relations.view_all"), load.get(u.pk, 0)))
    return candidates[0] if candidates else None


@transaction.atomic
def open_case(user, data: dict, respondents=()):
    """Employees raise grievances/reports; HR (relations.manage) can register any case type."""
    case_type = data.get("case_type")
    hr = has_perm(user, "relations.manage")
    if case_type not in dict(Case.TYPES):
        raise BusinessRuleError("Choose the type of matter.")
    if not hr and case_type not in EMPLOYEE_TYPES:
        raise PermissionDenied("Disciplinary and misconduct cases are registered by HR.")
    if not data.get("description"):
        raise BusinessRuleError("Describe what happened.")
    reporter_emp = getattr(user, "employee", None)
    if any(r == reporter_emp for r in respondents):
        raise BusinessRuleError("You cannot be a respondent in your own report.")
    case = Case(case_type=case_type, title=data.get("title") or dict(Case.TYPES)[case_type],
                description=data["description"], severity=data.get("severity") or "medium",
                incident_date=data.get("incident_date"), policy_reference=data.get("policy_reference", ""),
                is_anonymous=bool(data.get("is_anonymous")) and case_type in ("harassment", "whistleblowing"),
                reported_by=user)
    # the reporter is the complainant when raising their own concern; HR registering a case names one explicitly
    case.complainant = reporter_emp if (data.get("own") or not hr) else data.get("complainant")
    case.reference = next_number("er_case", default_prefix="ER", default_pattern="{prefix}-{year}-{seq:04d}")
    case.due_date = dt.date.today() + dt.timedelta(days=DEADLINE_DAYS.get(case.severity, 21))
    case.save()
    case.respondents.set(respondents)
    case.case_officer = _pick_officer(case)
    case.save(update_fields=["case_officer"])
    audit.log("create", case, {"type": case_type, "severity": case.severity})
    _notify([case.case_officer], f"New confidential case {case.reference}",
            "A new employee-relations case has been assigned to you.", f"/relations/cases/{case.id}")
    return case


def assign(case, user, officer=None, investigators=None, plan=None):
    if not (has_perm(user, "relations.view_all") or case.case_officer_id == user.pk):
        raise PermissionDenied()
    parties = _party_user_ids(case)
    if officer is not None:
        if officer.pk in parties:
            raise BusinessRuleError("A party to the case cannot handle it.")
        case.case_officer = officer
    if investigators is not None:
        if any(i.pk in parties for i in investigators):
            raise BusinessRuleError("A party to the case cannot investigate it.")
        case.investigators.set(investigators)
        _notify(investigators, f"Investigation assignment {case.reference}",
                "You have been asked to investigate a confidential case.", f"/relations/cases/{case.id}")
    if plan is not None:
        case.investigation_plan = plan
    if case.status == "reported" and (investigators or plan):
        case.status = "investigating"
    case.save()
    audit.log("update", case, {"action": "assigned", "officer": case.case_officer_id})
    return case


def _require_handler(case, user):
    if not (is_handler(case, user) or has_perm(user, "relations.view_all")) or user.pk in _party_user_ids(case):
        raise PermissionDenied("Only the assigned case handlers can do this.")


def add_note(case, user, kind, text="", file=None):
    from apps.documents.services import validate_upload

    _require_handler(case, user)
    if case.status in ("closed", "withdrawn"):
        raise BusinessRuleError("The case is closed.")
    if not text and file is None:
        raise BusinessRuleError("Add text or attach a file.")
    note = CaseNote(case=case, kind=kind, text=text, author=user)
    if file is not None:
        validate_upload(file)
        note.file_name = file.name[:255]
        note.file.save(file.name, file, save=False)
    note.save()
    return note


def schedule_meeting(case, user, data, invitees=()):
    _require_handler(case, user)
    m = CaseMeeting.objects.create(case=case, **data)
    m.invitees.set(invitees)
    if case.status in ("reported", "investigating") and m.kind in ("hearing", "mediation"):
        case.status = "hearing"
        case.save(update_fields=["status", "updated_at"])
    when = timezone.localtime(m.scheduled_at)
    _notify([e.user for e in invitees if e.user_id], "Meeting with HR",
            f"You are invited to a confidential meeting on {when:%d/%m/%Y %H:%M}{' at ' + m.venue if m.venue else ''}. "
            "You may bring a colleague or representative.", "/relations/my")
    return m


def record_minutes(meeting, user, minutes):
    _require_handler(meeting.case, user)
    if not minutes:
        raise BusinessRuleError("Record the minutes.")
    meeting.minutes, meeting.held = minutes, True
    meeting.save(update_fields=["minutes", "held", "updated_at"])
    return meeting


@transaction.atomic
def decide(case, user, outcome, summary, actions=()):
    """actions: [{"employee": Employee, "action_type": str, "details": str, "effective_date": date,
    "suspension_days": int}]"""
    from apps.workflow import engine

    _require_handler(case, user)
    if case.status not in ("reported", "investigating", "hearing"):
        raise BusinessRuleError("A decision has already been recorded.")
    if outcome not in dict(Case.OUTCOMES) or not summary:
        raise BusinessRuleError("Choose an outcome and summarise the reasons.")
    respondents = set(case.respondents.values_list("pk", flat=True))
    for a in actions:
        if a["employee"].pk not in respondents:
            raise BusinessRuleError("Sanctions can only be issued to a respondent in the case.")
        if a["action_type"] in FORMAL and not case.meetings.filter(kind="hearing", held=True).exists():
            raise BusinessRuleError("Hold and minute a hearing (the employee's right to be heard) before a formal "
                                    "sanction.")
        if a["action_type"] == "suspension" and not a.get("suspension_days"):
            raise BusinessRuleError("Give the suspension length in days.")
    case.outcome, case.outcome_summary, case.decided_at = outcome, summary, timezone.now()
    for a in actions:
        months = WARNING_MONTHS.get(a["action_type"])
        eff = a.get("effective_date") or dt.date.today()
        CaseAction.objects.create(case=case, employee=a["employee"], action_type=a["action_type"],
                                  details=a.get("details") or summary, effective_date=eff,
                                  suspension_days=a.get("suspension_days") or 0,
                                  expires_on=_add_months(eff, months) if months else None)
    if any(a["action_type"] in Case.SERIOUS for a in actions):
        case.status = "pending_decision"
        case.save()
        engine.start(case, "disciplinary_decision", user, subject_employee=actions[0]["employee"],
                     extra_context={"outcome": outcome})
        return case
    case.save()
    issue(case)
    return case


def _add_months(d, months):
    import calendar

    m = d.month - 1 + months
    y, m = d.year + m // 12, m % 12 + 1
    return dt.date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def issue(case):
    """Issue the decided actions: letters to the restricted personnel file, notifications, appeal window."""
    from apps.documents.models import DocumentCategory, LetterTemplate
    from apps.documents.services import generate_letter

    tpl = LetterTemplate.objects.filter(code="disciplinary_outcome", is_active=True).first()
    cat = DocumentCategory.objects.filter(code="disciplinary").first()
    for a in case.actions.filter(issued_at__isnull=True).select_related("employee__user"):
        if tpl is not None:
            doc = generate_letter(tpl, a.employee, {"action": a, "case": case}, reference=case.reference)
            if cat:
                doc.category, doc.confidentiality, doc.visible_to_employee = cat, "restricted", True
                doc.save(update_fields=["category", "confidentiality", "visible_to_employee"])
            a.letter = doc
        a.issued_at = timezone.now()
        a.appeal_deadline = dt.date.today() + dt.timedelta(days=APPEAL_DAYS)
        a.save()
        _notify([a.employee.user], "HR outcome letter",
                f"An outcome has been issued to you. Read it, respond if you wish and note the appeal deadline "
                f"({a.appeal_deadline:%d/%m/%Y}).", "/relations/my")
        if a.action_type == "dismissal":
            from apps.offboarding.services import separation_from_case

            separation_from_case(a)
    case.status = "decided"
    case.save(update_fields=["status", "updated_at"])
    if case.complainant_id and case.complainant.user_id:
        _notify([case.complainant.user], f"Your case {case.reference}",
                "A decision has been reached on the matter you raised. HR will contact you.", "/relations/my")
    audit.log("update", case, {"action": "decision_issued", "outcome": case.outcome})


def respond(action, user, response):
    if action.employee.user_id != user.pk:
        raise PermissionDenied()
    action.acknowledged_at = timezone.now()
    action.employee_response = response or action.employee_response
    action.save(update_fields=["acknowledged_at", "employee_response", "updated_at"])
    return action


def lodge_appeal(action, user, grounds):
    if action.employee.user_id != user.pk:
        raise PermissionDenied()
    if not action.issued_at:
        raise BusinessRuleError("This outcome has not been issued.")
    if action.appeal_deadline and action.appeal_deadline < dt.date.today():
        raise BusinessRuleError(f"The appeal deadline ({action.appeal_deadline:%d/%m/%Y}) has passed.")
    if action.appeals.exclude(status="withdrawn").exists():
        raise BusinessRuleError("An appeal has already been lodged.")
    if not grounds:
        raise BusinessRuleError("State the grounds of your appeal.")
    ap = Appeal.objects.create(action=action, grounds=grounds)
    case = action.case
    case.status = "appeal"
    case.save(update_fields=["status", "updated_at"])
    _notify(_perm_users("relations.view_all"), f"Appeal lodged on {case.reference}",
            "An employee has appealed a disciplinary outcome.", f"/relations/cases/{case.id}")
    return ap


def decide_appeal(appeal, user, status, decision):
    case = appeal.action.case
    if not has_perm(user, "relations.view_all"):
        raise PermissionDenied("Appeals are decided by a senior reviewer.")
    if case.case_officer_id == user.pk or user.pk in _party_user_ids(case):
        raise PermissionDenied("The appeal must be decided by someone independent of the original decision.")
    if status not in ("upheld", "varied", "dismissed") or not decision:
        raise BusinessRuleError("Choose the appeal outcome and give reasons.")
    appeal.status, appeal.decision, appeal.decided_by, appeal.decided_at = status, decision, user, timezone.now()
    appeal.save()
    a = appeal.action
    if status == "upheld":
        a.expires_on = dt.date.today() - dt.timedelta(days=1)  # no longer active from today
        a.details += f"\n\nRescinded on appeal {dt.date.today():%d/%m/%Y}: {decision}"
        a.save(update_fields=["expires_on", "details", "updated_at"])
    elif status == "varied":
        a.details += f"\n\nVaried on appeal {dt.date.today():%d/%m/%Y}: {decision}"
        a.save(update_fields=["details", "updated_at"])
    case.status = "decided"
    case.save(update_fields=["status", "updated_at"])
    _notify([a.employee.user], "Your appeal", f"Your appeal has been decided: {appeal.get_status_display()}.",
            "/relations/my")
    audit.log("update", case, {"action": "appeal_decided", "result": status})
    return appeal


def close(case, user, note=""):
    _require_handler(case, user)
    if case.status not in ("decided", "reported", "investigating", "hearing"):
        raise BusinessRuleError("Resolve the pending decision or appeal first.")
    if not case.outcome:
        raise BusinessRuleError("Record the outcome before closing.")
    case.status, case.closed_at = "closed", timezone.now()
    case.save(update_fields=["status", "closed_at", "updated_at"])
    if note:
        CaseNote.objects.create(case=case, kind="note", text=f"Closed: {note}", author=user)
    return case


def withdraw(case, user, reason):
    reporter = case.reported_by_id == user.pk
    if not (reporter or has_perm(user, "relations.view_all")):
        raise PermissionDenied()
    if case.status not in ("reported", "investigating", "hearing"):
        raise BusinessRuleError("The case can no longer be withdrawn.")
    case.status, case.closed_at = "withdrawn", timezone.now()
    case.outcome_summary = f"Withdrawn: {reason}"
    case.save()
    return case


def active_warnings(employee, today=None):
    today = today or dt.date.today()
    return CaseAction.objects.filter(employee=employee, issued_at__isnull=False,
                                     action_type__in=list(WARNING_MONTHS)).filter(
        Q(expires_on__isnull=True) | Q(expires_on__gte=today))


def escalate_overdue(today=None):
    today = today or dt.date.today()
    n = 0
    seniors = _perm_users("relations.view_all")
    for case in Case.objects.filter(status__in=OPEN, due_date__lt=today, escalated_at__isnull=True):
        _notify([case.case_officer, *[u for u in seniors if u != case.case_officer]],
                f"Overdue case {case.reference}", f"The resolution deadline ({case.due_date:%d/%m/%Y}) has passed.",
                f"/relations/cases/{case.id}")
        case.escalated_at = timezone.now()
        case.save(update_fields=["escalated_at"])
        n += 1
    return n


def report(year=None):
    """Aggregates only - no names (trend reporting must not expose individuals)."""
    year = year or dt.date.today().year
    qs = Case.objects.filter(created_at__year=year)
    closed = list(qs.filter(closed_at__isnull=False).values_list("created_at", "closed_at"))
    days = [(c - o).days for o, c in closed]
    months = Counter(qs.values_list("created_at__month", flat=True))
    types, outcomes = dict(Case.TYPES), dict(Case.OUTCOMES)
    return {
        "year": year, "cases": qs.count(), "open": qs.filter(status__in=OPEN).count(),
        "overdue": qs.filter(status__in=OPEN, due_date__lt=dt.date.today()).count(),
        "avg_days_to_close": round(sum(days) / len(days), 1) if days else None,
        "appeals": Appeal.objects.filter(action__case__in=qs).count(),
        "by_type": [{"label": types[k], "value": v} for k, v in
                    qs.values_list("case_type").annotate(n=Count("id")).order_by("-n")],
        "by_outcome": [{"label": outcomes.get(k, k), "value": v} for k, v in
                       qs.exclude(outcome="").values_list("outcome").annotate(n=Count("id")).order_by("-n")],
        "by_month": [{"label": dt.date(year, m, 1).strftime("%b"), "value": months.get(m, 0)} for m in range(1, 13)],
        "by_department": [{"label": k or "—", "value": v} for k, v in
                          qs.values_list("respondents__department__name").annotate(n=Count("id", distinct=True))
                          .order_by("-n") if k or v][:10],
    }
