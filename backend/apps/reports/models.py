from django.conf import settings
from django.db import models

from apps.core.models import TenantModel


class ScheduledReport(TenantModel):
    FREQUENCY = [("daily", "Daily"), ("weekly", "Weekly (Monday)"), ("monthly", "Monthly (1st)")]
    name = models.CharField(max_length=150)
    report_code = models.CharField(max_length=50)
    params = models.JSONField(default=dict, blank=True)
    frequency = models.CharField(max_length=10, choices=FREQUENCY, default="monthly")
    recipients = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name="+",
                                        help_text="Only users authorised for the report receive it.")
    format = models.CharField(max_length=5, default="xlsx", choices=[("xlsx", "Excel"), ("csv", "CSV")])
    is_active = models.BooleanField(default=True)
    last_sent_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.name


class ExportRequest(TenantModel):
    """Bulk data exports require approval by a second person (features.txt section 24)."""

    STATUS = [("pending", "Pending approval"), ("approved", "Approved"), ("rejected", "Rejected"),
              ("downloaded", "Downloaded")]
    report_code = models.CharField(max_length=50)
    params = models.JSONField(default=dict, blank=True)
    reason = models.TextField()
    status = models.CharField(max_length=12, choices=STATUS, default="pending")
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
