from django.conf import settings
from django.db import models

from apps.core.models import TenantModel

REGULATORS = [
    ("mdc", "Medical and Dental Council"),
    ("nmc", "Nursing and Midwifery Council"),
    ("pc", "Pharmacy Council"),
    ("ahpc", "Allied Health Professions Council"),
    ("ghpc", "Health Facilities Regulatory Agency"),
    ("other", "Other professional body"),
]


class ProfessionalLicense(TenantModel):
    STATUS = [("pending", "Pending verification"), ("active", "Active"), ("expired", "Expired"),
              ("suspended", "Suspended"), ("revoked", "Revoked")]
    employee = models.ForeignKey("employees.Employee", on_delete=models.CASCADE, related_name="licenses")
    license_type = models.CharField(max_length=100, help_text="e.g. Registered General Nurse, Medical Officer")
    regulator = models.CharField(max_length=10, choices=REGULATORS)
    registration_number = models.CharField(max_length=60)
    issue_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True, db_index=True)
    status = models.CharField(max_length=10, choices=STATUS, default="pending")
    verified_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="+")
    verified_at = models.DateTimeField(null=True, blank=True)
    verification_note = models.CharField(max_length=255, blank=True)
    document = models.ForeignKey("documents.Document", null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name="+")

    class Meta:
        ordering = ["employee", "-expiry_date"]

    def __str__(self):
        return f"{self.license_type} {self.registration_number} ({self.employee.full_name})"

    def is_valid_on(self, date):
        return self.status == "active" and (self.expiry_date is None or self.expiry_date >= date)


class CompetencyRequirement(TenantModel):
    """Mandatory clinical training/competency for a role (e.g. BLS every 24 months)."""

    name = models.CharField(max_length=150)
    job_titles = models.ManyToManyField("organization.JobTitle", related_name="competency_requirements")
    refresh_months = models.PositiveSmallIntegerField(default=24)
    blocks_rostering = models.BooleanField(default=False)

    def __str__(self):
        return self.name


class CompetencyRecord(TenantModel):
    employee = models.ForeignKey("employees.Employee", on_delete=models.CASCADE, related_name="competencies")
    requirement = models.ForeignKey(CompetencyRequirement, on_delete=models.CASCADE, related_name="records")
    completed_on = models.DateField()
    expires_on = models.DateField(null=True, blank=True)
    assessor = models.CharField(max_length=150, blank=True)
    score = models.CharField(max_length=20, blank=True)

    class Meta:
        ordering = ["-completed_on"]
