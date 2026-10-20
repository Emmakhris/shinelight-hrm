import os
import secrets
from decimal import Decimal

from django.conf import settings
from django.db import models

from apps.core.models import TenantModel
from apps.organization.models import Position

MONEY = {"max_digits": 14, "decimal_places": 2, "default": Decimal("0")}
QUALIFICATIONS = [
    ("none", "No formal qualification"), ("basic", "BECE / basic"), ("secondary", "WASSCE / SSSCE"),
    ("certificate", "Certificate"), ("diploma", "Diploma / HND"), ("degree", "Bachelor's degree"),
    ("masters", "Master's degree"), ("doctorate", "Doctorate"), ("professional", "Professional (ACCA, ICAG, etc.)"),
]
QUALIFICATION_RANK = {code: i for i, (code, _) in enumerate(QUALIFICATIONS)}
QUALIFICATION_RANK["professional"] = QUALIFICATION_RANK["degree"]
DEFAULT_CRITERIA = [
    {"name": "Technical knowledge", "weight": 30}, {"name": "Relevant experience", "weight": 25},
    {"name": "Communication", "weight": 15}, {"name": "Problem solving", "weight": 15},
    {"name": "Culture and values fit", "weight": 15},
]


class Requisition(TenantModel):
    """Manpower request raised by a manager and approved by HOD, HR and finance."""

    REASONS = [("new", "New position"), ("replacement", "Replacement"), ("expansion", "Additional headcount"),
               ("temporary", "Temporary cover")]
    STATUS = [("draft", "Draft"), ("pending", "Pending approval"), ("approved", "Approved"), ("rejected", "Rejected"),
              ("returned", "Returned"), ("cancelled", "Cancelled"), ("filled", "Filled"), ("closed", "Closed")]
    reference = models.CharField(max_length=30, blank=True)
    position = models.ForeignKey(Position, null=True, blank=True, on_delete=models.SET_NULL, related_name="requisitions")
    job_title = models.ForeignKey("organization.JobTitle", on_delete=models.PROTECT, related_name="+")
    department = models.ForeignKey("organization.Department", on_delete=models.PROTECT, related_name="requisitions")
    location = models.ForeignKey("organization.Location", null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name="+")
    grade = models.ForeignKey("organization.Grade", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    employment_type = models.CharField(max_length=20, choices=Position.EMPLOYMENT_TYPES, default="permanent")
    headcount = models.PositiveSmallIntegerField(default=1)
    reason = models.CharField(max_length=15, choices=REASONS, default="replacement")
    replacing = models.ForeignKey("employees.Employee", null=True, blank=True, on_delete=models.SET_NULL,
                                  related_name="+")
    justification = models.TextField()
    salary_min = models.DecimalField(**MONEY)
    salary_max = models.DecimalField(**MONEY, help_text="Monthly basic budget ceiling.")
    target_start_date = models.DateField(null=True, blank=True)
    requested_by = models.ForeignKey("employees.Employee", null=True, blank=True, on_delete=models.SET_NULL,
                                     related_name="requisitions_raised")
    status = models.CharField(max_length=12, choices=STATUS, default="draft", db_index=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    filled_count = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.reference or 'Requisition'} {self.job_title.name}"

    @property
    def annual_budget(self):
        return self.salary_max * 12 * self.headcount


class Vacancy(TenantModel):
    VISIBILITY = [("internal", "Internal only"), ("external", "External only"), ("both", "Internal and external")]
    STATUS = [("draft", "Draft"), ("published", "Published"), ("closed", "Closed to applications"),
              ("filled", "Filled"), ("cancelled", "Cancelled")]
    reference = models.CharField(max_length=30, blank=True)
    requisition = models.ForeignKey(Requisition, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="vacancies")
    title = models.CharField(max_length=200)
    department = models.ForeignKey("organization.Department", on_delete=models.PROTECT, related_name="vacancies")
    location = models.ForeignKey("organization.Location", null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name="+")
    employment_type = models.CharField(max_length=20, choices=Position.EMPLOYMENT_TYPES, default="permanent")
    openings = models.PositiveSmallIntegerField(default=1)
    summary = models.TextField(blank=True)
    responsibilities = models.TextField(blank=True)
    requirements = models.TextField(blank=True)
    salary_display = models.CharField(max_length=100, blank=True, help_text="Shown to applicants, e.g. 'Competitive'.")
    min_qualification = models.CharField(max_length=15, choices=QUALIFICATIONS, default="none")
    min_experience_years = models.PositiveSmallIntegerField(default=0)
    # [{"key": "license", "question": "Do you hold a valid licence?", "type": "yes_no", "knockout": "no"}]
    screening_questions = models.JSONField(default=list, blank=True)
    scorecard_criteria = models.JSONField(default=list, blank=True)
    visibility = models.CharField(max_length=10, choices=VISIBILITY, default="both")
    channels = models.JSONField(default=list, blank=True, help_text="Where it was advertised (career site, Daily "
                                                                    "Graphic, LinkedIn, Jobberman...).")
    advertising_cost = models.DecimalField(**MONEY)
    closing_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS, default="draft", db_index=True)
    published_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    recruiter = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                  related_name="+")

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "vacancies"

    def __str__(self):
        return f"{self.reference or 'Vacancy'} {self.title}"

    @property
    def criteria(self):
        return self.scorecard_criteria or DEFAULT_CRITERIA


class Candidate(TenantModel):
    """A person in the talent database. One record per email address, reused across applications."""

    SOURCES = [("career_site", "Career site"), ("internal", "Internal employee"), ("referral", "Staff referral"),
               ("agency", "Recruitment agency"), ("job_board", "Job board"), ("newspaper", "Newspaper"),
               ("walk_in", "Walk-in / unsolicited"), ("other", "Other")]
    first_name = models.CharField(max_length=80)
    last_name = models.CharField(max_length=80)
    email = models.EmailField()
    phone = models.CharField(max_length=20, blank=True)
    gender = models.CharField(max_length=10, blank=True)
    location = models.CharField(max_length=100, blank=True)
    highest_qualification = models.CharField(max_length=15, choices=QUALIFICATIONS, default="none")
    field_of_study = models.CharField(max_length=120, blank=True)
    years_experience = models.DecimalField(max_digits=4, decimal_places=1, default=Decimal("0"))
    current_employer = models.CharField(max_length=150, blank=True)
    current_title = models.CharField(max_length=150, blank=True)
    linkedin = models.URLField(blank=True)
    source = models.CharField(max_length=15, choices=SOURCES, default="career_site")
    employee = models.ForeignKey("employees.Employee", null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name="candidate_profiles")
    consent_given_at = models.DateTimeField(null=True, blank=True)
    talent_pool = models.BooleanField(default=False, help_text="Candidate agreed to be considered for future roles.")
    retain_until = models.DateField(null=True, blank=True, help_text="Personal data is anonymised after this date.")
    anonymised = models.BooleanField(default=False)
    tags = models.JSONField(default=list, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["last_name", "first_name"]
        constraints = [models.UniqueConstraint(fields=["organization", "email"], name="uniq_candidate_email")]

    def __str__(self):
        return self.full_name

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()


def _cv_path(instance, filename):
    return (f"recruitment/{instance.organization_id}/{instance.candidate_id}/"
            f"{secrets.token_hex(8)}{os.path.splitext(filename)[1].lower()}")


class Application(TenantModel):
    STAGES = [("applied", "Applied"), ("screening", "Screening"), ("shortlisted", "Shortlisted"),
              ("interview", "Interview"), ("assessment", "Assessment"), ("reference_check", "Reference checks"),
              ("offer", "Offer"), ("hired", "Hired"), ("rejected", "Unsuccessful"), ("withdrawn", "Withdrawn")]
    ACTIVE_STAGES = ["applied", "screening", "shortlisted", "interview", "assessment", "reference_check", "offer"]
    reference = models.CharField(max_length=30, blank=True)
    vacancy = models.ForeignKey(Vacancy, on_delete=models.CASCADE, related_name="applications")
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name="applications")
    stage = models.CharField(max_length=16, choices=STAGES, default="applied", db_index=True)
    cv = models.FileField(upload_to=_cv_path, max_length=255, blank=True)
    cv_name = models.CharField(max_length=255, blank=True)
    cover_letter = models.TextField(blank=True)
    answers = models.JSONField(default=dict, blank=True)
    screening_score = models.PositiveSmallIntegerField(default=0)
    screening_flags = models.JSONField(default=list, blank=True)
    knocked_out = models.BooleanField(default=False, help_text="Failed a knockout question (for recruiter review).")
    screening_notes = models.TextField(blank=True)
    rating = models.PositiveSmallIntegerField(null=True, blank=True)
    referred_by = models.ForeignKey("employees.Employee", null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="+")
    rejection_reason = models.CharField(max_length=255, blank=True)
    applied_at = models.DateTimeField(auto_now_add=True)
    stage_changed_at = models.DateTimeField(null=True, blank=True)
    hired_employee = models.ForeignKey("employees.Employee", null=True, blank=True, on_delete=models.SET_NULL,
                                       related_name="+")

    class Meta:
        ordering = ["-applied_at"]
        constraints = [models.UniqueConstraint(fields=["vacancy", "candidate"], name="uniq_application")]

    def __str__(self):
        return f"{self.reference or 'Application'} {self.candidate.full_name}"


class ApplicationEvent(TenantModel):
    """Stage history and communications log (powers time-in-stage analytics)."""

    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="events")
    kind = models.CharField(max_length=15, choices=[("stage", "Stage change"), ("message", "Message sent"),
                                                    ("note", "Note")], default="stage")
    from_stage = models.CharField(max_length=16, blank=True)
    to_stage = models.CharField(max_length=16, blank=True)
    note = models.TextField(blank=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                              related_name="+")

    class Meta:
        ordering = ["created_at", "id"]


class Interview(TenantModel):
    MODES = [("in_person", "In person"), ("phone", "Phone"), ("video", "Video call")]
    STATUS = [("scheduled", "Scheduled"), ("completed", "Completed"), ("cancelled", "Cancelled"),
              ("no_show", "Candidate did not attend")]
    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="interviews")
    round_name = models.CharField(max_length=100, default="Panel interview")
    scheduled_at = models.DateTimeField()
    duration_minutes = models.PositiveSmallIntegerField(default=45)
    mode = models.CharField(max_length=10, choices=MODES, default="in_person")
    venue = models.CharField(max_length=255, blank=True, help_text="Room, address or meeting link.")
    panel = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name="interview_panels", blank=True)
    status = models.CharField(max_length=10, choices=STATUS, default="scheduled")
    candidate_notified = models.BooleanField(default=False)

    class Meta:
        ordering = ["scheduled_at"]

    def __str__(self):
        return f"{self.round_name} - {self.application.candidate.full_name}"


class Scorecard(TenantModel):
    RECOMMENDATIONS = [("strong_yes", "Strongly recommend"), ("yes", "Recommend"), ("no", "Do not recommend"),
                       ("strong_no", "Strongly against")]
    interview = models.ForeignKey(Interview, on_delete=models.CASCADE, related_name="scorecards")
    panelist = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    ratings = models.JSONField(default=dict, help_text="{criterion: 1-5}")
    overall_score = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"),
                                        help_text="Weighted score out of 100.")
    recommendation = models.CharField(max_length=12, choices=RECOMMENDATIONS)
    strengths = models.TextField(blank=True)
    concerns = models.TextField(blank=True)
    conflict_of_interest = models.BooleanField(default=False)
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["interview", "panelist"], name="uniq_scorecard")]


class ReferenceCheck(TenantModel):
    TYPES = [("reference", "Employment reference"), ("academic", "Academic verification"),
             ("professional", "Professional licence"), ("police", "Police / criminal record"),
             ("medical", "Pre-employment medical"), ("identity", "Ghana Card / identity")]
    STATUS = [("pending", "Pending"), ("in_progress", "In progress"), ("verified", "Verified"),
              ("concerns", "Verified with concerns"), ("failed", "Failed / could not verify")]
    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="checks")
    check_type = models.CharField(max_length=15, choices=TYPES, default="reference")
    referee_name = models.CharField(max_length=150, blank=True)
    referee_organization = models.CharField(max_length=150, blank=True)
    referee_relationship = models.CharField(max_length=100, blank=True)
    referee_contact = models.CharField(max_length=150, blank=True)
    consent_obtained = models.BooleanField(default=False, help_text="Candidate authorised this verification.")
    status = models.CharField(max_length=12, choices=STATUS, default="pending")
    outcome_notes = models.TextField(blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    checked_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")

    class Meta:
        ordering = ["created_at"]


def _offer_path(instance, filename):
    return f"recruitment/{instance.organization_id}/offers/{instance.pk or 'new'}-{secrets.token_hex(6)}.pdf"


class Offer(TenantModel):
    STATUS = [("draft", "Draft"), ("pending", "Pending approval"), ("approved", "Approved"), ("rejected", "Rejected"),
              ("returned", "Returned"), ("sent", "Sent to candidate"), ("accepted", "Accepted"),
              ("declined", "Declined"), ("negotiating", "Candidate negotiating"), ("withdrawn", "Withdrawn"),
              ("expired", "Expired"), ("superseded", "Superseded by revision"), ("cancelled", "Cancelled")]
    reference = models.CharField(max_length=30, blank=True)
    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="offers")
    revision = models.PositiveSmallIntegerField(default=1)
    job_title = models.ForeignKey("organization.JobTitle", on_delete=models.PROTECT, related_name="+")
    department = models.ForeignKey("organization.Department", on_delete=models.PROTECT, related_name="+")
    position = models.ForeignKey(Position, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    grade = models.ForeignKey("organization.Grade", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    grade_step = models.ForeignKey("organization.GradeStep", null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    supervisor = models.ForeignKey("employees.Employee", null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    employment_type = models.CharField(max_length=20, choices=Position.EMPLOYMENT_TYPES, default="permanent")
    basic_salary = models.DecimalField(**MONEY)
    allowances = models.JSONField(default=list, blank=True, help_text='[{"name": "Transport", "amount": 300}]')
    start_date = models.DateField()
    probation_months = models.PositiveSmallIntegerField(default=6)
    contract_end_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(help_text="Candidate must respond by this date.")
    terms = models.TextField(blank=True, help_text="Additional terms shown in the letter.")
    status = models.CharField(max_length=12, choices=STATUS, default="draft", db_index=True)
    letter = models.FileField(upload_to=_offer_path, max_length=255, blank=True)
    token = models.CharField(max_length=64, blank=True, db_index=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    responded_at = models.DateTimeField(null=True, blank=True)
    response_note = models.TextField(blank=True)
    accepted_name = models.CharField(max_length=200, blank=True)
    accepted_ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.reference or 'Offer'} rev {self.revision} - {self.application.candidate.full_name}"

    @property
    def monthly_allowances(self):
        return sum((Decimal(str(a.get("amount") or 0)) for a in self.allowances or []), Decimal("0"))
