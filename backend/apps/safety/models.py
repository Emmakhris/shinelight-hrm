from django.conf import settings
from django.db import models

from apps.core.models import TenantModel


class Incident(TenantModel):
    KINDS = [("near_miss", "Near miss"), ("injury", "Injury / accident"), ("exposure", "Occupational exposure "
                                                                                       "(needlestick, splash)"),
             ("ill_health", "Work-related ill health"), ("violence", "Violence / aggression"),
             ("property", "Property / equipment damage"), ("fire", "Fire"), ("dangerous", "Dangerous occurrence")]
    SEVERITY = [("none", "No harm"), ("minor", "Minor (first aid)"), ("moderate", "Moderate (medical treatment)"),
                ("serious", "Serious (hospitalisation / lost time)"), ("fatal", "Fatal")]
    STATUS = [("reported", "Reported"), ("investigating", "Under investigation"), ("actions", "Actions in progress"),
              ("closed", "Closed")]
    reference = models.CharField(max_length=30, blank=True)
    kind = models.CharField(max_length=12, choices=KINDS)
    severity = models.CharField(max_length=10, choices=SEVERITY, default="none")
    occurred_at = models.DateTimeField()
    location = models.CharField(max_length=200)
    department = models.ForeignKey("organization.Department", null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    description = models.TextField(help_text="What happened. Do not include medical details here.")
    immediate_action = models.TextField(blank=True)
    persons_involved = models.ManyToManyField("employees.Employee", blank=True, related_name="incidents")
    others_involved = models.CharField(max_length=255, blank=True, help_text="Patients, visitors, contractors.")
    reported_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="+")
    investigator = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                     related_name="+")
    root_cause = models.TextField(blank=True)
    contributing_factors = models.TextField(blank=True)
    lost_time_days = models.PositiveSmallIntegerField(default=0)
    reportable = models.BooleanField(default=False, help_text="Must be reported to the Labour Department / "
                                                              "Factories Inspectorate.")
    reported_to_authority_on = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=14, choices=STATUS, default="reported", db_index=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-occurred_at"]

    def __str__(self):
        return f"{self.reference} {self.get_kind_display()}"


class RiskAssessment(TenantModel):
    STATUS = [("draft", "Draft"), ("active", "Active"), ("review_due", "Review due"), ("archived", "Archived")]
    title = models.CharField(max_length=200)
    department = models.ForeignKey("organization.Department", null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    activity = models.CharField(max_length=200, blank=True)
    hazard = models.TextField()
    who_at_risk = models.CharField(max_length=200, blank=True)
    likelihood = models.PositiveSmallIntegerField(default=3)
    severity = models.PositiveSmallIntegerField(default=3)
    controls = models.TextField(blank=True)
    residual_likelihood = models.PositiveSmallIntegerField(default=2)
    residual_severity = models.PositiveSmallIntegerField(default=2)
    assessed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="+")
    review_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS, default="active")

    class Meta:
        ordering = ["-likelihood", "-severity"]

    @property
    def risk_score(self):
        return self.likelihood * self.severity

    @property
    def residual_score(self):
        return self.residual_likelihood * self.residual_severity


class Inspection(TenantModel):
    title = models.CharField(max_length=200)
    department = models.ForeignKey("organization.Department", null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    date = models.DateField()
    inspector = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                  related_name="+")
    checklist = models.JSONField(default=list, help_text='[{"item": "Fire exits clear", "ok": true, "note": ""}]')
    findings = models.TextField(blank=True)

    class Meta:
        ordering = ["-date"]

    @property
    def score(self):
        items = self.checklist or []
        return round(100 * sum(1 for i in items if i.get("ok")) / len(items)) if items else None


class CorrectiveAction(TenantModel):
    STATUS = [("open", "Open"), ("done", "Done"), ("verified", "Verified effective")]
    incident = models.ForeignKey(Incident, null=True, blank=True, on_delete=models.CASCADE, related_name="actions")
    risk_assessment = models.ForeignKey(RiskAssessment, null=True, blank=True, on_delete=models.CASCADE,
                                        related_name="actions")
    inspection = models.ForeignKey(Inspection, null=True, blank=True, on_delete=models.CASCADE,
                                   related_name="actions")
    description = models.TextField()
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                              related_name="+")
    due_date = models.DateField()
    status = models.CharField(max_length=10, choices=STATUS, default="open")
    completed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    reminded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["status", "due_date"]


class OHRecord(TenantModel):
    """Occupational health record. Clinical content is visible only with ohs.medical; HR and managers see the
    fitness outcome and work restrictions only (features.txt §17)."""

    KINDS = [("pre_employment", "Pre-employment medical"), ("fitness", "Fitness-for-duty assessment"),
             ("injury_care", "Work injury treatment"), ("exposure", "Exposure follow-up (e.g. PEP)"),
             ("vaccination", "Vaccination (e.g. Hepatitis B)"), ("return_to_work", "Return-to-work assessment"),
             ("surveillance", "Health surveillance")]
    FITNESS = [("fit", "Fit for duty"), ("fit_restricted", "Fit with restrictions"), ("unfit", "Temporarily unfit"),
               ("pending", "Assessment pending")]
    employee = models.ForeignKey("employees.Employee", on_delete=models.CASCADE, related_name="oh_records")
    incident = models.ForeignKey(Incident, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    kind = models.CharField(max_length=15, choices=KINDS)
    date = models.DateField()
    clinical_notes = models.TextField(blank=True)
    fitness = models.CharField(max_length=15, choices=FITNESS, blank=True)
    restrictions = models.CharField(max_length=255, blank=True, help_text="Non-clinical, e.g. 'no lifting > 10 kg'.")
    valid_until = models.DateField(null=True, blank=True)
    review_date = models.DateField(null=True, blank=True)
    clinician = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                  related_name="+")

    class Meta:
        ordering = ["-date", "-id"]
