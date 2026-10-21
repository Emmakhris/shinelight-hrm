from django.conf import settings
from django.db import models

from apps.core.models import TenantModel


class Conversation(TenantModel):
    """A user's private conversation with the assistant. Only the user can read it; HR sees usage counts only."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="assistant_conversations")
    title = models.CharField(max_length=150, blank=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return self.title or f"Conversation {self.pk}"


class Message(TenantModel):
    ROLES = [("user", "User"), ("assistant", "Assistant"), ("tool", "Tool results")]
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=10, choices=ROLES)
    content = models.JSONField(default=list, help_text="Exact API content blocks, replayed unchanged.")
    text = models.TextField(blank=True, help_text="What the user sees.")
    tools_used = models.JSONField(default=list, blank=True)
    sources = models.JSONField(default=list, blank=True)
    input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    helpful = models.BooleanField(null=True, blank=True)
    feedback = models.TextField(blank=True)

    class Meta:
        ordering = ["created_at", "id"]
