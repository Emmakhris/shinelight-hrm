import hashlib
import secrets

from django.conf import settings
from django.db import models

from apps.core.models import TenantModel

EVENTS = [
    ("employee.created", "Employee created"),
    ("employee.updated", "Employee updated"),
    ("employee.status_changed", "Employee status changed"),
    ("employee.exited", "Employee exited"),
    ("leave.approved", "Leave approved"),
    ("payroll.released", "Payroll released"),
]


class ApiKey(TenantModel):
    """Machine-to-machine API access. Only a hash of the key is stored."""

    name = models.CharField(max_length=100)
    prefix = models.CharField(max_length=12, unique=True)
    key_hash = models.CharField(max_length=64)
    service_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="api_keys",
                                     help_text="Calls run with this user's permissions.")
    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    allowed_ips = models.JSONField(default=list, blank=True)

    def __str__(self):
        return f"{self.name} ({self.prefix}...)"

    @staticmethod
    def generate():
        raw = "slk_" + secrets.token_urlsafe(32)
        return raw, raw[:12], hashlib.sha256(raw.encode()).hexdigest()


class Webhook(TenantModel):
    name = models.CharField(max_length=100)
    url = models.URLField()
    events = models.JSONField(default=list, help_text="Event codes to deliver.")
    secret = models.CharField(max_length=64, default=secrets.token_hex)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class WebhookDelivery(TenantModel):
    webhook = models.ForeignKey(Webhook, on_delete=models.CASCADE, related_name="deliveries")
    event = models.CharField(max_length=50)
    payload = models.JSONField()
    status = models.CharField(max_length=10, default="pending")  # pending, success, failed
    attempts = models.PositiveSmallIntegerField(default=0)
    response_code = models.PositiveSmallIntegerField(null=True, blank=True)
    error = models.TextField(blank=True)
    next_attempt_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
