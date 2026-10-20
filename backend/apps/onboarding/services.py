"""Onboarding checklists, task routing to HR/manager/IT/finance/admin/new hire, and probation reviews.

Example (features.txt section 4): when HR registers a new employee the checklist is created
automatically; IT receives the account/equipment tasks, the department the induction task and HR
the probation review reminders."""

import datetime as dt
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from apps.audit import services as audit
from apps.core.exceptions import BusinessRuleError
from apps.rbac.models import RoleAssignment
from apps.rbac.services import has_perm

from .models import ChecklistTemplate, Onboarding, OnboardingTask, ProbationReview

OWNER_ROLES = {"hr": "hr_officer", "it": "it_support", "finance": "payroll_officer", "admin": "admin_officer"}
AUTO_START_WINDOW_DAYS = 30  # employees registered with a hire date older than this are not auto-onboarded
MAX_EXTENSION_MONTHS = 6


def choose_template(employee):
    qs = ChecklistTemplate.all_objects.filter(organization_id=employee.organization_id, is_active=True)
    qs = qs.filter(Q(department__isnull=True) | Q(department_id=employee.department_id))
    qs = qs.filter(Q(employment_type="") | Q(employment_type=employee.employment_type))
    best = sorted(qs, key=lambda t: (t.department_id is not None, t.employment_type != ""), reverse=True)
    return best[0] if best else None


@transaction.atomic
def start(employee, user=None, template=None, start_date=None, buddy=None, notify=True) -> Onboarding:
    if Onboarding.all_objects.filter(employee=employee, status="in_progress").exists():
        raise BusinessRuleError(f"{employee.full_name} already has an onboarding in progress.")
    template = template or choose_template(employee)
    if template is None:
        raise BusinessRuleError("No active onboarding checklist template. Create one under Onboarding setup.")
    start_date = start_date or employee.hire_date
    ob = Onboarding.all_objects.create(organization_id=employee.organization_id, employee=employee,
                                       template=template, start_date=start_date, buddy=buddy)
    for t in template.tasks.all():
        OnboardingTask.all_objects.create(
            organization_id=employee.organization_id, onboarding=ob, order=t.order, title=t.title,
            description=t.description, category=t.category, owner_type=t.owner_type, role=t.role,
            due_date=start_date + dt.timedelta(days=t.due_offset_days), is_mandatory=t.is_mandatory,
            document_category=t.document_category, policy_document=t.policy_document, form=t.form)
    schedule_probation_reviews(employee, ob)
    if notify:
        notify_new_tasks(ob)
    return ob


def link_offer(employee, offer):
    Onboarding.all_objects.filter(employee=employee, status="in_progress").update(offer=offer)


def _role_users(code, organization_id):
    today = dt.date.today()
    return [ra.user for ra in RoleAssignment.all_objects.filter(
        organization_id=organization_id, role__code=code, user__is_active=True)
        .filter(Q(valid_from__isnull=True) | Q(valid_from__lte=today))
        .filter(Q(valid_to__isnull=True) | Q(valid_to__gte=today)).select_related("user")]


def owner_users(task: OnboardingTask) -> list:
    if task.assignee_id:
        return [task.assignee]
    emp = task.onboarding.employee
    if task.owner_type == "employee":
        return [emp.user] if emp.user_id else []
    if task.owner_type == "manager":
        sup = emp.supervisor
        return [sup.user] if sup and sup.user_id else _role_users("hr_officer", task.organization_id)
    code = task.role.code if task.owner_type == "role" and task.role_id else OWNER_ROLES.get(task.owner_type)
    users = _role_users(code, task.organization_id) if code else []
    return users or _role_users("hr_officer", task.organization_id)


def _user_role_codes(user):
    today = dt.date.today()
    return list(RoleAssignment.objects.filter(user=user)
                .filter(Q(valid_from__isnull=True) | Q(valid_from__lte=today))
                .filter(Q(valid_to__isnull=True) | Q(valid_to__gte=today)).values_list("role__code", flat=True))


def tasks_for_user(user):
    """Tasks the user is responsible for, including their own new-hire tasks."""
    codes = _user_role_codes(user)
    owner_types = [ot for ot, code in OWNER_ROLES.items() if code in codes]
    unassigned = Q(assignee__isnull=True)
    cond = (Q(assignee=user)
            | (unassigned & Q(owner_type="employee", onboarding__employee__user=user))
            | (unassigned & Q(owner_type="manager", onboarding__employee__supervisor__user=user))
            | (unassigned & Q(owner_type__in=owner_types))
            | (unassigned & Q(owner_type="role", role__code__in=codes)))
    return OnboardingTask.objects.filter(cond, onboarding__status="in_progress").select_related(
        "onboarding__employee__department", "policy_document", "document_category")


def can_work(task: OnboardingTask, user) -> bool:
    return has_perm(user, "onboarding.manage") or tasks_for_user(user).filter(pk=task.pk).exists()


def notify_new_tasks(ob: Onboarding):
    from apps.notifications.services import notify

    per_user: dict = {}
    for t in ob.tasks.all():
        for u in owner_users(t):
            per_user.setdefault(u, []).append(t)
    for u, tasks in per_user.items():
        notify("generic", [u], {
            "title": f"Onboarding: {len(tasks)} task(s) for {ob.employee.full_name}",
            "body": f"{ob.employee.full_name} starts on {ob.start_date:%d/%m/%Y}. First task due "
                    f"{min(t.due_date for t in tasks):%d/%m/%Y}: {tasks[0].title}.",
            "link": "/onboarding/my-tasks"}, related=ob)


def _validate_form(task: OnboardingTask, response: dict):
    clean = {}
    for f in task.form or []:
        key = f.get("key")
        val = (response or {}).get(key)
        if f.get("type") == "rating":
            try:
                val = int(val)
            except (TypeError, ValueError):
                raise BusinessRuleError(f"Rate '{f.get('label', key)}' from 1 to 5.") from None
            if not 1 <= val <= 5:
                raise BusinessRuleError(f"Rate '{f.get('label', key)}' from 1 to 5.")
        elif f.get("required") and not val:
            raise BusinessRuleError(f"'{f.get('label', key)}' is required.")
        clean[key] = val
    return clean


@transaction.atomic
def complete_task(task: OnboardingTask, user, response=None, notes=""):
    from apps.documents.models import Document, DocumentAcknowledgment

    if task.status != "pending":
        raise BusinessRuleError("This task is already closed.")
    if not can_work(task, user):
        raise PermissionDenied("This task is not assigned to you.")
    emp = task.onboarding.employee
    if task.document_category_id and not Document.objects.filter(
            employee=emp, category=task.document_category, is_archived=False).exists():
        raise BusinessRuleError(f"Upload the employee's {task.document_category.name.lower()} to the personnel file "
                                "first.")
    if task.policy_document_id:
        doc = task.policy_document
        if user == emp.user:
            DocumentAcknowledgment.objects.get_or_create(document=doc, user=user, version=doc.current_version)
        elif not emp.user_id or not DocumentAcknowledgment.objects.filter(document=doc, user=emp.user).exists():
            raise BusinessRuleError("The employee has not yet acknowledged this policy.")
    task.response = _validate_form(task, response or {}) if task.form else {}
    task.status, task.completed_by, task.completed_at = "done", user, timezone.now()
    task.notes = notes or task.notes
    task.save()
    _check_complete(task.onboarding)
    return task


def waive_task(task: OnboardingTask, user, reason):
    if task.status != "pending":
        raise BusinessRuleError("This task is already closed.")
    if not reason:
        raise BusinessRuleError("Give a reason for waiving the task.")
    task.status, task.notes, task.completed_by, task.completed_at = "waived", reason, user, timezone.now()
    task.save()
    audit.log("update", task.onboarding, {"task_waived": task.title, "reason": reason})
    _check_complete(task.onboarding)
    return task


def reopen_task(task: OnboardingTask, user):
    if task.status == "pending":
        return task
    task.status, task.completed_at, task.completed_by = "pending", None, None
    task.save()
    ob = task.onboarding
    if ob.status == "completed":
        ob.status, ob.completed_at = "in_progress", None
        ob.save(update_fields=["status", "completed_at", "updated_at"])
    return task


def _check_complete(ob: Onboarding):
    if not ob.tasks.filter(status="pending", is_mandatory=True).exists() and ob.status == "in_progress":
        ob.status, ob.completed_at = "completed", timezone.now()
        ob.save(update_fields=["status", "completed_at", "updated_at"])


def progress(ob: Onboarding, today=None):
    today = today or dt.date.today()
    tasks = list(ob.tasks.all())
    total = len(tasks)
    closed = sum(1 for t in tasks if t.status != "pending")
    overdue = sum(1 for t in tasks if t.status == "pending" and t.due_date < today)
    return {"total": total, "done": closed, "overdue": overdue,
            "percent": round(100 * closed / total) if total else 100}


def escalate_overdue(today=None):
    """Daily: remind owners of overdue tasks and escalate to HR (once per task)."""
    from apps.notifications.services import notify

    today = today or dt.date.today()
    n = 0
    qs = OnboardingTask.objects.filter(status="pending", due_date__lt=today, escalated_at__isnull=True,
                                       onboarding__status="in_progress").select_related("onboarding__employee")
    for t in qs:
        owners = owner_users(t)
        hr = _role_users("hr_officer", t.organization_id)
        ctx = {"title": f"Overdue onboarding task: {t.title}",
               "body": f"'{t.title}' for {t.onboarding.employee.full_name} was due on {t.due_date:%d/%m/%Y}.",
               "link": "/onboarding/my-tasks"}
        notify("generic", owners, ctx, related=t.onboarding)
        notify("generic", [u for u in hr if u not in owners], {**ctx, "link": f"/onboarding/{t.onboarding_id}"},
               related=t.onboarding)
        t.escalated_at = timezone.now()
        t.save(update_fields=["escalated_at"])
        n += 1
    return n


def dashboard(today=None):
    today = today or dt.date.today()
    active = Onboarding.objects.filter(status="in_progress")
    overdue = OnboardingTask.objects.filter(status="pending", due_date__lt=today, onboarding__status="in_progress")
    done_recent = Onboarding.objects.filter(status="completed", completed_at__date__gte=today - dt.timedelta(days=90))
    durations = [(o.completed_at.date() - o.start_date).days for o in done_recent if o.completed_at]
    return {
        "active": active.count(),
        "starting_next_30_days": active.filter(start_date__gt=today,
                                               start_date__lte=today + dt.timedelta(days=30)).count(),
        "overdue_tasks": overdue.count(),
        "completed_90_days": done_recent.count(),
        "avg_days_to_complete": round(sum(durations) / len(durations), 1) if durations else None,
        "overdue_by_owner": list(overdue.values("owner_type").annotate(n=Count("id")).order_by("-n")),
        "probation_due_30_days": ProbationReview.objects.filter(
            status__in=["scheduled", "returned"], due_date__lte=today + dt.timedelta(days=30)).count(),
        "probation_overdue": ProbationReview.objects.filter(status__in=["scheduled", "returned"],
                                                            due_date__lt=today).count(),
    }


# ---------------------------------------------------------------- probation
def _reviewer_for(employee):
    sup = employee.supervisor
    return sup.user if sup and sup.user_id else None


def schedule_probation_reviews(employee, onboarding=None):
    end = employee.probation_end_date
    if not end:
        return []
    start = employee.hire_date
    length = (end - start).days
    reviewer = _reviewer_for(employee)
    out = []
    existing = set(ProbationReview.all_objects.filter(employee=employee, status__in=["scheduled", "returned"])
                   .values_list("review_type", flat=True))
    if length >= 90 and "midpoint" not in existing:
        out.append(ProbationReview.all_objects.create(
            organization_id=employee.organization_id, employee=employee, onboarding=onboarding,
            review_type="midpoint", due_date=start + dt.timedelta(days=length // 2), reviewer=reviewer))
    if "final" not in existing:
        out.append(ProbationReview.all_objects.create(
            organization_id=employee.organization_id, employee=employee, onboarding=onboarding, review_type="final",
            due_date=max(start, end - dt.timedelta(days=14)), reviewer=reviewer))
    return out


def can_review(review: ProbationReview, user):
    if review.reviewer_id:
        return review.reviewer_id == user.pk or has_perm(user, "onboarding.manage")
    sup = review.employee.supervisor
    return bool(sup and sup.user_id == user.pk) or has_perm(user, "onboarding.manage")


@transaction.atomic
def submit_review(review: ProbationReview, user, data: dict):
    from apps.workflow import engine

    if review.status not in ("scheduled", "returned"):
        raise BusinessRuleError("This review has already been submitted.")
    if not can_review(review, user):
        raise PermissionDenied("Only the assigned reviewer can complete this review.")
    if review.employee.user_id == user.pk:
        raise PermissionDenied("You cannot review your own probation.")
    ratings = {}
    for c in ProbationReview.CRITERIA:
        try:
            val = int((data.get("ratings") or {}).get(c))
        except (TypeError, ValueError):
            raise BusinessRuleError(f"Rate '{c}' from 1 to 5.") from None
        if not 1 <= val <= 5:
            raise BusinessRuleError(f"Rate '{c}' from 1 to 5.")
        ratings[c] = val
    rec = data.get("recommendation")
    allowed = ["continue", "terminate"] if review.review_type == "midpoint" else ["confirm", "extend", "terminate"]
    if rec not in allowed:
        raise BusinessRuleError(f"Choose one of: {', '.join(dict(ProbationReview.RECOMMENDATIONS)[a] for a in allowed)}.")
    months = int(data.get("extend_months") or 0)
    if rec == "extend" and not 1 <= months <= MAX_EXTENSION_MONTHS:
        raise BusinessRuleError(f"Extend probation by 1 to {MAX_EXTENSION_MONTHS} months.")
    if rec in ("extend", "terminate") and not data.get("improvements"):
        raise BusinessRuleError("Record the performance gaps that support this recommendation.")
    review.ratings = ratings
    review.overall_rating = (Decimal(sum(ratings.values())) / len(ratings)).quantize(Decimal("0.01"),
                                                                                     rounding=ROUND_HALF_UP)
    for f in ("strengths", "improvements", "reviewer_comments"):
        setattr(review, f, data.get(f, "") or "")
    review.recommendation, review.extend_months = rec, months if rec == "extend" else 0
    review.submitted_at = timezone.now()
    resubmit = review.status == "returned"
    if rec == "continue":
        review.status, review.decided_at = "completed", timezone.now()
        review.save()
        return review
    review.status = "submitted"
    review.save()
    if resubmit:
        from apps.recruitment.services import _instance

        inst = _instance(review)
        if inst and inst.status == "returned":
            engine.resubmit(inst, user)
            return review
    engine.start(review, "probation_outcome", user, subject_employee=review.employee,
                 extra_context={"recommendation": rec, "review_type": review.review_type})
    return review


@transaction.atomic
def apply_decision(review: ProbationReview, actor=None):
    from apps.employees import services as emp_services

    emp = review.employee
    today = dt.date.today()
    if review.recommendation == "confirm":
        effective = max(emp.probation_end_date or today, emp.hire_date)
        emp_services.confirm_appointment(emp, effective, user=actor,
                                         reason=f"Confirmed after probation review (rating {review.overall_rating})")
        emp.refresh_from_db()
        emp.confirmation_date = effective
        emp.save(update_fields=["confirmation_date", "updated_at"])
        _issue_letter(emp, "confirmation")
    elif review.recommendation == "extend":
        base = emp.probation_end_date or today
        new_end = _add_months(base, review.extend_months)
        emp_services.extend_probation(emp, new_end, user=actor,
                                      reason=f"Probation extended by {review.extend_months} month(s) after review")
        emp.refresh_from_db()
        ProbationReview.objects.create(employee=emp, onboarding=review.onboarding, review_type="final",
                                       due_date=max(today, new_end - dt.timedelta(days=14)),
                                       reviewer=_reviewer_for(emp))
    elif review.recommendation == "terminate":
        emp_services.separate(emp, today, "probation_termination", notes="Appointment terminated during probation",
                              rehire_eligible=False, user=actor)
        ProbationReview.objects.filter(employee=emp, status__in=["scheduled", "returned"]).update(status="cancelled")
    review.status, review.decided_at = "completed", timezone.now()
    review.save(update_fields=["status", "decided_at", "updated_at"])
    return review


def _add_months(d: dt.date, months: int) -> dt.date:
    import calendar

    m = d.month - 1 + months
    y, m = d.year + m // 12, m % 12 + 1
    return dt.date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def _issue_letter(employee, template_code):
    from apps.documents.models import LetterTemplate
    from apps.documents.services import generate_letter

    tpl = LetterTemplate.objects.filter(code=template_code, is_active=True).first()
    if tpl is not None:
        try:
            generate_letter(tpl, employee)
        except Exception:  # letter generation must never block the HR decision
            return None
    return tpl


def acknowledge_review(review: ProbationReview, user, comments=""):
    if review.employee.user_id != user.pk:
        raise PermissionDenied("Only the employee can acknowledge their review.")
    if review.status not in ("submitted", "completed"):
        raise BusinessRuleError("This review has not been submitted yet.")
    review.employee_comments, review.employee_acknowledged_at = comments, timezone.now()
    review.save(update_fields=["employee_comments", "employee_acknowledged_at", "updated_at"])
    return review


def remind_due_reviews(today=None):
    from apps.notifications.services import notify

    today = today or dt.date.today()
    n = 0
    for r in ProbationReview.objects.filter(status__in=["scheduled", "returned"], reminded_at__isnull=True,
                                            due_date__lte=today + dt.timedelta(days=7)).select_related("employee"):
        sup = r.employee.supervisor
        users = ([r.reviewer] if r.reviewer_id else [sup.user] if sup and sup.user_id
                 else _role_users("hr_officer", r.organization_id))
        notify("generic", users, {
            "title": f"{r.get_review_type_display()} due: {r.employee.full_name}",
            "body": f"Complete the {r.get_review_type_display().lower()} for {r.employee.full_name} by "
                    f"{r.due_date:%d/%m/%Y}. Probation ends {r.employee.probation_end_date:%d/%m/%Y}."
            if r.employee.probation_end_date else f"Complete the review by {r.due_date:%d/%m/%Y}.",
            "link": "/onboarding/probation"}, related=r)
        r.reminded_at = timezone.now()
        r.save(update_fields=["reminded_at"])
        n += 1
    return n
