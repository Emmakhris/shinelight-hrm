from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

from apps.core.models import TenantModel


class WorkflowDefinition(TenantModel):
    """Configurable approval route for a request type. HR admins edit these without code changes.
    When several definitions exist for one request type, the lowest `priority` whose `conditions`
    match the request context is used (e.g. a stricter route for leave > 10 days)."""

    request_type = models.CharField(max_length=50, db_index=True)
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    conditions = models.JSONField(default=dict, blank=True, help_text='e.g. {"all":[{"field":"days","op":">","value":10}]}')
    priority = models.PositiveSmallIntegerField(default=100)
    is_active = models.BooleanField(default=True)
    version = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["request_type", "priority"]

    def __str__(self):
        return f"{self.name} ({self.request_type})"


class WorkflowStep(TenantModel):
    APPROVER_TYPES = [
        ("supervisor", "Employee's supervisor"),
        ("supervisor_2", "Supervisor's supervisor"),
        ("dept_head", "Head of department"),
        ("role", "Users holding a role"),
        ("user", "Specific user"),
    ]
    COMMENT_RULES = [("none", "Optional"), ("reject", "Required to reject/return"), ("all", "Always required")]
    MODES = [("any", "Any one approver"), ("all", "All approvers")]

    definition = models.ForeignKey(WorkflowDefinition, on_delete=models.CASCADE, related_name="steps")
    order = models.PositiveSmallIntegerField(help_text="Steps with the same order run in parallel.")
    name = models.CharField(max_length=100)
    approver_type = models.CharField(max_length=20, choices=APPROVER_TYPES)
    role = models.ForeignKey("rbac.Role", null=True, blank=True, on_delete=models.PROTECT)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
                             related_name="+")
    approval_mode = models.CharField(max_length=5, choices=MODES, default="any")
    condition = models.JSONField(default=dict, blank=True, help_text="Step runs only when this matches.")
    sla_hours = models.PositiveIntegerField(default=48)
    escalate_to_role = models.ForeignKey("rbac.Role", null=True, blank=True, on_delete=models.SET_NULL,
                                         related_name="+")
    comment_rule = models.CharField(max_length=10, choices=COMMENT_RULES, default="reject")
    skip_if_no_approver = models.BooleanField(default=True, help_text="Skip (instead of escalating) when unresolved.")

    class Meta:
        ordering = ["definition", "order", "id"]

    def __str__(self):
        return f"{self.definition.name} #{self.order} {self.name}"


class WorkflowInstance(TenantModel):
    STATUS = [
        ("in_progress", "In progress"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("returned", "Returned for correction"),
        ("cancelled", "Cancelled"),
        ("error", "Error / needs attention"),
    ]
    definition = models.ForeignKey(WorkflowDefinition, on_delete=models.PROTECT, related_name="instances")
    request_type = models.CharField(max_length=50, db_index=True)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveBigIntegerField()
    target = GenericForeignKey("content_type", "object_id")
    title = models.CharField(max_length=255)
    initiator = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    subject_employee = models.ForeignKey("employees.Employee", null=True, blank=True, on_delete=models.SET_NULL,
                                         related_name="workflow_instances")
    status = models.CharField(max_length=12, choices=STATUS, default="in_progress", db_index=True)
    current_order = models.PositiveSmallIntegerField(default=0)
    context = models.JSONField(default=dict, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["content_type", "object_id"])]

    def __str__(self):
        return self.title


class WorkflowTask(TenantModel):
    STATUS = [
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("returned", "Returned"),
        ("skipped", "Skipped"),
        ("cancelled", "Cancelled"),
        ("reassigned", "Reassigned"),
    ]
    instance = models.ForeignKey(WorkflowInstance, on_delete=models.CASCADE, related_name="tasks")
    step = models.ForeignKey(WorkflowStep, on_delete=models.PROTECT, related_name="tasks")
    assignee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="workflow_tasks")
    delegated_from = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                       related_name="+")
    status = models.CharField(max_length=12, choices=STATUS, default="pending", db_index=True)
    due_at = models.DateTimeField(null=True, blank=True)
    reminded_at = models.DateTimeField(null=True, blank=True)
    escalated_at = models.DateTimeField(null=True, blank=True)
    is_escalation = models.BooleanField(default=False)
    acted_at = models.DateTimeField(null=True, blank=True)
    acted_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name="+")
    comment = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.instance.title} -> {self.assignee}"


class WorkflowAction(TenantModel):
    """Immutable history: who acted, when, and what decision was made."""

    instance = models.ForeignKey(WorkflowInstance, on_delete=models.CASCADE, related_name="history")
    task = models.ForeignKey(WorkflowTask, null=True, blank=True, on_delete=models.SET_NULL)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    action = models.CharField(max_length=30)
    comment = models.TextField(blank=True)

    class Meta:
        ordering = ["created_at", "id"]


class Delegation(TenantModel):
    """Delegation of approval authority during a manager's absence."""

    delegator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="delegations_given")
    delegate = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                 related_name="delegations_received")
    start_date = models.DateField()
    end_date = models.DateField()
    request_types = models.JSONField(default=list, blank=True, help_text="Empty = all request types.")
    reason = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-start_date"]

    def __str__(self):
        return f"{self.delegator} -> {self.delegate} ({self.start_date} to {self.end_date})"
