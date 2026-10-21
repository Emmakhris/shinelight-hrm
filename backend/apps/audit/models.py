import hashlib
import json

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils import timezone


class AppendOnlyQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise PermissionError("Audit records are immutable.")

    def delete(self):
        raise PermissionError("Audit records cannot be deleted.")


class AuditLog(models.Model):
    """Tamper-evident, append-only audit trail. Each entry stores the hash of the previous
    entry for the same organization; `verify_chain` detects any alteration or removal."""

    ACTIONS = [
        ("create", "Create"),
        ("update", "Update"),
        ("delete", "Delete"),
        ("view", "View sensitive record"),
        ("export", "Export"),
        ("login", "Login"),
        ("login_failed", "Failed login"),
        ("logout", "Logout"),
        ("approve", "Approve"),
        ("reject", "Reject"),
        ("workflow", "Workflow action"),
        ("payroll", "Payroll action"),
        ("permission", "Permission change"),
        ("config", "Configuration change"),
        ("download", "Document download"),
        ("ai", "AI assistant use"),
    ]

    organization = models.ForeignKey("tenancy.Organization", null=True, on_delete=models.PROTECT, related_name="+")
    timestamp = models.DateTimeField(default=timezone.now, db_index=True, editable=False)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    actor_repr = models.CharField(max_length=255, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    action = models.CharField(max_length=20, choices=ACTIONS, db_index=True)
    content_type = models.ForeignKey(ContentType, null=True, blank=True, on_delete=models.SET_NULL)
    object_id = models.CharField(max_length=64, blank=True, db_index=True)
    object_repr = models.CharField(max_length=255, blank=True)
    changes = models.JSONField(default=dict, blank=True)
    message = models.TextField(blank=True)
    prev_hash = models.CharField(max_length=64, blank=True)
    hash = models.CharField(max_length=64, blank=True)

    objects = AppendOnlyQuerySet.as_manager()

    class Meta:
        ordering = ["-id"]
        indexes = [models.Index(fields=["content_type", "object_id"])]

    def __str__(self):
        return f"{self.timestamp:%Y-%m-%d %H:%M} {self.actor_repr} {self.action} {self.object_repr}"

    def compute_hash(self):
        payload = json.dumps(
            {
                "org": self.organization_id,
                "ts": self.timestamp.isoformat() if self.timestamp else None,
                "actor": self.actor_id,
                "action": self.action,
                "ct": self.content_type_id,
                "oid": self.object_id,
                "repr": self.object_repr,
                "changes": self.changes,
                "msg": self.message,
                "prev": self.prev_hash,
            },
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    def save(self, *args, **kwargs):
        if self.pk:
            raise PermissionError("Audit records are immutable.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError("Audit records cannot be deleted.")


class AuditChainHead(models.Model):
    """Holds the latest hash per organization; row-locked when appending."""

    organization = models.OneToOneField("tenancy.Organization", null=True, on_delete=models.CASCADE)
    last_hash = models.CharField(max_length=64, blank=True)
