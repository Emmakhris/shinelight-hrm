"""Performance management: cycles, cascading objectives, self/manager/360 reviews, calibration,
acknowledgment and improvement plans (features.txt sections 12-13).

Flow per appraisal:
objective_setting -> objectives_pending (supervisor approval via the workflow engine) -> objectives_agreed
-> [mid-year check-in] -> self_review -> manager_review -> calibration (optional) -> acknowledgement -> completed
"""

import datetime as dt
import random
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.db.models import Count, F, Q
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from apps.audit import services as audit
from apps.core.exceptions import BusinessRuleError
from apps.employees.models import Employee
from apps.rbac.services import can_access_employee, has_perm

from .models import (
    DEFAULT_LEVELS,
    Appraisal,
    AppraisalTemplate,
    CompetencyRating,
    FeedbackRequest,
    ImprovementPlan,
    Objective,
    RatingScale,
    ReviewCycle,
)

FEEDBACK_MIN_RESPONSES = 3  # 360 anonymity threshold
MAX_FEEDBACK_REQUESTS = 8
LOW_RATING = 2  # ratings at or below this need comments and a development plan
ACTIVE_STATUSES = ["active", "probation", "on_leave"]


def q2(x):
    return Decimal(x).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def default_scale():
    scale = RatingScale.objects.filter(is_default=True).first() or RatingScale.objects.first()
    if scale is None:
        scale = RatingScale.objects.create(name="5-point scale", levels=DEFAULT_LEVELS, is_default=True)
    return scale


def _instance(obj):
    from apps.recruitment.services import _instance as inst

    return inst(obj)


def _notify(users, title, body, link):
    from apps.notifications.services import notify

    users = [u for u in users if u is not None]
    if users:
        notify("generic", users, {"title": title, "body": body, "link": link})


# ---------------------------------------------------------------- templates & launch
def choose_template(employee):
    best, best_score = None, -1
    clinical = bool(employee.job_title_id and employee.job_title.is_clinical)
    family = employee.job_title.family_id if employee.job_title_id else None
    for t in AppraisalTemplate.objects.filter(is_active=True):
        if t.clinical_only and not clinical:
            continue
        if t.job_family_id and t.job_family_id != family:
            continue
        if t.category_id and t.category_id != employee.category_id:
            continue
        score = 4 * bool(t.job_family_id) + 2 * bool(t.category_id) + t.clinical_only
        if score > best_score:
            best, best_score = t, score
    return best


def reviewer_for(employee):
    sup = employee.supervisor
    if sup and sup.user_id and sup.status != "exited":
        return sup.user
    from apps.workflow.engine import _dept_head_user

    return _dept_head_user(employee)


def eligible(cycle: ReviewCycle):
    statuses = ACTIVE_STATUSES if cycle.include_probation else [s for s in ACTIVE_STATUSES if s != "probation"]
    qs = Employee.objects.filter(status__in=statuses,
                                 hire_date__lte=cycle.period_end - dt.timedelta(days=cycle.min_service_days))
    if cycle.departments.exists():
        from apps.rbac.services import department_descendants

        ids = set()
        for d in cycle.departments.all():
            ids.update(department_descendants(d.id))
        qs = qs.filter(department_id__in=ids)
    return qs.select_related("job_title", "supervisor__user", "department")


@transaction.atomic
def launch_cycle(cycle: ReviewCycle, user):
    if cycle.status != "draft":
        raise BusinessRuleError("This cycle has already been launched.")
    if cycle.period_end <= cycle.period_start:
        raise BusinessRuleError("The period end must be after the start.")
    created, skipped = 0, []
    for emp in eligible(cycle):
        if Appraisal.objects.filter(cycle=cycle, employee=emp).exists():
            continue
        tpl = choose_template(emp)
        if tpl is None:
            skipped.append(emp.full_name)
            continue
        ap = Appraisal.objects.create(cycle=cycle, employee=emp, template=tpl, reviewer=reviewer_for(emp))
        for comp in tpl.competencies.filter(is_active=True):
            CompetencyRating.objects.create(appraisal=ap, competency=comp)
        created += 1
    if not created:
        raise BusinessRuleError("No eligible employees with a matching appraisal template.")
    cycle.status, cycle.launched_at = "goal_setting", timezone.now()
    cycle.save(update_fields=["status", "launched_at", "updated_at"])
    users = [a.employee.user for a in cycle.appraisals.select_related("employee__user") if a.employee.user_id]
    deadline = f" by {cycle.goal_setting_deadline:%d/%m/%Y}" if cycle.goal_setting_deadline else ""
    _notify(users, f"{cycle.name}: set your objectives",
            f"Agree your objectives for {cycle.name} with your supervisor{deadline}.", "/performance/my")
    audit.log("update", cycle, {"action": "launched", "appraisals": created})
    return {"created": created, "skipped_no_template": skipped}


# ---------------------------------------------------------------- access
def can_view(ap: Appraisal, user) -> bool:
    return (ap.employee.user_id == user.pk or ap.reviewer_id == user.pk
            or can_access_employee(user, "performance.view", ap.employee))


def is_employee(ap, user):
    return ap.employee.user_id == user.pk


def is_reviewer(ap, user):
    return ap.reviewer_id == user.pk


def scale_of(ap: Appraisal):
    return ap.template.rating_scale


def _check_rating(scale, value, what):
    try:
        value = int(value)
    except (TypeError, ValueError):
        raise BusinessRuleError(f"Rate '{what}'.") from None
    if value not in scale.values:
        raise BusinessRuleError(f"'{what}': rating must be one of {scale.values}.")
    return value


# ---------------------------------------------------------------- objectives
def validate_objectives(ap: Appraisal):
    objs = list(ap.objectives.all())
    t = ap.template
    if not t.min_objectives <= len(objs) <= t.max_objectives:
        raise BusinessRuleError(f"Set between {t.min_objectives} and {t.max_objectives} objectives "
                                f"(currently {len(objs)}).")
    total = sum((o.weight for o in objs), Decimal("0"))
    if total != Decimal("100"):
        raise BusinessRuleError(f"Objective weights must add up to 100% (currently {total:g}%).")
    for o in objs:
        if not o.measure:
            raise BusinessRuleError(f"Add a measure (KPI) for '{o.title}'.")
        if o.weight <= 0:
            raise BusinessRuleError(f"'{o.title}' needs a weight above zero.")
    return objs


def objectives_editable(ap: Appraisal, user):
    if ap.status not in ("objective_setting", "objectives_returned"):
        return False
    return is_employee(ap, user) or is_reviewer(ap, user) or has_perm(user, "performance.manage")


@transaction.atomic
def submit_objectives(ap: Appraisal, user):
    from apps.workflow import engine

    if ap.status not in ("objective_setting", "objectives_returned"):
        raise BusinessRuleError("Objectives have already been submitted.")
    if not (is_employee(ap, user) or is_reviewer(ap, user)):
        raise PermissionDenied("Only the employee or their reviewer can submit objectives.")
    validate_objectives(ap)
    if is_reviewer(ap, user):
        # the approver set them: agreed without a separate approval step
        ap.status = "objectives_agreed"
        ap.save(update_fields=["status", "updated_at"])
        _notify([ap.employee.user], f"Objectives agreed: {ap.cycle.name}",
                "Your supervisor has set and agreed your objectives. Review them under My performance.",
                "/performance/my")
        return ap
    resubmit = ap.status == "objectives_returned"
    ap.status = "objectives_pending"
    ap.save(update_fields=["status", "updated_at"])
    inst = _instance(ap) if resubmit else None
    if inst and inst.status == "returned":
        engine.resubmit(inst, user)
    else:
        engine.start(ap, "appraisal_objectives", user, subject_employee=ap.employee)
    return ap


def record_midyear(ap: Appraisal, user, items, comments=""):
    if ap.status != "objectives_agreed":
        raise BusinessRuleError("The mid-year check-in is recorded once objectives are agreed.")
    if not (is_employee(ap, user) or is_reviewer(ap, user)):
        raise PermissionDenied("Only the employee or reviewer can record the check-in.")
    valid = dict(Objective.PROGRESS)
    objs = {o.id: o for o in ap.objectives.all()}
    for it in items or []:
        o = objs.get(int(it.get("id", 0)))
        if o is None:
            continue
        if it.get("midyear_status") and it["midyear_status"] not in valid:
            raise BusinessRuleError("Unknown progress status.")
        o.midyear_status = it.get("midyear_status", o.midyear_status)
        o.midyear_comment = it.get("midyear_comment", o.midyear_comment)
        o.save(update_fields=["midyear_status", "midyear_comment", "updated_at"])
    ap.midyear_comments = comments or ap.midyear_comments
    ap.midyear_done_at = timezone.now()
    ap.save(update_fields=["midyear_comments", "midyear_done_at", "updated_at"])
    return ap


# ---------------------------------------------------------------- cycle phases
@transaction.atomic
def advance_cycle(cycle: ReviewCycle, user):
    """Move the cycle to its next phase and the appraisals that are ready with it."""
    out = {"from": cycle.status}
    if cycle.status == "goal_setting":
        cycle.status = "in_progress"
        out["objectives_not_agreed"] = cycle.appraisals.exclude(status__in=["objectives_agreed", "cancelled"]).count()
    elif cycle.status == "in_progress":
        cycle.status = "review"
        ready = cycle.appraisals.filter(status="objectives_agreed")
        out["moved_to_self_review"] = ready.update(status="self_review")
        out["objectives_not_agreed"] = cycle.appraisals.filter(
            status__in=["objective_setting", "objectives_pending", "objectives_returned"]).count()
        users = [a.employee.user for a in cycle.appraisals.filter(status="self_review").select_related("employee__user")]
        deadline = f" by {cycle.self_review_deadline:%d/%m/%Y}" if cycle.self_review_deadline else ""
        _notify(users, f"{cycle.name}: complete your self-assessment",
                f"Rate your objectives and competencies{deadline}.", "/performance/my")
    elif cycle.status == "review":
        pending = cycle.appraisals.filter(status__in=["self_review", "manager_review"]).count()
        out["reviews_outstanding"] = pending
        if cycle.use_calibration:
            cycle.status = "calibration"
        else:
            cycle.status = "closed"
            _close(cycle)
    elif cycle.status == "calibration":
        out["released"] = release_calibration(cycle, user)
        cycle.status = "closed"
        _close(cycle)
    else:
        raise BusinessRuleError("This cycle cannot be advanced.")
    cycle.save()
    out["to"] = cycle.status
    audit.log("update", cycle, {"action": "advanced", **out})
    return out


def _close(cycle):
    cycle.closed_at = timezone.now()


# ---------------------------------------------------------------- reviews
def _scores(ap: Appraisal, field="manager_rating"):
    objs = list(ap.objectives.all())
    tw = sum((o.weight for o in objs), Decimal("0"))
    obj_score = (sum(o.weight * getattr(o, field) for o in objs) / tw) if tw else None
    comps = [getattr(c, field) for c in ap.competency_ratings.all() if getattr(c, field) is not None]
    comp_score = Decimal(sum(comps)) / len(comps) if comps else None
    ow = Decimal(ap.template.objectives_weight)
    if obj_score is not None and comp_score is not None:
        overall = (ow * obj_score + (100 - ow) * comp_score) / 100
    else:
        overall = obj_score if obj_score is not None else comp_score
    return (q2(obj_score) if obj_score is not None else None, q2(comp_score) if comp_score is not None else None,
            q2(overall) if overall is not None else None)


def rating_from_score(scale, score):
    if score is None:
        return None
    values = scale.values
    r = int(Decimal(score).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return max(values[0], min(values[-1], r))


def _apply_ratings(ap, data, field, require_all=True):
    scale = scale_of(ap)
    objs = {o.id: o for o in ap.objectives.all()}
    comps = {c.id: c for c in ap.competency_ratings.select_related("competency")}
    for it in data.get("objectives") or []:
        o = objs.get(int(it.get("id", 0)))
        if o is None:
            continue
        if it.get(field) not in (None, ""):
            setattr(o, field, _check_rating(scale, it[field], o.title))
        if field == "self_rating" and "achievement" in it:
            o.achievement = it["achievement"] or ""
        if field == "manager_rating" and "manager_comment" in it:
            o.manager_comment = it["manager_comment"] or ""
        o.save()
    for it in data.get("competencies") or []:
        c = comps.get(int(it.get("id", 0)))
        if c is None:
            continue
        if it.get(field) not in (None, ""):
            setattr(c, field, _check_rating(scale, it[field], c.competency.name))
        if "comment" in it and field == "manager_rating":
            c.comment = it["comment"] or ""
        c.save()
    if require_all:
        missing = [o.title for o in objs.values() if getattr(o, field) is None]
        missing += [c.competency.name for c in comps.values() if getattr(c, field) is None]
        if missing:
            raise BusinessRuleError(f"Rate every item before submitting (missing: {', '.join(missing[:4])}).")


@transaction.atomic
def save_self_review(ap: Appraisal, user, data, submit=False):
    if not is_employee(ap, user):
        raise PermissionDenied("Only the employee completes the self-assessment.")
    if ap.status != "self_review":
        raise BusinessRuleError("The self-assessment is not open.")
    _apply_ratings(ap, data, "self_rating", require_all=submit)
    ap.self_comments = data.get("self_comments", ap.self_comments) or ""
    if submit:
        ap.status, ap.self_submitted_at = "manager_review", timezone.now()
        _notify([ap.reviewer], f"Appraisal ready for your review: {ap.employee.full_name}",
                f"{ap.employee.full_name} has completed the self-assessment for {ap.cycle.name}.",
                f"/performance/appraisals/{ap.id}")
    ap.save()
    return ap


def _manager_can_skip_self(ap):
    d = ap.cycle.self_review_deadline
    return ap.status == "self_review" and d is not None and d < dt.date.today()


@transaction.atomic
def save_manager_review(ap: Appraisal, user, data, submit=False):
    if not (is_reviewer(ap, user) or has_perm(user, "performance.manage")) or is_employee(ap, user):
        raise PermissionDenied("Only the assigned reviewer completes the manager review.")
    if not (ap.status == "manager_review" or _manager_can_skip_self(ap)):
        raise BusinessRuleError("The manager review opens after the self-assessment (or its deadline).")
    _apply_ratings(ap, data, "manager_rating", require_all=submit)
    for f in ("manager_comments", "development_needs"):
        if f in data:
            setattr(ap, f, data[f] or "")
    ap.objectives_score, ap.competencies_score, ap.overall_score = _scores(ap)
    if submit:
        rating = rating_from_score(scale_of(ap), ap.overall_score)
        if rating is not None and rating <= LOW_RATING and not (ap.manager_comments and ap.development_needs):
            raise BusinessRuleError("A low rating needs manager comments and a development plan.")
        ap.manager_rating = ap.final_rating = rating
        ap.manager_submitted_at = timezone.now()
        ap.status = "calibration" if ap.cycle.use_calibration else "acknowledgement"
        if ap.status == "acknowledgement":
            _notify([ap.employee.user], f"Your appraisal for {ap.cycle.name} is ready",
                    "Read your supervisor's review and acknowledge it.", f"/performance/appraisals/{ap.id}")
    ap.save()
    return ap


def calibrate(ap: Appraisal, user, rating, reason=""):
    if not has_perm(user, "performance.manage"):
        raise PermissionDenied("Only HR can calibrate ratings.")
    if ap.status != "calibration":
        raise BusinessRuleError("This appraisal is not in calibration.")
    rating = _check_rating(scale_of(ap), rating, "final rating")
    if rating != ap.manager_rating and not reason:
        raise BusinessRuleError("Record the reason for changing the manager's rating.")
    old = ap.final_rating
    ap.final_rating, ap.calibration_reason, ap.calibrated_by = rating, reason, user
    ap.save(update_fields=["final_rating", "calibration_reason", "calibrated_by", "updated_at"])
    audit.log("update", ap, {"action": "calibrated", "from": old, "to": rating, "reason": reason})
    return ap


def release_calibration(cycle, user):
    aps = list(cycle.appraisals.filter(status="calibration").select_related("employee__user"))
    for ap in aps:
        ap.status = "acknowledgement"
        ap.save(update_fields=["status", "updated_at"])
    _notify([a.employee.user for a in aps], f"Your appraisal for {cycle.name} is ready",
            "Read your final rating and your supervisor's comments, then acknowledge.", "/performance/my")
    return len(aps)


def acknowledge(ap: Appraisal, user, agrees: bool, comments=""):
    if not is_employee(ap, user):
        raise PermissionDenied("Only the employee can acknowledge their appraisal.")
    if ap.status != "acknowledgement":
        raise BusinessRuleError("This appraisal is not awaiting acknowledgment.")
    if not agrees and not comments:
        raise BusinessRuleError("Explain why you disagree; HR will follow up.")
    ap.employee_agrees, ap.employee_comments = agrees, comments
    ap.acknowledged_at = ap.completed_at = timezone.now()
    ap.status = "completed"
    ap.save()
    if not agrees:
        from apps.onboarding.services import _role_users

        _notify(_role_users("hr_officer", ap.organization_id), f"Appraisal disputed: {ap.employee.full_name}",
                f"{ap.employee.full_name} disagrees with the {ap.cycle.name} appraisal: {comments[:200]}",
                f"/performance/appraisals/{ap.id}")
    return ap


def reassign_reviewer(ap: Appraisal, user, reviewer):
    if not has_perm(user, "performance.manage"):
        raise PermissionDenied()
    if reviewer.pk == ap.employee.user_id:
        raise BusinessRuleError("An employee cannot review themselves.")
    ap.reviewer = reviewer
    ap.save(update_fields=["reviewer", "updated_at"])
    audit.log("update", ap, {"action": "reviewer_changed", "reviewer": reviewer.pk})
    return ap


# ---------------------------------------------------------------- 360 feedback
def request_feedback(ap: Appraisal, user, respondents):
    from django.contrib.auth import get_user_model

    if not ap.template.include_360:
        raise BusinessRuleError("360 feedback is not part of this appraisal template.")
    if not (is_employee(ap, user) or is_reviewer(ap, user) or has_perm(user, "performance.manage")):
        raise PermissionDenied()
    if ap.status in ("calibration", "acknowledgement", "completed", "cancelled"):
        raise BusinessRuleError("Feedback can no longer be requested for this appraisal.")
    User = get_user_model()
    created = []
    for r in respondents:
        u = User.objects.filter(pk=r.get("user"), organization=ap.organization, is_active=True).first()
        if u is None or u.pk in (ap.employee.user_id,):
            continue
        if ap.feedback_requests.count() >= MAX_FEEDBACK_REQUESTS:
            raise BusinessRuleError(f"At most {MAX_FEEDBACK_REQUESTS} people can be asked for feedback.")
        fr, was = FeedbackRequest.objects.get_or_create(appraisal=ap, respondent=u,
                                                        defaults={"relationship": r.get("relationship", "peer")})
        if was:
            created.append(fr)
    _notify([f.respondent for f in created], f"Feedback requested: {ap.employee.full_name}",
            f"You have been asked for confidential feedback on {ap.employee.full_name} for {ap.cycle.name}. "
            "Individual responses are never shown; only combined results from three or more people.",
            "/performance/feedback")
    return created


def submit_feedback(fr: FeedbackRequest, user, ratings, strengths="", improvements="", decline=False):
    if fr.respondent_id != user.pk:
        raise PermissionDenied("This feedback request is not yours.")
    if fr.status != "pending":
        raise BusinessRuleError("Feedback has already been given.")
    if decline:
        fr.status = "declined"
        fr.save(update_fields=["status", "updated_at"])
        return fr
    scale = scale_of(fr.appraisal)
    comp_ids = set(fr.appraisal.competency_ratings.values_list("competency_id", flat=True))
    clean = {}
    for k, v in (ratings or {}).items():
        if int(k) in comp_ids and v not in (None, ""):
            clean[str(int(k))] = _check_rating(scale, v, "competency")
    if not clean:
        raise BusinessRuleError("Rate at least one competency.")
    fr.ratings, fr.strengths, fr.improvements = clean, strengths, improvements
    fr.status, fr.submitted_at = "submitted", timezone.now()
    fr.save()
    return fr


def feedback_summary(ap: Appraisal):
    done = list(ap.feedback_requests.filter(status="submitted"))
    asked = ap.feedback_requests.exclude(status="declined").count()
    if len(done) < FEEDBACK_MIN_RESPONSES:
        return {"requested": asked, "received": len(done), "sufficient": False,
                "threshold": FEEDBACK_MIN_RESPONSES}
    names = dict(ap.competency_ratings.values_list("competency_id", "competency__name"))
    per = {}
    for fr in done:
        for k, v in fr.ratings.items():
            per.setdefault(int(k), []).append(v)
    comments = [c for fr in done for c in (fr.strengths, fr.improvements) if c]
    strengths = [fr.strengths for fr in done if fr.strengths]
    improvements = [fr.improvements for fr in done if fr.improvements]
    rnd = random.Random(ap.pk)  # stable order that does not reveal who wrote what
    rnd.shuffle(strengths)
    rnd.shuffle(improvements)
    return {"requested": asked, "received": len(done), "sufficient": True, "threshold": FEEDBACK_MIN_RESPONSES,
            "competencies": [{"competency": names.get(k, str(k)), "average": q2(Decimal(sum(v)) / len(v)),
                              "responses": len(v)} for k, v in per.items()],
            "strengths": strengths, "improvements": improvements, "comment_count": len(comments)}


# ---------------------------------------------------------------- improvement plans
@transaction.atomic
def submit_plan(plan: ImprovementPlan, user):
    from apps.workflow import engine

    if plan.status not in ("draft", "returned"):
        raise BusinessRuleError("Only draft or returned plans can be submitted.")
    if plan.end_date <= plan.start_date:
        raise BusinessRuleError("The end date must be after the start date.")
    if (plan.end_date - plan.start_date).days < 30:
        raise BusinessRuleError("An improvement plan should run for at least 30 days to give a fair chance.")
    if not plan.milestones.exists():
        raise BusinessRuleError("Add at least one measurable milestone.")
    if not plan.support:
        raise BusinessRuleError("Describe the support (training, coaching, resources) the employee will receive.")
    resubmit = plan.status == "returned"
    plan.status = "pending"
    plan.save(update_fields=["status", "updated_at"])
    inst = _instance(plan) if resubmit else None
    if inst and inst.status == "returned":
        engine.resubmit(inst, user)
    else:
        engine.start(plan, "improvement_plan", user, subject_employee=plan.employee)
    return plan


def can_manage_plan(plan, user):
    return plan.supervisor_id == user.pk or has_perm(user, "performance.manage")


def close_plan(plan: ImprovementPlan, user, outcome, notes="", new_end_date=None):
    if not can_manage_plan(plan, user) or plan.employee.user_id == user.pk:
        raise PermissionDenied()
    if plan.status not in ("active", "extended"):
        raise BusinessRuleError("Only active plans can be closed or extended.")
    if not notes:
        raise BusinessRuleError("Record the outcome and evidence.")
    if outcome == "extended":
        if not new_end_date or new_end_date <= plan.end_date:
            raise BusinessRuleError("Give a new end date after the current one.")
        plan.end_date = new_end_date
    elif outcome not in ("successful", "unsuccessful"):
        raise BusinessRuleError("Outcome must be successful, unsuccessful or extended.")
    else:
        plan.closed_at = timezone.now()
    plan.status, plan.outcome_notes = outcome, notes
    plan.save()
    _notify([plan.employee.user], "Your performance improvement plan has been updated",
            f"Outcome: {plan.get_status_display()}.", "/performance/my")
    return plan


# ---------------------------------------------------------------- reporting & links
def cycle_summary(cycle: ReviewCycle):
    by_status = dict(cycle.appraisals.values_list("status").annotate(n=Count("id")))
    rated = cycle.appraisals.exclude(final_rating__isnull=True)
    dist = dict(rated.values_list("final_rating").annotate(n=Count("id")))
    total = sum(dist.values())
    scale = default_scale()
    labels = {int(lv["value"]): lv["label"] for lv in scale.levels}
    target = {int(k): v for k, v in (cycle.target_distribution or {}).items()}
    distribution = [{"rating": v, "label": labels.get(v, str(v)), "count": dist.get(v, 0),
                     "percent": round(100 * dist.get(v, 0) / total, 1) if total else 0,
                     "target_percent": target.get(v)} for v in sorted(labels, reverse=True)]
    changed = rated.exclude(final_rating=F("manager_rating")).count()
    return {"appraisals": cycle.appraisals.count(), "by_status": by_status, "distribution": distribution,
            "rated": total, "calibrated_changes": changed,
            "disputed": cycle.appraisals.filter(employee_agrees=False).count(),
            "low_ratings_without_plan": cycle.appraisals.filter(final_rating__lte=LOW_RATING)
            .filter(~Q(pips__status__in=["pending", "active", "extended", "successful", "unsuccessful"])).count()}


def latest_rating(employee, before=None):
    qs = Appraisal.objects.filter(employee=employee, final_rating__isnull=False,
                                  status__in=["acknowledgement", "completed"])
    if before:
        qs = qs.filter(cycle__period_end__lte=before)
    ap = qs.order_by("-cycle__period_end").first()
    return ap.final_rating if ap else None


def reminders(today=None):
    """Daily: remind people with an outstanding step three days before (and on) each deadline."""
    today = today or dt.date.today()
    n = 0
    for cycle in ReviewCycle.objects.exclude(status__in=["draft", "closed"]):
        steps = [("goal_setting", cycle.goal_setting_deadline, ["objective_setting", "objectives_returned"],
                  "employee", "set your objectives"),
                 ("review", cycle.self_review_deadline, ["self_review"], "employee", "complete your self-assessment"),
                 ("review", cycle.manager_review_deadline, ["manager_review"], "reviewer",
                  "complete the manager review")]
        for phase, deadline, statuses, who, what in steps:
            if cycle.status != phase or not deadline or (deadline - today).days not in (3, 0):
                continue
            for ap in cycle.appraisals.filter(status__in=statuses).select_related("employee__user", "reviewer"):
                u = ap.employee.user if who == "employee" else ap.reviewer
                _notify([u], f"Reminder: {cycle.name}", f"Please {what}"
                         f"{' for ' + ap.employee.full_name if who == 'reviewer' else ''} by {deadline:%d/%m/%Y}.",
                         f"/performance/appraisals/{ap.id}")
                n += 1
    for plan in ImprovementPlan.objects.filter(status__in=["active", "extended"], end_date=today + dt.timedelta(days=7)):
        _notify([plan.supervisor], f"Improvement plan ends in a week: {plan.employee.full_name}",
                "Prepare the outcome review with evidence for each milestone.", "/performance/plans")
        n += 1
    return n
