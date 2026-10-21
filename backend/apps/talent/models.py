from decimal import Decimal

from django.conf import settings
from django.db import models

from apps.core.models import TenantModel

MONEY = {"max_digits": 14, "decimal_places": 2, "default": Decimal("0")}
# transparent potential criteria: each is a documented yes/no judgement with evidence, never a hidden score
POTENTIAL_CRITERIA = [
    ("learning_agility", "Learns new roles and skills quickly"),
    ("leadership", "Shows leadership beyond the current role"),
    ("aspiration", "Has expressed an aspiration to grow"),
    ("judgement", "Sound judgement in complex or unfamiliar situations"),
    ("mobility", "Open to moving role, unit or location"),
]


class TalentProfile(TenantModel):
    """Employee-owned career profile: aspirations, skills and mobility preferences."""

    employee = models.OneToOneField("employees.Employee", on_delete=models.CASCADE, related_name="talent_profile")
    aspirations = models.TextField(blank=True, help_text="Where would you like your career to go?")
    preferred_roles = models.ManyToManyField("organization.JobTitle", blank=True, related_name="+")
    skills = models.JSONField(default=list, blank=True, help_text='["Phlebotomy", "Excel", "Team leadership"]')
    languages = models.JSONField(default=list, blank=True)
    willing_to_relocate = models.BooleanField(default=False)
    open_to_lateral_moves = models.BooleanField(default=True)
    updated_by_employee_at = models.DateTimeField(null=True, blank=True)


class TalentAssessment(TenantModel):
    """Nine-box placement with documented reasons. Performance is suggested from the latest appraisal; potential
    is the assessor's judgement against the published criteria."""

    employee = models.ForeignKey("employees.Employee", on_delete=models.CASCADE, related_name="talent_assessments")
    period = models.CharField(max_length=30, help_text="e.g. 2026 talent review")
    performance = models.PositiveSmallIntegerField(help_text="1 = below, 2 = meets, 3 = exceeds")
    potential = models.PositiveSmallIntegerField(help_text="1 = limited, 2 = moderate, 3 = high")
    criteria = models.JSONField(default=dict, help_text="{criterion: {met: bool, evidence: str}}")
    rationale = models.TextField()
    flight_risk = models.CharField(max_length=6, choices=[("low", "Low"), ("medium", "Medium"), ("high", "High")],
                                   default="low")
    assessed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="+")
    calibrated = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["employee", "period"], name="uniq_talent_assessment")]

    @property
    def box(self):
        return (self.performance - 1) * 3 + self.potential  # 1..9; 9 = high performance, high potential


class SuccessionPlan(TenantModel):
    RISK = [("low", "Low"), ("medium", "Medium"), ("high", "High")]
    position = models.OneToOneField("organization.Position", on_delete=models.CASCADE, related_name="succession_plan")
    risk_of_loss = models.CharField(max_length=6, choices=RISK, default="medium",
                                    help_text="Likelihood the incumbent leaves (incl. retirement).")
    impact_of_loss = models.CharField(max_length=6, choices=RISK, default="high")
    knowledge_transfer = models.TextField(blank=True, help_text="Critical knowledge to document or share.")
    notes = models.TextField(blank=True)
    last_reviewed = models.DateField(null=True, blank=True)

    def __str__(self):
        return f"Succession: {self.position}"


class Successor(TenantModel):
    READINESS = [("ready_now", "Ready now"), ("1_2_years", "Ready in 1-2 years"), ("3_plus", "Ready in 3+ years"),
                 ("emergency", "Emergency cover only")]
    plan = models.ForeignKey(SuccessionPlan, on_delete=models.CASCADE, related_name="successors")
    employee = models.ForeignKey("employees.Employee", on_delete=models.CASCADE, related_name="succession_slots")
    readiness = models.CharField(max_length=10, choices=READINESS, default="1_2_years")
    development_actions = models.TextField(blank=True)
    rank = models.PositiveSmallIntegerField(default=1)

    class Meta:
        ordering = ["plan", "rank"]
        constraints = [models.UniqueConstraint(fields=["plan", "employee"], name="uniq_successor")]


class CareerPath(TenantModel):
    """A defined progression step with transparent requirements (used for promotion eligibility)."""

    from_title = models.ForeignKey("organization.JobTitle", on_delete=models.CASCADE, related_name="paths_from")
    to_title = models.ForeignKey("organization.JobTitle", on_delete=models.CASCADE, related_name="paths_to")
    min_years_in_role = models.DecimalField(max_digits=4, decimal_places=1, default=Decimal("2"))
    min_rating = models.PositiveSmallIntegerField(default=3, help_text="Latest final appraisal rating at least.")
    required_courses = models.ManyToManyField("learning.Course", blank=True, related_name="+")
    required_qualification = models.CharField(max_length=200, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["from_title", "to_title"], name="uniq_career_path")]


class WorkforcePlan(TenantModel):
    STATUS = [("draft", "Draft"), ("approved", "Approved"), ("archived", "Archived")]
    name = models.CharField(max_length=150)
    year = models.PositiveSmallIntegerField(help_text="Plan year (projections run from here).")
    horizon_years = models.PositiveSmallIntegerField(default=3)
    status = models.CharField(max_length=10, choices=STATUS, default="draft")
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-year", "name"]

    def __str__(self):
        return self.name


class PlanLine(TenantModel):
    plan = models.ForeignKey(WorkforcePlan, on_delete=models.CASCADE, related_name="lines")
    department = models.ForeignKey("organization.Department", on_delete=models.CASCADE, related_name="+")
    job_title = models.ForeignKey("organization.JobTitle", null=True, blank=True, on_delete=models.SET_NULL,
                                  related_name="+", help_text="Blank = whole department.")
    employment_type = models.CharField(max_length=20, blank=True)
    planned_headcount = models.PositiveIntegerField()
    workload_units = models.DecimalField(max_digits=10, decimal_places=1, null=True, blank=True,
                                         help_text="Demand driver, e.g. beds or daily patients.")
    workload_label = models.CharField(max_length=60, blank=True)
    target_ratio = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True,
                                       help_text="Staff needed per workload unit (e.g. 0.25 nurses per bed).")
    justification = models.TextField(blank=True)

    class Meta:
        ordering = ["department__name"]


class Scenario(TenantModel):
    """What-if assumptions applied to a plan: growth, restructuring or budget cuts."""

    plan = models.ForeignKey(WorkforcePlan, on_delete=models.CASCADE, related_name="scenarios")
    name = models.CharField(max_length=150)
    attrition_percent = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True,
                                            help_text="Blank = use the last 12 months' actual turnover.")
    salary_increase_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"))
    growth_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"),
                                         help_text="Applied to planned headcount each year.")
    department_adjustments = models.JSONField(default=dict, blank=True,
                                              help_text='{"<department id>": -10} percent change per department.')
    hiring_freeze = models.BooleanField(default=False)
    budget_cap = models.DecimalField(**MONEY, help_text="Annual staff-cost ceiling (0 = none).")
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["plan", "name"]
