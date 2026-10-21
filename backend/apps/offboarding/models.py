from django.conf import settings
from django.db import models

from apps.core.models import TenantModel

OWNERS = [("hr", "HR"), ("supervisor", "Supervisor / department"), ("it", "IT"), ("finance", "Finance"),
          ("payroll", "Payroll"), ("admin", "Administration / facilities")]


class Separation(TenantModel):
    TYPES = [("resignation", "Resignation"), ("retirement", "Retirement"), ("contract_end", "End of contract"),
             ("termination", "Termination (notice)"), ("dismissal", "Dismissal"), ("redundancy", "Redundancy"),
             ("mutual", "Mutual separation"), ("death", "Death in service"),
             ("probation_termination", "Termination during probation")]
    REASONS = [("better_pay", "Better pay / benefits"), ("career", "Career growth"), ("relocation", "Relocation"),
               ("family", "Family / personal"), ("health", "Health"), ("management", "Relationship with management"),
               ("workload", "Workload / working hours"), ("studies", "Further studies"), ("travel", "Travelling abroad"),
               ("retirement", "Retirement"), ("conduct", "Conduct / performance"), ("other", "Other")]
    STATUS = [("draft", "Draft"), ("pending", "Pending approval"), ("returned", "Returned"), ("rejected", "Rejected"),
              ("clearance", "Clearance in progress"), ("completed", "Completed"), ("withdrawn", "Withdrawn")]
    INVOLUNTARY = ["termination", "dismissal", "redundancy", "probation_termination"]
    reference = models.CharField(max_length=30, blank=True)
    employee = models.ForeignKey("employees.Employee", on_delete=models.CASCADE, related_name="separations")
    exit_type = models.CharField(max_length=24, choices=TYPES)
    reason = models.CharField(max_length=12, choices=REASONS, blank=True)
    details = models.TextField(blank=True, help_text="Resignation letter text or grounds.")
    notice_date = models.DateField()
    last_working_day = models.DateField()
    notice_required_days = models.PositiveSmallIntegerField(default=30)
    notice_shortfall_days = models.PositiveSmallIntegerField(default=0)
    rehire_eligible = models.BooleanField(default=True)
    handover_to = models.ForeignKey("employees.Employee", null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="+")
    handover_notes = models.TextField(blank=True)
    access_extension_until = models.DateField(null=True, blank=True,
                                              help_text="Approved exception: keep system access until this date.")
    status = models.CharField(max_length=12, choices=STATUS, default="pending", db_index=True)
    er_action = models.ForeignKey("relations.CaseAction", null=True, blank=True, on_delete=models.SET_NULL,
                                  related_name="+")
    submitted_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                     related_name="+")
    approved_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    certificate = models.ForeignKey("documents.Document", null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="+")

    class Meta:
        ordering = ["-last_working_day"]

    def __str__(self):
        return f"{self.reference} {self.employee.full_name} ({self.get_exit_type_display()})"


class ClearanceItem(TenantModel):
    STATUS = [("pending", "Pending"), ("cleared", "Cleared"), ("waived", "Waived")]
    separation = models.ForeignKey(Separation, on_delete=models.CASCADE, related_name="clearance")
    order = models.PositiveSmallIntegerField(default=0)
    owner = models.CharField(max_length=10, choices=OWNERS)
    title = models.CharField(max_length=200)
    auto_check = models.CharField(max_length=20, blank=True, help_text="Automatic check: assets | loans | "
                                                                       "exit_interview | final_pay")
    status = models.CharField(max_length=8, choices=STATUS, default="pending")
    notes = models.TextField(blank=True)
    cleared_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    cleared_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["order", "id"]


class ExitInterview(TenantModel):
    QUESTIONS = ["Pay and benefits", "Relationship with supervisor", "Career growth and training", "Workload",
                 "Working conditions", "Recognition", "Team and colleagues"]
    separation = models.OneToOneField(Separation, on_delete=models.CASCADE, related_name="exit_interview")
    ratings = models.JSONField(default=dict, blank=True)
    primary_reason = models.CharField(max_length=12, choices=Separation.REASONS, blank=True)
    what_went_well = models.TextField(blank=True)
    what_to_improve = models.TextField(blank=True)
    would_recommend = models.BooleanField(null=True, blank=True)
    would_return = models.BooleanField(null=True, blank=True)
    conducted_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                     related_name="+", help_text="Blank when completed by the leaver online.")
    completed_at = models.DateTimeField(null=True, blank=True)
