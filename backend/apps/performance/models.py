from decimal import Decimal

from django.conf import settings
from django.db import models

from apps.core.models import TenantModel

DEFAULT_LEVELS = [
    {"value": 5, "label": "Outstanding", "description": "Consistently far exceeds expectations."},
    {"value": 4, "label": "Exceeds expectations", "description": "Frequently exceeds expectations."},
    {"value": 3, "label": "Meets expectations", "description": "Fully meets the requirements of the role."},
    {"value": 2, "label": "Needs improvement", "description": "Meets some but not all expectations."},
    {"value": 1, "label": "Unsatisfactory", "description": "Does not meet expectations."},
]
SCORE = {"max_digits": 5, "decimal_places": 2, "null": True, "blank": True}


class RatingScale(TenantModel):
    """Configurable rating scale; levels are ordered values with labels (e.g. 1-5 or 1-4)."""

    name = models.CharField(max_length=100)
    levels = models.JSONField(default=list)
    is_default = models.BooleanField(default=False)

    def __str__(self):
        return self.name

    @property
    def values(self):
        return sorted(int(level["value"]) for level in self.levels)

    def label(self, value):
        if value is None:
            return None
        return next((lv["label"] for lv in self.levels if int(lv["value"]) == int(value)), str(value))


class Competency(TenantModel):
    CATEGORIES = [("core", "Core / values"), ("leadership", "Leadership"), ("technical", "Technical / functional"),
                  ("clinical", "Clinical")]
    name = models.CharField(max_length=120)
    category = models.CharField(max_length=12, choices=CATEGORIES, default="core")
    description = models.TextField(blank=True)
    behaviours = models.TextField(blank=True, help_text="Observable behaviours at the expected level.")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["category", "name"]
        verbose_name_plural = "competencies"

    def __str__(self):
        return self.name


class AppraisalTemplate(TenantModel):
    """Role-specific appraisal form. The most specific active template is applied to each employee."""

    name = models.CharField(max_length=150)
    rating_scale = models.ForeignKey(RatingScale, on_delete=models.PROTECT, related_name="+")
    job_family = models.ForeignKey("organization.JobFamily", null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    category = models.ForeignKey("employees.EmployeeCategory", null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name="+")
    clinical_only = models.BooleanField(default=False)
    objectives_weight = models.PositiveSmallIntegerField(default=70, help_text="% of the overall score.")
    competencies = models.ManyToManyField(Competency, blank=True, related_name="templates")
    min_objectives = models.PositiveSmallIntegerField(default=3)
    max_objectives = models.PositiveSmallIntegerField(default=8)
    include_360 = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def competencies_weight(self):
        return 100 - self.objectives_weight


class ReviewCycle(TenantModel):
    TYPES = [("annual", "Annual"), ("semiannual", "Half-year"), ("quarterly", "Quarterly")]
    STATUS = [("draft", "Draft"), ("goal_setting", "Objective setting"), ("in_progress", "In progress (mid-year)"),
              ("review", "Year-end review"), ("calibration", "Calibration"), ("closed", "Closed")]
    name = models.CharField(max_length=150)
    cycle_type = models.CharField(max_length=12, choices=TYPES, default="annual")
    period_start = models.DateField()
    period_end = models.DateField()
    goal_setting_deadline = models.DateField(null=True, blank=True)
    midyear_date = models.DateField(null=True, blank=True)
    self_review_deadline = models.DateField(null=True, blank=True)
    manager_review_deadline = models.DateField(null=True, blank=True)
    min_service_days = models.PositiveSmallIntegerField(default=90, help_text="Exclude staff hired too recently.")
    include_probation = models.BooleanField(default=False)
    departments = models.ManyToManyField("organization.Department", blank=True, related_name="+")
    use_calibration = models.BooleanField(default=True)
    target_distribution = models.JSONField(default=dict, blank=True,
                                           help_text='Guide only, e.g. {"5": 10, "4": 20, "3": 50, "2": 15, "1": 5}')
    status = models.CharField(max_length=12, choices=STATUS, default="draft", db_index=True)
    launched_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-period_start"]

    def __str__(self):
        return self.name


class Goal(TenantModel):
    """Organization or department goal that individual objectives cascade from."""

    cycle = models.ForeignKey(ReviewCycle, on_delete=models.CASCADE, related_name="goals")
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="children")
    department = models.ForeignKey("organization.Department", null=True, blank=True, on_delete=models.CASCADE,
                                   related_name="+", help_text="Blank = organization-wide goal.")
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    measure = models.CharField(max_length=255, blank=True)
    target = models.CharField(max_length=120, blank=True)
    owner = models.ForeignKey("employees.Employee", null=True, blank=True, on_delete=models.SET_NULL,
                              related_name="+")

    class Meta:
        ordering = ["department_id", "title"]

    def __str__(self):
        return self.title


class Appraisal(TenantModel):
    STATUS = [("objective_setting", "Setting objectives"), ("objectives_pending", "Objectives awaiting approval"),
              ("objectives_returned", "Objectives returned"), ("objectives_agreed", "Objectives agreed"),
              ("self_review", "Self-assessment"), ("manager_review", "Manager review"),
              ("calibration", "Calibration"), ("acknowledgement", "Awaiting employee acknowledgment"),
              ("completed", "Completed"), ("cancelled", "Cancelled")]
    cycle = models.ForeignKey(ReviewCycle, on_delete=models.CASCADE, related_name="appraisals")
    employee = models.ForeignKey("employees.Employee", on_delete=models.CASCADE, related_name="appraisals")
    template = models.ForeignKey(AppraisalTemplate, on_delete=models.PROTECT, related_name="+")
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name="+")
    status = models.CharField(max_length=20, choices=STATUS, default="objective_setting", db_index=True)
    objectives_score = models.DecimalField(**SCORE)
    competencies_score = models.DecimalField(**SCORE)
    overall_score = models.DecimalField(**SCORE)
    manager_rating = models.PositiveSmallIntegerField(null=True, blank=True, help_text="Rating before calibration.")
    final_rating = models.PositiveSmallIntegerField(null=True, blank=True)
    calibration_reason = models.TextField(blank=True)
    calibrated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                      related_name="+")
    midyear_comments = models.TextField(blank=True)
    midyear_done_at = models.DateTimeField(null=True, blank=True)
    self_comments = models.TextField(blank=True)
    manager_comments = models.TextField(blank=True)
    development_needs = models.TextField(blank=True, help_text="Training and development agreed for next period.")
    employee_comments = models.TextField(blank=True)
    employee_agrees = models.BooleanField(null=True, blank=True)
    self_submitted_at = models.DateTimeField(null=True, blank=True)
    manager_submitted_at = models.DateTimeField(null=True, blank=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-cycle__period_start", "employee__last_name"]
        constraints = [models.UniqueConstraint(fields=["cycle", "employee"], name="uniq_appraisal")]

    def __str__(self):
        return f"{self.cycle.name} - {self.employee.full_name}"


class Objective(TenantModel):
    PROGRESS = [("on_track", "On track"), ("at_risk", "At risk"), ("off_track", "Off track"), ("done", "Achieved")]
    appraisal = models.ForeignKey(Appraisal, on_delete=models.CASCADE, related_name="objectives")
    goal = models.ForeignKey(Goal, null=True, blank=True, on_delete=models.SET_NULL, related_name="objectives")
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    measure = models.CharField(max_length=255, blank=True, help_text="KPI / how success is measured.")
    target = models.CharField(max_length=120, blank=True)
    weight = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"))
    due_date = models.DateField(null=True, blank=True)
    midyear_status = models.CharField(max_length=10, choices=PROGRESS, blank=True)
    midyear_comment = models.TextField(blank=True)
    achievement = models.TextField(blank=True, help_text="Result achieved (employee).")
    self_rating = models.PositiveSmallIntegerField(null=True, blank=True)
    manager_rating = models.PositiveSmallIntegerField(null=True, blank=True)
    manager_comment = models.TextField(blank=True)

    class Meta:
        ordering = ["id"]


class CompetencyRating(TenantModel):
    appraisal = models.ForeignKey(Appraisal, on_delete=models.CASCADE, related_name="competency_ratings")
    competency = models.ForeignKey(Competency, on_delete=models.PROTECT, related_name="+")
    self_rating = models.PositiveSmallIntegerField(null=True, blank=True)
    manager_rating = models.PositiveSmallIntegerField(null=True, blank=True)
    comment = models.TextField(blank=True)

    class Meta:
        ordering = ["competency__category", "competency__name"]
        constraints = [models.UniqueConstraint(fields=["appraisal", "competency"], name="uniq_competency_rating")]


class FeedbackRequest(TenantModel):
    """360 feedback. Responses are only ever shown aggregated, and only once enough have been received."""

    RELATIONSHIPS = [("peer", "Peer"), ("direct_report", "Direct report"), ("internal_customer", "Internal customer"),
                     ("other", "Other")]
    STATUS = [("pending", "Pending"), ("submitted", "Submitted"), ("declined", "Declined")]
    appraisal = models.ForeignKey(Appraisal, on_delete=models.CASCADE, related_name="feedback_requests")
    respondent = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    relationship = models.CharField(max_length=20, choices=RELATIONSHIPS, default="peer")
    status = models.CharField(max_length=10, choices=STATUS, default="pending")
    ratings = models.JSONField(default=dict, blank=True, help_text="{competency_id: rating}")
    strengths = models.TextField(blank=True)
    improvements = models.TextField(blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["appraisal", "respondent"], name="uniq_feedback_request")]


class ImprovementPlan(TenantModel):
    STATUS = [("draft", "Draft"), ("pending", "Pending HR approval"), ("returned", "Returned"),
              ("rejected", "Not approved"), ("active", "Active"), ("extended", "Extended"),
              ("successful", "Completed successfully"), ("unsuccessful", "Not successful"),
              ("cancelled", "Cancelled")]
    employee = models.ForeignKey("employees.Employee", on_delete=models.CASCADE, related_name="improvement_plans")
    appraisal = models.ForeignKey(Appraisal, null=True, blank=True, on_delete=models.SET_NULL, related_name="pips")
    supervisor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    reason = models.TextField(help_text="Performance gaps, with evidence.")
    support = models.TextField(blank=True, help_text="Training, coaching and resources provided.")
    start_date = models.DateField()
    end_date = models.DateField()
    review_frequency_days = models.PositiveSmallIntegerField(default=14)
    status = models.CharField(max_length=12, choices=STATUS, default="draft", db_index=True)
    outcome_notes = models.TextField(blank=True)
    employee_acknowledged_at = models.DateTimeField(null=True, blank=True)
    employee_comments = models.TextField(blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-start_date"]

    def __str__(self):
        return f"PIP {self.employee.full_name} ({self.start_date:%d/%m/%Y})"


class PlanMilestone(TenantModel):
    STATUS = [("pending", "Pending"), ("met", "Met"), ("partly_met", "Partly met"), ("not_met", "Not met")]
    plan = models.ForeignKey(ImprovementPlan, on_delete=models.CASCADE, related_name="milestones")
    objective = models.CharField(max_length=255)
    measure = models.CharField(max_length=255, blank=True)
    due_date = models.DateField()
    status = models.CharField(max_length=10, choices=STATUS, default="pending")
    review_notes = models.TextField(blank=True)

    class Meta:
        ordering = ["due_date", "id"]
