from django.conf import settings
from django.db import models

from apps.core.models import TenantModel


class NotificationTemplate(TenantModel):
    """Editable per-event, per-channel templates (Django template syntax). When absent, built-in
    defaults from notifications.defaults are used."""

    CHANNELS = [("in_app", "In-app"), ("email", "Email"), ("sms", "SMS")]
    event_code = models.CharField(max_length=60, db_index=True)
    channel = models.CharField(max_length=10, choices=CHANNELS)
    department = models.ForeignKey("organization.Department", null=True, blank=True, on_delete=models.CASCADE,
                                   help_text="Optional department-specific override.")
    subject = models.CharField(max_length=200, blank=True)
    body = models.TextField()
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["event_code", "channel"]

    def __str__(self):
        return f"{self.event_code} [{self.channel}]"


class Notification(TenantModel):
    """In-app notification shown in the portal inbox / bell."""

    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    event_code = models.CharField(max_length=60)
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    link = models.CharField(max_length=255, blank=True)
    is_read = models.BooleanField(default=False, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)
    related_type = models.CharField(max_length=60, blank=True)
    related_id = models.CharField(max_length=40, blank=True)

    class Meta:
        ordering = ["-created_at"]


class DeliveryLog(TenantModel):
    """Outbound email/SMS delivery attempts (for troubleshooting and retry)."""

    channel = models.CharField(max_length=10)
    recipient = models.CharField(max_length=255)
    event_code = models.CharField(max_length=60)
    status = models.CharField(max_length=10, default="queued")  # queued, sent, failed
    error = models.TextField(blank=True)
    provider_ref = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ["-created_at"]


class Announcement(TenantModel):
    AUDIENCE = [("all", "All staff"), ("department", "Specific departments"), ("branch", "Specific branches")]
    title = models.CharField(max_length=200)
    body = models.TextField()
    audience = models.CharField(max_length=12, choices=AUDIENCE, default="all")
    departments = models.ManyToManyField("organization.Department", blank=True)
    branches = models.ManyToManyField("organization.Branch", blank=True)
    publish_at = models.DateTimeField()
    expires_at = models.DateTimeField(null=True, blank=True)
    is_pinned = models.BooleanField(default=False)
    requires_acknowledgment = models.BooleanField(default=False, help_text="Policy acknowledgment required.")
    attachment = models.ForeignKey("documents.Document", null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")

    class Meta:
        ordering = ["-is_pinned", "-publish_at"]

    def __str__(self):
        return self.title


class Acknowledgment(TenantModel):
    """Employee read/acknowledgment of announcements and policies."""

    announcement = models.ForeignKey(Announcement, on_delete=models.CASCADE, related_name="acknowledgments")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    acknowledged_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("announcement", "user")]
