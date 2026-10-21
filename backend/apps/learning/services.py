"""Learning & development: catalogue, requests with budget approval, sessions and attendance, e-learning
with assessments, mandatory training and compliance, CPD, development plans and training effectiveness
(features.txt section 12; hospital mandatory clinical training)."""

import calendar
import datetime as dt
from decimal import Decimal

from django.db import transaction
from django.db.models import Avg, Count, Q, Sum
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from apps.audit import services as audit
from apps.core.exceptions import BusinessRuleError
from apps.employees.models import Employee
from apps.rbac.services import can_access_employee, has_perm

from .models import Course, CPDRecord, CPDRequirement, Enrollment, Session, TrainingBudget

D0 = Decimal("0")
MANDATORY_DUE_DAYS = 30
EXPIRING_DAYS = 60
EFFECTIVENESS_AFTER_DAYS = 30  # manager evaluates application on the job after this
ACTIVE = ["active", "probation", "on_leave"]


def add_months(d, months):
    m = d.month - 1 + months
    y, m = d.year + m // 12, m % 12 + 1
    return dt.date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def _notify(users, title, body, link):
    from apps.notifications.services import notify

    users = [u for u in users if u is not None]
    if users:
        notify("generic", users, {"title": title, "body": body, "link": link})


def _instance(obj):
    from apps.recruitment.services import _instance as inst

    return inst(obj)


# ---------------------------------------------------------------- budgets
def budget_status(department, year):
    if department is None:
        return None
    b = TrainingBudget.objects.filter(department=department, year=year).first()
    if b is None:
        return None
    spent = (Enrollment.objects.filter(employee__department=department, created_at__year=year,
                                       status__in=["enrolled", "in_progress", "completed", "failed", "no_show"])
             .aggregate(s=Sum("cost"))["s"] or D0)
    pending = (Enrollment.objects.filter(employee__department=department, created_at__year=year, status="pending")
               .aggregate(s=Sum("cost"))["s"] or D0)
    return {"budget": b.amount, "committed": spent, "pending": pending, "available": b.amount - spent}


# ---------------------------------------------------------------- requests & enrolment
def _open_enrollment(employee, course):
    return Enrollment.objects.filter(employee=employee, course=course, status__in=Enrollment.OPEN).first()


def _seats_left(session, exclude=None):
    taken = session.enrollments.filter(status__in=["enrolled", "in_progress", "completed", "failed"])
    if exclude is not None:
        taken = taken.exclude(pk=exclude.pk)
    return session.capacity - taken.count()


@transaction.atomic
def request_training(employee, course: Course, user, session=None, reason="", source="request",
                     development_goal=None) -> Enrollment:
    """Employee or manager asks for a course. Paid or external training goes through approval;
    free internal courses enrol directly."""
    from apps.workflow import engine

    if not course.is_active:
        raise BusinessRuleError("This course is not available.")
    own = getattr(user, "employee", None) == employee
    if own and not course.self_enrol:
        raise BusinessRuleError("This course is by nomination only. Ask your supervisor or HR.")
    if not own and not (can_access_employee(user, "learning.view", employee) or has_perm(user, "learning.manage")):
        raise PermissionDenied("You cannot nominate this employee.")
    if _open_enrollment(employee, course):
        raise BusinessRuleError("There is already an open enrolment for this course.")
    if session is not None:
        if session.course_id != course.id or session.status != "scheduled":
            raise BusinessRuleError("Choose a scheduled session of this course.")
        if session.registration_deadline and session.registration_deadline < dt.date.today():
            raise BusinessRuleError("Registration for this session has closed.")
    elif course.delivery in ("classroom", "blended") and course.sessions.filter(status="scheduled").exists():
        raise BusinessRuleError("Choose a session date.")
    needs_approval = course.cost_per_participant > 0 or course.delivery == "external"
    if needs_approval and source in ("request", "manager") and not reason:
        raise BusinessRuleError("Explain how this training will help in the role.")
    e = Enrollment.objects.create(employee=employee, course=course, session=session, source=source, reason=reason,
                                  cost=course.cost_per_participant, development_goal=development_goal,
                                  status="pending" if needs_approval else "enrolled")
    if needs_approval:
        st = budget_status(employee.department, dt.date.today().year)
        engine.start(e, "training_request", user, subject_employee=employee,
                     extra_context={"amount": float(e.cost), "external": course.delivery == "external",
                                    "over_budget": bool(st and e.cost > st["available"])})
    else:
        _place(e)
    return e


def _place(e: Enrollment):
    """Confirm a seat (or waitlist) once enrolment is approved."""
    if e.session_id and _seats_left(e.session, exclude=e) <= 0:
        e.status = "waitlisted"
    else:
        e.status = "enrolled"
    e.save(update_fields=["status", "updated_at"])
    if e.employee.user_id:
        when = f" on {timezone.localtime(e.session.start):%d/%m/%Y %H:%M} at {e.session.venue}" if e.session_id else ""
        _notify([e.employee.user], f"Training: {e.course.title}",
                f"You are {'waitlisted' if e.status == 'waitlisted' else 'enrolled'} for {e.course.title}{when}.",
                f"/learning/enrollments/{e.id}")
    return e


def assign(course: Course, employees, user, due_date=None, source="hr"):
    """HR / training officer assigns a course (no approval needed)."""
    n = 0
    for emp in employees:
        if _open_enrollment(emp, course):
            continue
        Enrollment.objects.create(employee=emp, course=course, source=source, status="enrolled",
                                  due_date=due_date or dt.date.today() + dt.timedelta(days=MANDATORY_DUE_DAYS),
                                  cost=course.cost_per_participant if course.delivery == "external" else D0)
        n += 1
    return n


def cancel(e: Enrollment, user, reason=""):
    if e.status not in Enrollment.OPEN:
        raise BusinessRuleError("This enrolment is already closed.")
    if e.source == "mandatory" and not has_perm(user, "learning.manage"):
        raise BusinessRuleError("Mandatory training cannot be cancelled by the employee.")
    inst = _instance(e)
    if inst and inst.status in ("pending", "returned"):
        from apps.workflow import engine

        engine.cancel(inst, user, reason or "Cancelled")
    e.status = "cancelled"
    e.save(update_fields=["status", "updated_at"])
    if e.session_id:  # promote the first waitlisted person
        nxt = e.session.enrollments.filter(status="waitlisted").order_by("created_at").first()
        if nxt:
            _place(nxt)
    return e


# ---------------------------------------------------------------- e-learning
def mark_module(e: Enrollment, module_id, user):
    if e.employee.user_id != user.pk:
        raise PermissionDenied()
    if e.status not in ("enrolled", "in_progress"):
        raise BusinessRuleError("This enrolment is not active.")
    if not e.course.modules.filter(pk=module_id).exists():
        raise BusinessRuleError("Unknown module.")
    if module_id not in e.modules_done:
        e.modules_done = [*e.modules_done, int(module_id)]
    e.status = "in_progress"
    e.save(update_fields=["modules_done", "status", "updated_at"])
    if not e.course.questions.exists() and set(e.modules_done) >= set(e.course.modules.values_list("pk", flat=True)):
        complete(e)
    return e


def submit_quiz(e: Enrollment, user, answers: dict):
    """answers: {question_id: [option indexes]}. Returns score %. Passing completes the course."""
    if e.employee.user_id != user.pk:
        raise PermissionDenied()
    if e.status not in ("enrolled", "in_progress"):
        raise BusinessRuleError("This enrolment is not active.")
    module_ids = set(e.course.modules.values_list("pk", flat=True))
    if not module_ids <= set(e.modules_done):
        raise BusinessRuleError("Complete all the modules before the assessment.")
    qs = list(e.course.questions.all())
    if not qs:
        raise BusinessRuleError("This course has no assessment.")
    total = sum(q.points for q in qs)
    got = 0
    for q in qs:
        raw = (answers or {}).get(str(q.id), (answers or {}).get(q.id, []))
        given = sorted(int(x) for x in (raw if isinstance(raw, list) else [raw]))
        if given == sorted(int(x) for x in q.correct):
            got += q.points
    score = round(100 * got / total) if total else 0
    e.attempts += 1
    e.quiz_score = score
    e.status = "in_progress"
    e.save(update_fields=["attempts", "quiz_score", "status", "updated_at"])
    if score >= e.course.pass_mark:
        complete(e)
    elif e.attempts >= 3:
        e.status = "failed"
        e.save(update_fields=["status", "updated_at"])
    return score


# ---------------------------------------------------------------- completion
@transaction.atomic
def complete(e: Enrollment, completed_on=None, score=None, assessor=""):
    from apps.hospital.models import CompetencyRecord

    completed_on = completed_on or dt.date.today()
    e.status, e.completed_at = "completed", completed_on
    if score is not None:
        e.quiz_score = score
    c = e.course
    e.expires_on = add_months(completed_on, c.refresher_months) if c.refresher_months else None
    e.save()
    if c.cpd_credits > 0 and not CPDRecord.objects.filter(enrollment=e).exists():
        CPDRecord.objects.create(employee=e.employee, title=c.title, provider=c.provider or "Internal",
                                 activity_date=completed_on, credits=c.cpd_credits, category=c.get_category_display(),
                                 enrollment=e, status="verified")
    if c.competency_requirement_id:
        CompetencyRecord.objects.create(employee=e.employee, requirement=c.competency_requirement,
                                        completed_on=completed_on, expires_on=e.expires_on,
                                        assessor=assessor or "Training record",
                                        score=f"{e.quiz_score}%" if e.quiz_score is not None else "")
    if e.development_goal_id and e.development_goal.status == "planned":
        e.development_goal.status = "in_progress"
        e.development_goal.save(update_fields=["status", "updated_at"])
    return e


def record_attendance(session: Session, user, rows):
    """rows: [{"enrollment": id, "attended": bool, "score": int|None}] -> completes or marks no-show."""
    if not has_perm(user, "learning.manage"):
        raise PermissionDenied()
    if session.status == "cancelled":
        raise BusinessRuleError("This session was cancelled.")
    if session.start.date() > dt.date.today():
        raise BusinessRuleError("Attendance can be recorded once the session has taken place.")
    done = 0
    for r in rows:
        e = session.enrollments.filter(pk=r.get("enrollment")).first()
        if e is None or e.status not in ("enrolled", "in_progress"):
            continue
        if r.get("attended"):
            score = r.get("score")
            if score not in (None, "") and int(score) < session.course.pass_mark:
                e.status, e.quiz_score, e.completed_at = "failed", int(score), session.end.date()
                e.save()
            else:
                complete(e, session.end.date(), int(score) if score not in (None, "") else None, session.trainer)
        else:
            e.status = "no_show"
            e.save(update_fields=["status", "updated_at"])
        done += 1
    session.status = "completed"
    session.save(update_fields=["status", "updated_at"])
    audit.log("update", session, {"action": "attendance", "rows": done})
    return done


def give_feedback(e: Enrollment, user, rating, comments=""):
    if e.employee.user_id != user.pk:
        raise PermissionDenied()
    if e.status != "completed":
        raise BusinessRuleError("Give feedback after completing the training.")
    rating = int(rating)
    if not 1 <= rating <= 5:
        raise BusinessRuleError("Rate the training from 1 to 5.")
    e.feedback_rating, e.feedback_comments = rating, comments
    e.save(update_fields=["feedback_rating", "feedback_comments", "updated_at"])
    return e


def evaluate_effectiveness(e: Enrollment, user, rating, comments=""):
    sup = e.employee.supervisor
    if not ((sup and sup.user_id == user.pk) or has_perm(user, "learning.manage")) or e.employee.user_id == user.pk:
        raise PermissionDenied("The employee's supervisor evaluates how the training is applied.")
    if e.status != "completed":
        raise BusinessRuleError("Only completed training can be evaluated.")
    rating = int(rating)
    if not 1 <= rating <= 5:
        raise BusinessRuleError("Rate from 1 to 5.")
    e.effectiveness_rating, e.effectiveness_comments, e.effectiveness_by = rating, comments, user
    e.save(update_fields=["effectiveness_rating", "effectiveness_comments", "effectiveness_by", "updated_at"])
    return e


# ---------------------------------------------------------------- mandatory training & compliance
def mandatory_courses_for(employee):
    qs = Course.objects.filter(is_active=True, is_mandatory=True)
    return qs.filter(Q(applies_to_all=True) | Q(job_titles=employee.job_title_id)).distinct()


def _latest_completion(employee, course):
    return (Enrollment.objects.filter(employee=employee, course=course, status="completed")
            .order_by("-completed_at").first())


def course_status(employee, course, today=None):
    today = today or dt.date.today()
    last = _latest_completion(employee, course)
    if last is None:
        return "missing", None
    if last.expires_on and last.expires_on < today:
        return "expired", last
    if last.expires_on and (last.expires_on - today).days <= EXPIRING_DAYS:
        return "expiring", last
    return "current", last


def assign_mandatory(today=None):
    """Daily: open an enrolment for every missing, expired or expiring mandatory course."""
    today = today or dt.date.today()
    created = 0
    for emp in Employee.objects.filter(status__in=ACTIVE).select_related("user"):
        new = []
        for course in mandatory_courses_for(emp):
            status, last = course_status(emp, course, today)
            if status == "current" or _open_enrollment(emp, course):
                continue
            due = last.expires_on if status == "expiring" and last and last.expires_on else \
                today + dt.timedelta(days=MANDATORY_DUE_DAYS)
            Enrollment.objects.create(employee=emp, course=course, source="mandatory", status="enrolled",
                                      due_date=due)
            new.append(course.title)
            created += 1
        if new and emp.user_id:
            _notify([emp.user], "Mandatory training assigned", f"Please complete: {', '.join(new)}.", "/learning")
    return created


def compliance_matrix(department=None, today=None):
    today = today or dt.date.today()
    emps = Employee.objects.filter(status__in=ACTIVE).select_related("job_title", "department")
    if department:
        from apps.rbac.services import department_descendants

        emps = emps.filter(department_id__in=department_descendants(int(department)))
    courses = list(Course.objects.filter(is_active=True, is_mandatory=True).prefetch_related("job_titles"))
    rows, totals = [], {"required": 0, "current": 0}
    for emp in emps:
        cells = {}
        for c in courses:
            if not (c.applies_to_all or any(j.id == emp.job_title_id for j in c.job_titles.all())):
                continue
            status, last = course_status(emp, c, today)
            cells[str(c.id)] = {"status": status, "expires_on": last.expires_on if last else None}
            totals["required"] += 1
            totals["current"] += status in ("current", "expiring")
        if cells:
            rows.append({"employee": emp.id, "name": emp.full_name, "department": emp.department.name
                         if emp.department_id else None, "job_title": emp.job_title.name if emp.job_title_id else None,
                         "cells": cells})
    return {"courses": [{"id": c.id, "title": c.title, "refresher_months": c.refresher_months} for c in courses],
            "rows": rows, "compliance_percent": round(100 * totals["current"] / totals["required"], 1)
            if totals["required"] else None}


# ---------------------------------------------------------------- CPD
def cpd_summary(employee, year=None):
    year = year or dt.date.today().year
    earned = (CPDRecord.objects.filter(employee=employee, activity_date__year=year, status="verified")
              .aggregate(s=Sum("credits"))["s"] or D0)
    req = CPDRequirement.objects.filter(job_titles=employee.job_title_id).order_by("-credits_per_year").first() \
        if employee.job_title_id else None
    required = req.credits_per_year if req else None
    return {"year": year, "earned": earned, "required": required, "requirement": req.name if req else None,
            "shortfall": max(D0, required - earned) if required is not None else None}


def verify_cpd(rec: CPDRecord, user, approve=True):
    if not has_perm(user, "learning.manage"):
        raise PermissionDenied()
    rec.status, rec.verified_by = ("verified" if approve else "rejected"), user
    rec.save(update_fields=["status", "verified_by", "updated_at"])
    return rec


# ---------------------------------------------------------------- needs analysis & reports
def training_needs(cycle=None, department=None):
    """Skills gaps from appraisals (competencies rated at or below 'needs improvement') and missing mandatory
    training, with the courses that address each gap."""
    from apps.performance.models import Appraisal, CompetencyRating

    aps = Appraisal.objects.filter(final_rating__isnull=False)
    if cycle:
        aps = aps.filter(cycle_id=cycle)
    else:
        latest = Appraisal.objects.filter(final_rating__isnull=False).order_by("-cycle__period_end").first()
        aps = aps.filter(cycle_id=latest.cycle_id) if latest else aps.none()
    if department:
        aps = aps.filter(employee__department_id=department)
    gaps = (CompetencyRating.objects.filter(appraisal__in=aps, manager_rating__lte=2)
            .values("competency_id", "competency__name").annotate(people=Count("appraisal__employee", distinct=True))
            .order_by("-people"))
    out = []
    for g in gaps:
        courses = Course.objects.filter(is_active=True, competencies=g["competency_id"])
        out.append({"competency": g["competency__name"], "people": g["people"],
                    "courses": [{"id": c.id, "title": c.title} for c in courses]})
    needs = list(aps.exclude(development_needs="").values("employee__id", "employee__first_name",
                                                         "employee__last_name", "development_needs")[:200])
    matrix = compliance_matrix(department)
    missing = {}
    for row in matrix["rows"]:
        for cid, cell in row["cells"].items():
            if cell["status"] in ("missing", "expired"):
                missing[cid] = missing.get(cid, 0) + 1
    titles = {str(c["id"]): c["title"] for c in matrix["courses"]}
    return {"competency_gaps": out,
            "development_needs": [{"employee": n["employee__id"],
                                   "name": f"{n['employee__first_name']} {n['employee__last_name']}",
                                   "needs": n["development_needs"]} for n in needs],
            "mandatory_gaps": [{"course": titles.get(k, k), "people": v} for k, v in
                               sorted(missing.items(), key=lambda x: -x[1])],
            "compliance_percent": matrix["compliance_percent"]}


def report(year=None, department=None):
    year = year or dt.date.today().year
    en = Enrollment.objects.filter(created_at__year=year)
    if department:
        en = en.filter(employee__department_id=department)
    done = en.filter(status="completed")
    session_cost = (Session.objects.filter(start__year=year, status="completed").aggregate(s=Sum("actual_cost"))["s"]
                    or D0)
    spend = (en.filter(status__in=["enrolled", "in_progress", "completed", "failed", "no_show"])
             .aggregate(s=Sum("cost"))["s"] or D0) + session_cost
    by_dept = (en.filter(status__in=["enrolled", "in_progress", "completed", "failed", "no_show"])
               .values("employee__department_id", "employee__department__name")
               .annotate(spent=Sum("cost"), completions=Count("id", filter=Q(status="completed"))))
    from apps.organization.models import Department

    budgets = []
    for row in by_dept:
        dep = Department.objects.filter(pk=row["employee__department_id"]).first()
        st = budget_status(dep, year) if dep else None
        budgets.append({"department": row["employee__department__name"] or "—", "spent": row["spent"] or D0,
                        "completions": row["completions"], "budget": st["budget"] if st else None})
    hours = sum((e.course.duration_hours for e in done.select_related("course")), Decimal("0"))
    n_done = done.count()
    return {
        "year": year, "enrolments": en.count(), "completions": n_done,
        "completion_rate": round(100 * n_done / en.exclude(status__in=["pending", "rejected", "cancelled"]).count(), 1)
        if en.exclude(status__in=["pending", "rejected", "cancelled"]).exists() else None,
        "training_hours": hours, "spend": spend,
        "cost_per_completion": round(spend / n_done, 2) if n_done else None,
        "avg_feedback": done.aggregate(a=Avg("feedback_rating"))["a"],
        "avg_effectiveness": done.aggregate(a=Avg("effectiveness_rating"))["a"],
        "pending_requests": Enrollment.objects.filter(status="pending").count(),
        "by_department": budgets,
        "by_course": list(done.values("course__title").annotate(n=Count("id"), feedback=Avg("feedback_rating"),
                                                                effectiveness=Avg("effectiveness_rating"))
                          .order_by("-n")[:15]),
    }


def reminders(today=None):
    """Daily: due-date reminders for open training and effectiveness evaluations for supervisors."""
    today = today or dt.date.today()
    n = 0
    for e in Enrollment.objects.filter(status__in=["enrolled", "in_progress"], due_date__isnull=False,
                                       due_date__in=[today + dt.timedelta(days=7), today]).select_related(
                                           "employee__user", "course"):
        _notify([e.employee.user], f"Training due: {e.course.title}", f"Complete it by {e.due_date:%d/%m/%Y}.",
                f"/learning/enrollments/{e.id}")
        n += 1
    target = today - dt.timedelta(days=EFFECTIVENESS_AFTER_DAYS)
    for e in Enrollment.objects.filter(status="completed", completed_at=target, effectiveness_rating__isnull=True,
                                       employee__supervisor__user__isnull=False).select_related(
                                           "employee__supervisor__user", "course", "employee"):
        _notify([e.employee.supervisor.user], f"How is {e.employee.full_name} applying '{e.course.title}'?",
                "Rate how the training is being applied on the job.", "/learning/team")
        n += 1
    return n
