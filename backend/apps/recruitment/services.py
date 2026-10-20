"""Recruitment: requisitions, vacancies, applications, screening, interviews, checks, offers and hiring.

Screening scores are advisory: the system flags knock-out answers and missing requirements but never
rejects a candidate on its own (features.txt section 3: AI/automation supports, not determines, hiring)."""

import datetime as dt
import secrets
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Avg, Count, Q, Sum
from django.template import Context, Template
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied

from apps.audit import services as audit
from apps.core.context import get_current_org
from apps.core.exceptions import BusinessRuleError
from apps.core.services import next_number

from .messages import CANDIDATE_MESSAGES
from .models import (
    QUALIFICATION_RANK,
    Application,
    ApplicationEvent,
    Candidate,
    Interview,
    Offer,
    ReferenceCheck,
    Requisition,
    Scorecard,
    Vacancy,
)

STAGE_ORDER = [s for s, _ in Application.STAGES]
# stages a recruiter can move to by hand; offer and hired happen through the offer/hire actions
MANUAL_STAGES = {"applied", "screening", "shortlisted", "interview", "assessment", "reference_check", "rejected",
                 "withdrawn"}
CANDIDATE_STAGE_MESSAGES = {"shortlisted": "shortlisted", "rejected": "regret"}


def q(x):
    return Decimal(x).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def retention_months():
    org = get_current_org()
    return int((org.settings or {}).get("recruitment_retention_months", 12)) if org else 12


def _instance(obj):
    from django.contrib.contenttypes.models import ContentType

    from apps.workflow.models import WorkflowInstance

    return WorkflowInstance.objects.filter(content_type=ContentType.objects.get_for_model(obj),
                                           object_id=obj.pk).order_by("-id").first()


# ---------------------------------------------------------------- requisitions
@transaction.atomic
def submit_requisition(req: Requisition, user):
    from apps.workflow import engine

    if req.status not in ("draft", "returned"):
        raise BusinessRuleError("Only draft or returned requisitions can be submitted.")
    if req.headcount < 1:
        raise BusinessRuleError("Headcount must be at least 1.")
    if req.salary_max and req.salary_min > req.salary_max:
        raise BusinessRuleError("Minimum salary cannot exceed the maximum.")
    if req.reason == "replacement" and not req.replacing_id:
        raise BusinessRuleError("Select the employee being replaced.")
    if req.position_id:
        p = req.position
        if p.status != "approved":
            raise BusinessRuleError(f"Position {p.code} is {p.get_status_display().lower()}; only approved positions "
                                    "can be recruited for.")
        if req.reason != "replacement" and p.vacancies < req.headcount:
            raise BusinessRuleError(f"Position {p.code} has {p.vacancies} vacancy(ies) in the approved establishment.",
                                    code="no_vacancy")
    if not req.reference:
        req.reference = next_number("requisition", default_prefix="REQ", default_pattern="{prefix}-{year}-{seq:04d}")
    resubmit = req.status == "returned"
    req.status = "pending"
    req.submitted_at = timezone.now()
    req.save()
    if resubmit:
        inst = _instance(req)
        if inst and inst.status == "returned":
            engine.resubmit(inst, user)
            return req
    engine.start(req, "job_requisition", user, subject_employee=req.requested_by,
                 extra_context={"amount": float(req.annual_budget), "headcount": req.headcount,
                                "reason": req.reason, "department": req.department.code})
    return req


def vacancy_from_requisition(req: Requisition, user) -> Vacancy:
    if req.status != "approved":
        raise BusinessRuleError("Only approved requisitions can be advertised.")
    existing = req.vacancies.exclude(status="cancelled").first()
    if existing:
        return existing
    jt = req.job_title
    return Vacancy.objects.create(
        requisition=req, title=jt.name, department=req.department, location=req.location,
        employment_type=req.employment_type, openings=req.headcount,
        summary=getattr(jt, "description", "") or "", recruiter=user, visibility="both")


# ---------------------------------------------------------------- vacancies
def publish_vacancy(v: Vacancy, user):
    if v.status not in ("draft", "closed"):
        raise BusinessRuleError("Only draft or closed vacancies can be published.")
    if v.requisition_id and v.requisition.status not in ("approved", "filled"):
        raise BusinessRuleError("The linked requisition is not approved.")
    if v.closing_date and v.closing_date < dt.date.today():
        raise BusinessRuleError("Set a closing date in the future before publishing.")
    if not (v.summary or v.responsibilities):
        raise BusinessRuleError("Add a summary or responsibilities before publishing.")
    for qn in v.screening_questions or []:
        if not qn.get("key") or not qn.get("question"):
            raise BusinessRuleError("Each screening question needs a key and question text.")
    if not v.reference:
        v.reference = next_number("vacancy", default_prefix="VAC", default_pattern="{prefix}-{year}-{seq:04d}")
    v.status = "published"
    v.published_at = v.published_at or timezone.now()
    v.closed_at = None
    if "career_site" not in (v.channels or []) and v.visibility != "internal":
        v.channels = list(v.channels or []) + ["career_site"]
    v.save()
    audit.log("update", v, {"action": "published"})
    return v


def close_vacancy(v: Vacancy, status="closed"):
    if v.status not in ("published", "draft", "closed"):
        raise BusinessRuleError("This vacancy is already finished.")
    v.status = status
    v.closed_at = timezone.now()
    v.save(update_fields=["status", "closed_at", "updated_at"])
    return v


def open_vacancies(internal: bool):
    today = dt.date.today()
    qs = Vacancy.objects.filter(status="published").filter(Q(closing_date__isnull=True) | Q(closing_date__gte=today))
    return qs.filter(visibility__in=["internal", "both"] if internal else ["external", "both"])


def close_expired_vacancies(today=None):
    today = today or dt.date.today()
    n = 0
    for v in Vacancy.objects.filter(status="published", closing_date__lt=today):
        close_vacancy(v)
        n += 1
    return n


# ---------------------------------------------------------------- applications
def screen(app: Application):
    """Rule-based screening: score out of 100 plus flags for the recruiter. Never auto-rejects."""
    v, c = app.vacancy, app.candidate
    flags, score, knocked = [], 0, False
    need = QUALIFICATION_RANK.get(v.min_qualification, 0)
    have = QUALIFICATION_RANK.get(c.highest_qualification, 0)
    if have >= need:
        score += 40
    else:
        flags.append(f"Qualification below the minimum ({v.get_min_qualification_display()}).")
    if v.min_experience_years:
        ratio = min(Decimal("1"), c.years_experience / v.min_experience_years)
        score += int(30 * ratio)
        if c.years_experience < v.min_experience_years:
            flags.append(f"{c.years_experience:g} years' experience; {v.min_experience_years} required.")
    else:
        score += 30
    questions = v.screening_questions or []
    if questions:
        passed = 0
        for qn in questions:
            ans = app.answers.get(qn["key"])
            ko = qn.get("knockout")
            if ko is not None and ko != "" and str(ans).strip().lower() == str(ko).strip().lower():
                knocked = True
                flags.append(f"Knock-out answer: {qn['question']}")
            elif ans not in (None, ""):
                passed += 1
        score += int(30 * passed / len(questions))
    else:
        score += 30
    if not app.cv:
        flags.append("No CV attached.")
    app.screening_score, app.screening_flags, app.knocked_out = min(score, 100), flags, knocked
    return app


def _validate_answers(v: Vacancy, answers: dict):
    answers = {k: v_ for k, v_ in (answers or {}).items() if isinstance(k, str)}
    for qn in v.screening_questions or []:
        if qn.get("required", True) and answers.get(qn["key"]) in (None, ""):
            raise BusinessRuleError(f"Please answer: {qn['question']}")
    return answers


@transaction.atomic
def apply(vacancy: Vacancy, candidate_data: dict, *, cv=None, cover_letter="", answers=None, source="career_site",
          employee=None, referred_by=None, consent=False, talent_pool=False, actor=None) -> Application:
    from apps.core.validators import validate_gh_phone
    from apps.documents.services import validate_upload

    internal = employee is not None
    if vacancy.status != "published" or (vacancy.closing_date and vacancy.closing_date < dt.date.today()):
        raise BusinessRuleError("This vacancy is not open for applications.")
    if internal and vacancy.visibility == "external":
        raise BusinessRuleError("This vacancy is not open to internal applicants.")
    if not internal and vacancy.visibility == "internal" and actor is None:
        raise BusinessRuleError("This vacancy is open to internal applicants only.")
    if not consent:
        raise BusinessRuleError("You must consent to the processing of your personal data to apply.",
                                code="consent_required")
    email = (candidate_data.get("email") or "").strip().lower()
    if not email:
        raise BusinessRuleError("An email address is required.")
    phone = (candidate_data.get("phone") or "").strip()
    if phone:
        try:
            validate_gh_phone(phone)
        except Exception as exc:
            raise BusinessRuleError("Enter a valid Ghana phone number (e.g. 024 123 4567).") from exc
    if cv is not None:
        validate_upload(cv)
    answers = _validate_answers(vacancy, answers)
    fields = ["first_name", "last_name", "phone", "gender", "location", "highest_qualification", "field_of_study",
              "years_experience", "current_employer", "current_title", "linkedin"]
    cand = Candidate.objects.filter(email__iexact=email).first()
    if cand is None:
        cand = Candidate(email=email, source=source)
    for f in fields:
        val = candidate_data.get(f)
        if val not in (None, ""):
            setattr(cand, f, val)
    if not cand.first_name or not cand.last_name:
        raise BusinessRuleError("First and last name are required.")
    if internal:
        cand.employee, cand.source = employee, "internal"
    cand.anonymised = False
    cand.consent_given_at = timezone.now()
    cand.talent_pool = cand.talent_pool or talent_pool
    cand.retain_until = dt.date.today() + dt.timedelta(days=30 * retention_months())
    cand.save()
    if Application.objects.filter(vacancy=vacancy, candidate=cand).exists():
        raise BusinessRuleError("You have already applied for this vacancy.", code="duplicate_application")
    app = Application(vacancy=vacancy, candidate=cand, cover_letter=cover_letter or "", answers=answers,
                      referred_by=referred_by, stage_changed_at=timezone.now(),
                      reference=next_number("application", default_prefix="APP",
                                            default_pattern="{prefix}-{year}-{seq:05d}"))
    if cv is not None:
        app.cv_name = getattr(cv, "name", "cv")[:255]
        app.cv.save(app.cv_name, cv, save=False)
    screen(app)
    app.save()
    ApplicationEvent.objects.create(application=app, to_stage="applied", actor=actor,
                                    note="Internal application" if internal else f"Source: {cand.get_source_display()}")
    message_candidate(app, "acknowledgment")
    return app


def message_candidate(app: Application, key: str, extra=None, sms=True):
    """Email (and optionally SMS) a candidate and log it on the application timeline."""
    from apps.notifications.tasks import send_email_task, send_sms_task

    tpl = CANDIDATE_MESSAGES.get(key)
    cand = app.candidate
    if not tpl or cand.anonymised:
        return False
    org = get_current_org() or app.organization
    ctx = Context({"candidate": cand, "vacancy": app.vacancy, "application": app, "organization": org,
                   **(extra or {})}, autoescape=False)
    subject = Template(tpl["subject"]).render(ctx)
    body = Template(tpl["body"]).render(ctx)
    if cand.email:
        send_email_task.delay(cand.email, subject, body, f"recruitment.{key}", app.organization_id)
    if sms and tpl.get("sms") and cand.phone and org and org.has_feature("sms"):
        send_sms_task.delay(cand.phone, Template(tpl["sms"]).render(ctx), f"recruitment.{key}", app.organization_id)
    ApplicationEvent.objects.create(application=app, kind="message", note=subject)
    return True


@transaction.atomic
def move_stage(app: Application, to_stage: str, user, note="", notify_candidate=True, reason=""):
    if to_stage not in MANUAL_STAGES:
        raise BusinessRuleError("Use the offer and hire actions to move a candidate to Offer or Hired.")
    if app.stage == "hired":
        raise BusinessRuleError("This candidate has already been hired.")
    if app.stage == to_stage:
        return app
    if to_stage == "rejected" and not (reason or note):
        raise BusinessRuleError("Record a reason before marking the application unsuccessful.")
    if app.stage == "offer" and app.offers.filter(status__in=["approved", "sent", "negotiating", "accepted"]).exists():
        raise BusinessRuleError("Withdraw the open offer first.")
    frm = app.stage
    app.stage = to_stage
    app.stage_changed_at = timezone.now()
    if to_stage == "rejected":
        app.rejection_reason = reason or note
    app.save()
    ApplicationEvent.objects.create(application=app, from_stage=frm, to_stage=to_stage, note=note or reason,
                                    actor=user)
    if notify_candidate and to_stage in CANDIDATE_STAGE_MESSAGES:
        message_candidate(app, CANDIDATE_STAGE_MESSAGES[to_stage], sms=False)
    return app


def _advance_to(app: Application, stage: str, user, note=""):
    if STAGE_ORDER.index(app.stage) < STAGE_ORDER.index(stage) and app.stage in Application.ACTIVE_STAGES:
        frm = app.stage
        app.stage, app.stage_changed_at = stage, timezone.now()
        app.save(update_fields=["stage", "stage_changed_at", "updated_at"])
        ApplicationEvent.objects.create(application=app, from_stage=frm, to_stage=stage, note=note, actor=user)


# ---------------------------------------------------------------- interviews & scorecards
@transaction.atomic
def schedule_interview(app: Application, data: dict, panel, user, notify=True) -> Interview:
    from apps.notifications.services import notify as notify_users

    if app.stage not in Application.ACTIVE_STAGES:
        raise BusinessRuleError("Only active applications can be scheduled for interview.")
    if not panel:
        raise BusinessRuleError("Add at least one panel member.")
    if data["scheduled_at"] < timezone.now():
        raise BusinessRuleError("The interview time must be in the future.")
    iv = Interview.objects.create(application=app, **data)
    iv.panel.set(panel)
    _advance_to(app, "interview", user, f"{iv.round_name} scheduled")
    if notify:
        message_candidate(app, "interview_invite", {"interview": iv})
        iv.candidate_notified = True
        iv.save(update_fields=["candidate_notified"])
    notify_users("generic", panel, {
        "title": f"Interview panel: {app.candidate.full_name} for {app.vacancy.title}",
        "body": f"You are on the panel for {iv.round_name} on {timezone.localtime(iv.scheduled_at):%d/%m/%Y %H:%M}"
                f"{' at ' + iv.venue if iv.venue else ''}. Submit your scorecard after the interview.",
        "link": "/recruitment/my-interviews"}, related=iv)
    return iv


def cancel_interview(iv: Interview, user, notify=True):
    if iv.status != "scheduled":
        raise BusinessRuleError("Only scheduled interviews can be cancelled.")
    iv.status = "cancelled"
    iv.save(update_fields=["status", "updated_at"])
    if notify:
        message_candidate(iv.application, "interview_cancelled", {"interview": iv})
    return iv


def weighted_score(criteria, ratings: dict) -> Decimal:
    total_w = sum(Decimal(str(c.get("weight") or 1)) for c in criteria) or Decimal("1")
    s = sum(Decimal(str(c.get("weight") or 1)) * Decimal(str(ratings[c["name"]])) for c in criteria)
    return q(s / total_w / 5 * 100)


@transaction.atomic
def submit_scorecard(iv: Interview, user, ratings: dict, recommendation: str, strengths="", concerns="",
                     conflict_of_interest=False) -> Scorecard:
    if not iv.panel.filter(pk=user.pk).exists():
        raise PermissionDenied("Only panel members can score this interview.")
    if iv.status == "cancelled":
        raise BusinessRuleError("This interview was cancelled.")
    if iv.scheduled_at > timezone.now() + dt.timedelta(minutes=15):
        raise BusinessRuleError("Scorecards can be submitted once the interview has started.")
    if Scorecard.objects.filter(interview=iv, panelist=user).exists():
        raise BusinessRuleError("You have already submitted a scorecard for this interview.")
    criteria = iv.application.vacancy.criteria
    clean = {}
    for c in criteria:
        val = ratings.get(c["name"])
        try:
            val = int(val)
        except (TypeError, ValueError):
            raise BusinessRuleError(f"Rate '{c['name']}' from 1 to 5.") from None
        if not 1 <= val <= 5:
            raise BusinessRuleError(f"Rate '{c['name']}' from 1 to 5.")
        clean[c["name"]] = val
    if recommendation not in dict(Scorecard.RECOMMENDATIONS):
        raise BusinessRuleError("Choose a recommendation.")
    if recommendation in ("no", "strong_no") and not concerns:
        raise BusinessRuleError("Explain your concerns when not recommending a candidate.")
    sc = Scorecard.objects.create(interview=iv, panelist=user, ratings=clean, recommendation=recommendation,
                                  overall_score=weighted_score(criteria, clean), strengths=strengths,
                                  concerns=concerns, conflict_of_interest=conflict_of_interest)
    if iv.scorecards.count() >= iv.panel.count() and iv.status == "scheduled":
        iv.status = "completed"
        iv.save(update_fields=["status", "updated_at"])
    return sc


def interview_summary(app: Application):
    cards = Scorecard.objects.filter(interview__application=app).exclude(conflict_of_interest=True)
    rec = dict(cards.values_list("recommendation").annotate(n=Count("id")))
    avg = cards.aggregate(a=Avg("overall_score"))["a"]
    return {"scorecards": cards.count(), "average_score": q(avg) if avg is not None else None,
            "recommendations": rec}


# ---------------------------------------------------------------- reference & background checks
def update_check(chk: ReferenceCheck, user, status, notes=""):
    if status not in dict(ReferenceCheck.STATUS):
        raise BusinessRuleError("Unknown status.")
    if status != "pending" and not chk.consent_obtained:
        raise BusinessRuleError("Record the candidate's consent before carrying out this verification.")
    if status in ("verified", "concerns", "failed") and not (notes or chk.outcome_notes):
        raise BusinessRuleError("Record the outcome of the verification.")
    chk.status = status
    if notes:
        chk.outcome_notes = notes
    if status in ("verified", "concerns", "failed"):
        chk.completed_at, chk.checked_by = timezone.now(), user
    chk.save()
    _advance_to(chk.application, "reference_check", user, "Verification started")
    return chk


# ---------------------------------------------------------------- offers
OPEN_OFFER = ["draft", "pending", "approved", "returned", "sent", "negotiating"]


def _requisition_of(app):
    return app.vacancy.requisition


def offer_warnings(offer: Offer):
    w = []
    req = _requisition_of(offer.application)
    if req and req.salary_max and offer.basic_salary > req.salary_max:
        w.append(f"Basic salary exceeds the approved budget ceiling of GHS {req.salary_max:,.2f}.")
    if offer.grade_step_id and offer.basic_salary != offer.grade_step.basic_salary:
        w.append(f"Salary differs from grade step {offer.grade_step} (GHS {offer.grade_step.basic_salary:,.2f}).")
    pending = offer.application.checks.exclude(status__in=["verified", "concerns"])
    if pending.exists():
        w.append(f"{pending.count()} reference/background check(s) not yet verified.")
    if offer.application.checks.filter(status__in=["concerns", "failed"]).exists():
        w.append("A verification returned concerns or failed.")
    return w


@transaction.atomic
def create_offer(app: Application, data: dict, user) -> Offer:
    if app.stage not in ("interview", "assessment", "reference_check", "offer"):
        raise BusinessRuleError("Interview the candidate before making an offer.")
    if data["start_date"] < dt.date.today():
        raise BusinessRuleError("The start date cannot be in the past.")
    if data["expiry_date"] < dt.date.today():
        raise BusinessRuleError("The response deadline cannot be in the past.")
    if q(data.get("basic_salary") or 0) <= 0:
        raise BusinessRuleError("Enter the offered basic salary.")
    prev = app.offers.filter(status__in=OPEN_OFFER + ["declined"]).order_by("-revision").first()
    if prev and prev.status in ("pending", "approved", "sent") and not data.pop("revise", False):
        raise BusinessRuleError("This candidate already has an open offer. Create a revision instead.")
    data.pop("revise", None)
    req = _requisition_of(app)
    data.setdefault("position", req.position if req else None)
    data.setdefault("grade", req.grade if req else None)
    data.setdefault("employment_type", req.employment_type if req else app.vacancy.employment_type)
    if not data.get("supervisor") and req and req.requested_by_id:
        data["supervisor"] = req.requested_by
    offer = Offer.objects.create(application=app, revision=(prev.revision + 1) if prev else 1,
                                 reference=prev.reference if prev else next_number(
                                     "offer", default_prefix="OFF", default_pattern="{prefix}-{year}-{seq:04d}"),
                                 **data)
    if prev and prev.status in OPEN_OFFER:
        prev.status = "superseded"
        prev.save(update_fields=["status", "updated_at"])
        inst = _instance(prev)
        if inst and inst.status in ("pending", "returned"):
            from apps.workflow import engine

            engine.cancel(inst, user, "Superseded by a revised offer")
    _advance_to(app, "offer", user, f"Offer {offer.reference} rev {offer.revision} drafted")
    return offer


@transaction.atomic
def submit_offer(offer: Offer, user):
    from apps.workflow import engine

    if offer.status not in ("draft", "returned"):
        raise BusinessRuleError("Only draft or returned offers can be submitted.")
    req = _requisition_of(offer.application)
    above = bool(req and req.salary_max and offer.basic_salary > req.salary_max)
    resubmit = offer.status == "returned"
    offer.status = "pending"
    offer.save(update_fields=["status", "updated_at"])
    if resubmit:
        inst = _instance(offer)
        if inst and inst.status == "returned":
            engine.resubmit(inst, user)
            return offer
    engine.start(offer, "job_offer", user, subject_employee=req.requested_by if req else None,
                 extra_context={"amount": float(offer.basic_salary), "above_budget": above,
                                "department": offer.department.code})
    return offer


def offer_letter_pdf(offer: Offer) -> bytes:
    from apps.core.pdf import letter_pdf
    from apps.documents.models import LetterTemplate

    tpl = LetterTemplate.objects.filter(code="offer_letter", is_active=True).first()
    if tpl is None:
        raise BusinessRuleError("No 'offer_letter' template is configured. Add one under Letter templates.")
    org = get_current_org() or offer.organization
    ctx = {"candidate": offer.application.candidate, "offer": offer, "organization": org, "today": dt.date.today(),
           "reference": f"{offer.reference}/R{offer.revision}", "allowances": offer.allowances,
           "total_monthly": offer.basic_salary + offer.monthly_allowances,
           "probation_end": offer.start_date + dt.timedelta(days=30 * offer.probation_months)
           if offer.probation_months else None}
    return letter_pdf(tpl.body_html, ctx)


@transaction.atomic
def send_offer(offer: Offer, user):
    if offer.status != "approved":
        raise BusinessRuleError("The offer must be approved before it is sent.")
    if offer.expiry_date < dt.date.today():
        raise BusinessRuleError("Update the response deadline before sending.")
    pdf = offer_letter_pdf(offer)
    offer.letter.save(f"offer-{offer.reference}-r{offer.revision}.pdf", ContentFile(pdf), save=False)
    offer.token = secrets.token_urlsafe(32)
    offer.status, offer.sent_at = "sent", timezone.now()
    offer.save()
    link = f"{settings.FRONTEND_URL}/offer/{offer.token}"
    message_candidate(offer.application, "offer", {"offer": offer, "link": link})
    audit.log("update", offer, {"action": "offer_sent", "revision": offer.revision})
    return offer


def offer_by_token(token: str) -> Offer:
    offer = (Offer.all_objects.select_related("application__candidate", "application__vacancy", "job_title",
                                              "department", "organization")
             .filter(token=token).exclude(token="").first())
    if offer is None:
        raise NotFound("This offer link is invalid or has been replaced.")
    return offer


@transaction.atomic
def respond_offer(offer: Offer, decision: str, typed_name="", note="", ip=None):
    from apps.notifications.services import notify

    if offer.status not in ("sent", "negotiating"):
        raise BusinessRuleError("This offer is no longer open for a response.")
    if offer.expiry_date < dt.date.today():
        raise BusinessRuleError("This offer has expired. Please contact the recruitment team.")
    cand = offer.application.candidate
    app = offer.application
    if decision == "accept":
        if " ".join(typed_name.lower().split()) != " ".join(cand.full_name.lower().split()):
            raise BusinessRuleError(f"Type your full name exactly as shown ({cand.full_name}) to accept.")
        offer.status, offer.accepted_name, offer.accepted_ip = "accepted", typed_name.strip(), ip
    elif decision == "decline":
        offer.status = "declined"
    elif decision == "negotiate":
        if not note.strip():
            raise BusinessRuleError("Tell us what you would like to discuss.")
        offer.status = "negotiating"
    else:
        raise BusinessRuleError("Unknown response.")
    offer.responded_at, offer.response_note = timezone.now(), note
    offer.save()
    ApplicationEvent.objects.create(application=app, kind="note",
                                    note=f"Candidate {offer.get_status_display().lower()} offer rev {offer.revision}"
                                         f"{': ' + note if note else ''}")
    if decision == "decline":
        app.stage, app.rejection_reason, app.stage_changed_at = "withdrawn", "Declined offer", timezone.now()
        app.save(update_fields=["stage", "rejection_reason", "stage_changed_at", "updated_at"])
        ApplicationEvent.objects.create(application=app, from_stage="offer", to_stage="withdrawn",
                                        note="Declined offer")
    if decision == "accept":
        message_candidate(app, "offer_accepted", {"offer": offer}, sms=False)
    recruiter = app.vacancy.recruiter
    if recruiter:
        notify("generic", [recruiter], {"title": f"Offer {offer.get_status_display().lower()}: {cand.full_name}",
                                        "body": f"{cand.full_name} responded to offer {offer.reference} for "
                                                f"{app.vacancy.title}. {note}",
                                        "link": f"/recruitment/applications/{app.id}"})
    audit.log("update", offer, {"action": f"candidate_{decision}", "ip": ip})
    return offer


def withdraw_offer(offer: Offer, user, reason):
    if offer.status not in ("draft", "pending", "approved", "returned", "sent", "negotiating"):
        raise BusinessRuleError("This offer can no longer be withdrawn.")
    if not reason:
        raise BusinessRuleError("Give a reason for withdrawing the offer.")
    inst = _instance(offer)
    if inst and inst.status in ("pending", "returned"):
        from apps.workflow import engine

        engine.cancel(inst, user, reason)
    offer.status, offer.response_note = "withdrawn", reason
    offer.save(update_fields=["status", "response_note", "updated_at"])
    return offer


def expire_offers(today=None):
    today = today or dt.date.today()
    return Offer.objects.filter(status__in=["sent", "negotiating"], expiry_date__lt=today).update(status="expired")


# ---------------------------------------------------------------- hire
@transaction.atomic
def hire_from_offer(offer: Offer, user, extra=None):
    """Create the employee from an accepted offer (effective-dated hire record) and start onboarding."""
    from apps.documents.models import Document, DocumentCategory
    from apps.documents.services import add_version
    from apps.employees.services import hire

    if offer.status != "accepted":
        raise BusinessRuleError("Only accepted offers can be converted to an employee.")
    app, cand = offer.application, offer.application.candidate
    if app.hired_employee_id:
        raise BusinessRuleError("This candidate has already been hired.")
    extra = dict(extra or {})
    data = {
        "first_name": cand.first_name, "last_name": cand.last_name, "personal_email": cand.email,
        "phone": cand.phone, "gender": cand.gender if cand.gender in ("male", "female") else "",
        "hire_date": offer.start_date, "job_title": offer.job_title, "department": offer.department,
        "grade": offer.grade, "grade_step": offer.grade_step, "basic_salary": offer.basic_salary,
        "employment_type": offer.employment_type, "supervisor": offer.supervisor,
        "probation_end_date": offer.start_date + dt.timedelta(days=30 * offer.probation_months)
        if offer.probation_months else None,
        "contract_end_date": offer.contract_end_date, "reason": f"Appointment via {app.reference}",
    }
    if offer.position_id:
        data["position"] = offer.position
    allow_dup = bool(extra.pop("allow_duplicate", False))
    data.update({k: v for k, v in extra.items() if v not in (None, "")})
    if cand.employee_id:
        raise BusinessRuleError("Internal candidates move through a transfer or promotion, not a new hire.",
                                code="internal_candidate")
    emp = hire(data, user=user, allow_duplicate=allow_dup)
    app.hired_employee, app.stage, app.stage_changed_at = emp, "hired", timezone.now()
    app.save(update_fields=["hired_employee", "stage", "stage_changed_at", "updated_at"])
    ApplicationEvent.objects.create(application=app, from_stage="offer", to_stage="hired", actor=user,
                                    note=f"Hired as {emp.staff_number}")
    cand.talent_pool = False
    cand.save(update_fields=["talent_pool", "updated_at"])
    # personnel file: CV and signed offer letter
    for code, title, fobj, fname in (("cv", "CV / application", app.cv, app.cv_name),
                                     ("appointment", f"Offer letter {offer.reference}", offer.letter,
                                      f"offer-{offer.reference}.pdf")):
        if fobj:
            cat = DocumentCategory.objects.filter(code=code).first() or DocumentCategory.objects.get(code="other")
            doc = Document.objects.create(employee=emp, category=cat, title=title,
                                          confidentiality=cat.default_confidentiality,
                                          issue_date=dt.date.today(), visible_to_employee=True)
            f = ContentFile(fobj.open("rb").read(), name=fname or "file.pdf")
            add_version(doc, f, note="From recruitment")
    # requisition and vacancy fill status
    v = app.vacancy
    req = v.requisition
    if req:
        req.filled_count += 1
        if req.filled_count >= req.headcount:
            req.status = "filled"
        req.save(update_fields=["filled_count", "status", "updated_at"])
    if v.applications.filter(stage="hired").count() >= v.openings:
        close_vacancy(v, "filled")
    from apps.onboarding import services as onboarding

    onboarding.link_offer(emp, offer)
    return emp


# ---------------------------------------------------------------- talent pool & data protection
def anonymise(cand: Candidate):
    for app in cand.applications.all():
        if app.cv:
            app.cv.delete(save=False)
        app.cv_name, app.cover_letter, app.answers, app.screening_notes = "", "", {}, ""
        app.save()
    cand.first_name, cand.last_name = "Anonymised", f"candidate {cand.pk}"
    cand.email = f"anon-{cand.pk}@redacted.invalid"
    for f in ("phone", "location", "current_employer", "current_title", "linkedin", "notes", "field_of_study"):
        setattr(cand, f, "")
    cand.tags, cand.talent_pool, cand.anonymised = [], False, True
    cand.save()
    audit.log("update", cand, {"action": "anonymised"})


def purge_expired_candidates(today=None):
    today = today or dt.date.today()
    qs = (Candidate.objects.filter(anonymised=False, retain_until__lt=today, employee__isnull=True)
          .exclude(applications__stage__in=Application.ACTIVE_STAGES + ["hired"]))
    n = 0
    for cand in qs.distinct():
        anonymise(cand)
        n += 1
    return n


# ---------------------------------------------------------------- analytics
def analytics(date_from=None, date_to=None, department=None):
    apps_qs = Application.objects.all()
    vac_qs = Vacancy.objects.all()
    if date_from:
        apps_qs = apps_qs.filter(applied_at__date__gte=date_from)
    if date_to:
        apps_qs = apps_qs.filter(applied_at__date__lte=date_to)
    if department:
        apps_qs = apps_qs.filter(vacancy__department_id=department)
        vac_qs = vac_qs.filter(department_id=department)
    today = timezone.now()
    # funnel: furthest stage reached (from the stage history)
    pipeline = STAGE_ORDER[:8]
    reached = dict.fromkeys(pipeline, 0)
    events = ApplicationEvent.objects.filter(application__in=apps_qs, kind="stage").values_list("application_id",
                                                                                                "to_stage")
    best: dict[int, int] = {}
    for app_id, stage in events:
        if stage in pipeline:
            best[app_id] = max(best.get(app_id, 0), pipeline.index(stage))
    for app_id, stage in apps_qs.values_list("id", "stage"):
        idx = max(best.get(app_id, 0), pipeline.index(stage) if stage in pipeline else 0)
        for s in pipeline[: idx + 1]:
            reached[s] += 1
    hired = apps_qs.filter(stage="hired")
    tth = []
    for a in hired.prefetch_related("events"):
        ev = next((e for e in a.events.all() if e.to_stage == "hired"), None)
        if ev:
            tth.append((ev.created_at - a.applied_at).days)
    fills = []
    for req in Requisition.objects.filter(approved_at__isnull=False, vacancies__applications__in=hired).distinct():
        firsts = ApplicationEvent.objects.filter(application__vacancy__requisition=req, to_stage="hired") \
            .order_by("created_at").first()
        if firsts:
            fills.append((firsts.created_at - req.approved_at).days)
    open_v = vac_qs.filter(status="published")
    ages = [(today - v.published_at).days for v in open_v if v.published_at]
    offers = Offer.objects.filter(application__in=apps_qs)
    decided = offers.filter(status__in=["accepted", "declined"])
    cost = vac_qs.filter(applications__stage="hired").distinct().aggregate(s=Sum("advertising_cost"))["s"] or 0
    n_hired = hired.count()
    sources = (apps_qs.values("candidate__source").annotate(applications=Count("id"),
                                                            hires=Count("id", filter=Q(stage="hired")))
               .order_by("-applications"))
    src_labels = dict(Candidate.SOURCES)
    return {
        "open_vacancies": open_v.count(),
        "applications": apps_qs.count(),
        "active_applications": apps_qs.filter(stage__in=Application.ACTIVE_STAGES).count(),
        "hires": n_hired,
        "pending_requisitions": Requisition.objects.filter(status="pending").count(),
        "avg_time_to_hire_days": round(sum(tth) / len(tth), 1) if tth else None,
        "avg_time_to_fill_days": round(sum(fills) / len(fills), 1) if fills else None,
        "avg_vacancy_age_days": round(sum(ages) / len(ages), 1) if ages else None,
        "offer_acceptance_percent": round(100 * decided.filter(status="accepted").count() / decided.count(), 1)
        if decided.exists() else None,
        "cost_per_hire": q(Decimal(cost) / n_hired) if n_hired else None,
        "funnel": [{"stage": dict(Application.STAGES)[s], "count": reached[s]} for s in pipeline],
        "sources": [{"source": src_labels.get(r["candidate__source"], r["candidate__source"]),
                     "applications": r["applications"], "hires": r["hires"]} for r in sources],
        "vacancy_ageing": [{"id": v.id, "reference": v.reference, "title": v.title,
                            "days_open": (today - v.published_at).days if v.published_at else 0,
                            "applications": v.applications.count(),
                            "closing_date": v.closing_date} for v in open_v.order_by("published_at")[:20]],
    }
