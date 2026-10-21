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


class ReportDefinition(TenantModel):
    """A saved report-builder definition. Runs in each viewer's own data scope, so sharing never widens access."""

    VISIBILITY = [("private", "Only me"), ("shared", "Everyone with report access")]
    CHARTS = [("none", "Table only"), ("bar", "Bar list"), ("column", "Columns")]
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    dataset = models.CharField(max_length=30)
    columns = models.JSONField(default=list, blank=True)
    filters = models.JSONField(default=list, blank=True, help_text='[{"field", "op", "value"}]')
    group_by = models.JSONField(default=list, blank=True)
    aggregates = models.JSONField(default=list, blank=True, help_text='[{"fn": "count|sum|avg|min|max", "field"}]')
    sort = models.CharField(max_length=60, blank=True, help_text="Column code; prefix with - for descending.")
    limit = models.PositiveIntegerField(default=0, help_text="0 = no limit.")
    chart = models.CharField(max_length=10, choices=CHARTS, default="none")
    visibility = models.CharField(max_length=10, choices=VISIBILITY, default="private")

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def code(self):
        return f"custom:{self.pk}"

    def spec(self):
        return {k: getattr(self, k) for k in ("dataset", "columns", "filters", "group_by", "aggregates", "sort",
                                               "limit")}
