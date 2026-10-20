from django.conf import settings
from django.db import models

from apps.core.models import TenantModel
from apps.organization.models import Position

OWNER_TYPES = [("hr", "HR"), ("manager", "Hiring manager / supervisor"), ("it", "IT"), ("finance", "Finance / payroll"),
               ("admin", "Administration / facilities"), ("employee", "New employee"), ("role", "Specific role")]
CATEGORIES = [("pre_employment", "Pre-employment checks"), ("documents", "Documents & information"),
              ("equipment", "Equipment & resources"), ("access", "Accounts & system access"),
              ("induction", "Induction & orientation"), ("policy", "Policy acknowledgment"),
              ("training", "Mandatory training"), ("probation", "Probation"), ("survey", "New-hire feedback"),
              ("other", "Other")]


class ChecklistTemplate(TenantModel):
    """Onboarding checklist; the most specific active template (department + employment type) is used."""

    name = models.CharField(max_length=150)
    department = models.ForeignKey("organization.Department", null=True, blank=True, on_delete=models.CASCADE,
                                   related_name="+", help_text="Leave blank for all departments.")
    employment_type = models.CharField(max_length=20, choices=Position.EMPLOYMENT_TYPES, blank=True)
    is_active = models.BooleanField(default=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class ChecklistTemplateTask(TenantModel):
    template = models.ForeignKey(ChecklistTemplate, on_delete=models.CASCADE, related_name="tasks")
    order = models.PositiveSmallIntegerField(default=0)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=15, choices=CATEGORIES, default="other")
    owner_type = models.CharField(max_length=10, choices=OWNER_TYPES, default="hr")
    role = models.ForeignKey("rbac.Role", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    due_offset_days = models.SmallIntegerField(default=0, help_text="Days relative to the start date (negative = "
                                                                    "before day one).")
    is_mandatory = models.BooleanField(default=True)
    document_category = models.ForeignKey("documents.DocumentCategory", null=True, blank=True,
                                          on_delete=models.SET_NULL, related_name="+",
                                          help_text="Completion requires a document of this type on file.")
    policy_document = models.ForeignKey("documents.Document", null=True, blank=True, on_delete=models.SET_NULL,
                                        related_name="+", help_text="Employee must acknowledge this policy.")
    # [{"key": "rating", "label": "How welcome did you feel?", "type": "rating"}, {"key": "comments", "type": "text"}]
    form = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["template", "order", "id"]


class Onboarding(TenantModel):
    STATUS = [("in_progress", "In progress"), ("completed", "Completed"), ("cancelled", "Cancelled")]
    employee = models.ForeignKey("employees.Employee", on_delete=models.CASCADE, related_name="onboardings")
    template = models.ForeignKey(ChecklistTemplate, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    offer = models.ForeignKey("recruitment.Offer", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    start_date = models.DateField()
    buddy = models.ForeignKey("employees.Employee", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    status = models.CharField(max_length=12, choices=STATUS, default="in_progress", db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-start_date"]

    def __str__(self):
        return f"Onboarding {self.employee.full_name}"


class OnboardingTask(TenantModel):
    STATUS = [("pending", "Pending"), ("done", "Done"), ("waived", "Not applicable / waived")]
    onboarding = models.ForeignKey(Onboarding, on_delete=models.CASCADE, related_name="tasks")
    order = models.PositiveSmallIntegerField(default=0)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=15, choices=CATEGORIES, default="other")
    owner_type = models.CharField(max_length=10, choices=OWNER_TYPES, default="hr")
    role = models.ForeignKey("rbac.Role", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    assignee = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name="+", help_text="Specific person (overrides the owner type).")
    due_date = models.DateField()
    is_mandatory = models.BooleanField(default=True)
    document_category = models.ForeignKey("documents.DocumentCategory", null=True, blank=True,
                                          on_delete=models.SET_NULL, related_name="+")
    policy_document = models.ForeignKey("documents.Document", null=True, blank=True, on_delete=models.SET_NULL,
                                        related_name="+")
    form = models.JSONField(default=list, blank=True)
    response = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=8, choices=STATUS, default="pending", db_index=True)
    notes = models.TextField(blank=True)
    completed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                     related_name="+")
    completed_at = models.DateTimeField(null=True, blank=True)
    escalated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["due_date", "order", "id"]


class ProbationReview(TenantModel):
    TYPES = [("midpoint", "Mid-probation review"), ("final", "End-of-probation review")]
    STATUS = [("scheduled", "Scheduled"), ("submitted", "Submitted for decision"), ("returned", "Returned"),
              ("completed", "Decision applied"), ("rejected", "Recommendation not approved"),
              ("cancelled", "Cancelled")]
    RECOMMENDATIONS = [("confirm", "Confirm appointment"), ("extend", "Extend probation"),
                       ("terminate", "Terminate appointment"), ("continue", "Continue probation (mid-point)")]
    CRITERIA = ["Job knowledge and skills", "Quality of work", "Productivity", "Attendance and punctuality",
                "Conduct and attitude", "Teamwork and communication"]
    employee = models.ForeignKey("employees.Employee", on_delete=models.CASCADE, related_name="probation_reviews")
    onboarding = models.ForeignKey(Onboarding, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="probation_reviews")
    review_type = models.CharField(max_length=10, choices=TYPES)
    due_date = models.DateField()
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name="+")
    status = models.CharField(max_length=10, choices=STATUS, default="scheduled", db_index=True)
    ratings = models.JSONField(default=dict, blank=True)
    overall_rating = models.DecimalField(max_digits=3, decimal_places=2, null=True, blank=True)
    strengths = models.TextField(blank=True)
    improvements = models.TextField(blank=True)
    recommendation = models.CharField(max_length=10, choices=RECOMMENDATIONS, blank=True)
    extend_months = models.PositiveSmallIntegerField(default=0)
    reviewer_comments = models.TextField(blank=True)
    employee_comments = models.TextField(blank=True)
    employee_acknowledged_at = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    reminded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["due_date"]

    def __str__(self):
        return f"{self.get_review_type_display()} - {self.employee.full_name}"
