"""Occupational health & safety (features.txt §17 and the hospital exposure workflow).

The incident register and risk/inspection records are for safety staff; clinical OH content lives in OHRecord
and is visible only with `ohs.medical`. HR, managers and rostering only ever see the fitness outcome."""

import datetime as dt
from collections import Counter

from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from apps.audit import services as audit
from apps.core.exceptions import BusinessRuleError
from apps.core.services import next_number
from apps.rbac.models import RoleAssignment
from apps.rbac.services import has_perm

from .models import CorrectiveAction, Incident, OHRecord, RiskAssessment

HOURS_PER_EMPLOYEE_YEAR = 2080
NEEDS_OH = ("injury", "exposure", "ill_health", "violence")


def _notify(users, title, body, link, sms=False):
    from apps.notifications.services import notify

    users = [u for u in users if u is not None]
    if users:
        notify("generic", users, {"title": title, "body": body, "link": link},
               channels=("in_app", "email") if not sms else ("in_app", "email", "sms"))


def _perm_users(code):
    seen = {}
    for ra in RoleAssignment.objects.filter(user__is_active=True).select_related("user"):
        if ra.user_id not in seen and has_perm(ra.user, code):
            seen[ra.user_id] = ra.user
    return list(seen.values())


@transaction.atomic
def report(user, data, persons=()):
    """Anyone can report an incident or near miss. Details must not contain medical information."""
    if data.get("kind") not in dict(Incident.KINDS):
        raise BusinessRuleError("Choose what kind of event it was.")
    if not data.get("description") or not data.get("location") or not data.get("occurred_at"):
        raise BusinessRuleError("Say what happened, where and when.")
    if data["occurred_at"] > timezone.now():
        raise BusinessRuleError("The date and time cannot be in the future.")
    inc = Incident.objects.create(
        kind=data["kind"], severity=data.get("severity") or "none", occurred_at=data["occurred_at"],
        location=data["location"], department=data.get("department"), description=data["description"],
        immediate_action=data.get("immediate_action", ""), others_involved=data.get("others_involved", ""),
        reported_by=user, reference=next_number("incident", default_prefix="INC",
                                                default_pattern="{prefix}-{year}-{seq:04d}"))
    inc.persons_involved.set(persons)
    urgent = inc.kind == "exposure" or inc.severity in ("serious", "fatal")
    _notify(_perm_users("ohs.manage"), f"{'URGENT: ' if urgent else ''}{inc.get_kind_display()} reported ({inc.reference})",
            f"{inc.location}, {timezone.localtime(inc.occurred_at):%d/%m/%Y %H:%M}. Please review.",
            f"/safety/incidents/{inc.id}", sms=urgent)
    if inc.kind in NEEDS_OH and persons:
        # occupational health follow-up; no clinical or incident detail in the message
        _notify(_perm_users("ohs.medical"), f"Occupational health follow-up needed ({inc.reference})",
                "A staff member involved in a workplace incident may need assessment"
                + (" urgently (exposure: post-exposure prophylaxis window)" if inc.kind == "exposure" else "") + ".",
                "/safety/occupational-health", sms=inc.kind == "exposure")
    if inc.severity in ("serious", "fatal"):
        inc.reportable = True
        inc.save(update_fields=["reportable"])
    return inc


def can_see_incident(inc, user):
    return has_perm(user, "ohs.view") or inc.reported_by_id == user.pk or inc.investigator_id == user.pk


def investigate(inc, user, investigator=None, root_cause=None, factors=None, lost_time_days=None, reportable=None,
                reported_to_authority_on=None):
    if not (has_perm(user, "ohs.manage") or inc.investigator_id == user.pk):
        raise PermissionDenied()
    if inc.status == "closed":
        raise BusinessRuleError("The incident is closed.")
    if investigator is not None:
        inc.investigator = investigator
        _notify([investigator], f"Incident investigation {inc.reference}", "You have been asked to investigate.",
                f"/safety/incidents/{inc.id}")
    for f, v in (("root_cause", root_cause), ("contributing_factors", factors), ("lost_time_days", lost_time_days),
                 ("reportable", reportable), ("reported_to_authority_on", reported_to_authority_on)):
        if v is not None:
            setattr(inc, f, v)
    if inc.status == "reported":
        inc.status = "investigating"
    inc.save()
    return inc


def add_action(user, description, owner, due_date, **target):
    if not has_perm(user, "ohs.manage") and not (target.get("incident") and target["incident"].investigator_id == user.pk):
        raise PermissionDenied()
    if not description or not due_date:
        raise BusinessRuleError("Describe the action and set a due date.")
    a = CorrectiveAction.objects.create(description=description, owner=owner, due_date=due_date, **target)
    inc = target.get("incident")
    if inc and inc.status in ("reported", "investigating"):
        inc.status = "actions"
        inc.save(update_fields=["status", "updated_at"])
    _notify([owner], "Safety action assigned to you", f"{description[:150]} (due {due_date:%d/%m/%Y})", "/safety")
    return a


def complete_action(a, user, notes=""):
    if not (a.owner_id == user.pk or has_perm(user, "ohs.manage")):
        raise PermissionDenied()
    if a.status != "open":
        raise BusinessRuleError("Already completed.")
    a.status, a.completed_at, a.notes = "done", timezone.now(), notes or a.notes
    a.save()
    return a


def close_incident(inc, user):
    if not has_perm(user, "ohs.manage"):
        raise PermissionDenied()
    if inc.kind != "near_miss" and not inc.root_cause:
        raise BusinessRuleError("Record the root cause before closing.")
    if inc.actions.filter(status="open").exists():
        raise BusinessRuleError("Complete the corrective actions first.")
    if inc.reportable and not inc.reported_to_authority_on:
        raise BusinessRuleError("Record when this reportable incident was notified to the authority.")
    inc.status, inc.closed_at = "closed", timezone.now()
    inc.save(update_fields=["status", "closed_at", "updated_at"])
    return inc


# ---------------------------------------------------------------- occupational health (restricted)
def add_oh_record(user, employee, data):
    if not has_perm(user, "ohs.medical"):
        raise PermissionDenied("Occupational health records are restricted to OH professionals.")
    if data.get("kind") not in dict(OHRecord.KINDS):
        raise BusinessRuleError("Choose the record type.")
    rec = OHRecord.objects.create(employee=employee, clinician=user, **data)
    audit.log("create", rec, {"kind": rec.kind, "fitness": rec.fitness})
    if rec.fitness in ("unfit", "fit_restricted"):
        from apps.onboarding.services import _role_users

        sup = employee.supervisor
        _notify([sup.user if sup and sup.user_id else None, *_role_users("hr_officer", employee.organization_id)],
                f"Fitness for duty: {employee.full_name}",
                f"{rec.get_fitness_display()}{f' - {rec.restrictions}' if rec.restrictions else ''}"
                f"{f' until {rec.valid_until:%d/%m/%Y}' if rec.valid_until else ''}.", "/safety/fitness")
    return rec


def fitness_status(employee, on_date=None):
    """Non-clinical fitness outcome for HR, managers and rostering."""
    on_date = on_date or dt.date.today()
    rec = (OHRecord.objects.filter(employee=employee, date__lte=on_date).exclude(fitness="")
           .filter(Q(valid_until__isnull=True) | Q(valid_until__gte=on_date)).order_by("-date", "-id").first())
    if rec is None:
        return None
    return {"status": rec.fitness, "label": rec.get_fitness_display(), "restrictions": rec.restrictions,
            "since": rec.date, "until": rec.valid_until, "review_date": rec.review_date}


def fitness_board(on_date=None):
    from apps.employees.models import Employee

    out = []
    ids = OHRecord.objects.exclude(fitness="").values_list("employee_id", flat=True).distinct()
    for emp in Employee.objects.filter(pk__in=ids, status__in=["active", "probation", "on_leave"]) \
            .select_related("department"):
        st = fitness_status(emp, on_date)
        if st and st["status"] != "fit":
            out.append({"employee": emp.id, "name": emp.full_name,
                        "department": emp.department.name if emp.department_id else None, **st})
    return out


# ---------------------------------------------------------------- analytics & housekeeping
def stats(year=None):
    from apps.employees.models import Employee

    year = year or dt.date.today().year
    qs = Incident.objects.filter(occurred_at__year=year)
    headcount = Employee.objects.filter(status__in=["active", "probation", "on_leave"]).count() or 1
    months_elapsed = dt.date.today().month if year == dt.date.today().year else 12
    hours = headcount * HOURS_PER_EMPLOYEE_YEAR * months_elapsed / 12
    lti = qs.filter(lost_time_days__gt=0).count()
    kinds, sev = dict(Incident.KINDS), dict(Incident.SEVERITY)
    last_lti = Incident.objects.filter(lost_time_days__gt=0).order_by("-occurred_at").first()
    months = Counter(qs.values_list("occurred_at__month", flat=True))
    today = dt.date.today()
    return {
        "year": year, "incidents": qs.exclude(kind="near_miss").count(), "near_misses": qs.filter(kind="near_miss").count(),
        "lost_time_injuries": lti, "lost_days": qs.aggregate(s=Sum("lost_time_days"))["s"] or 0,
        "ltifr": round(lti * 1_000_000 / hours, 2) if hours else None,
        "days_since_lti": (today - timezone.localtime(last_lti.occurred_at).date()).days if last_lti else None,
        "exposures": qs.filter(kind="exposure").count(),
        "open_actions": CorrectiveAction.objects.filter(status="open").count(),
        "overdue_actions": CorrectiveAction.objects.filter(status="open", due_date__lt=today).count(),
        "risks_high": sum(1 for r in RiskAssessment.objects.filter(status__in=["active", "review_due"])
                          if r.residual_score >= 12),
        "by_month": [{"label": dt.date(year, m, 1).strftime("%b"), "value": months.get(m, 0)} for m in range(1, 13)],
        "by_kind": [{"label": kinds[k], "value": v} for k, v in Counter(qs.values_list("kind", flat=True)).most_common()],
        "by_severity": [{"label": sev[k], "value": v} for k, v in
                        Counter(qs.values_list("severity", flat=True)).most_common()],
        "by_department": [{"label": k or "—", "value": v} for k, v in
                          Counter(qs.values_list("department__name", flat=True)).most_common(10)],
    }


def housekeeping(today=None):
    today = today or dt.date.today()
    n = 0
    for a in CorrectiveAction.objects.filter(status="open", due_date__lt=today, reminded_at__isnull=True):
        _notify([a.owner, *_perm_users("ohs.manage")], "Overdue safety action",
                f"{a.description[:150]} was due {a.due_date:%d/%m/%Y}.", "/safety")
        a.reminded_at = timezone.now()
        a.save(update_fields=["reminded_at"])
        n += 1
    RiskAssessment.objects.filter(status="active", review_date__lt=today).update(status="review_due")
    return n
