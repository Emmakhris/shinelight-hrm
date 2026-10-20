from django.conf import settings
from django.db import models

from apps.core.models import TenantModel

PRIORITIES = [("low", "Low"), ("normal", "Normal"), ("high", "High"), ("urgent", "Urgent")]


class ServiceCategory(TenantModel):
    code = models.SlugField(max_length=30)
    name = models.CharField(max_length=100)
    icon = models.CharField(max_length=40, blank=True)
    order = models.PositiveSmallIntegerField(default=100)

    class Meta:
        unique_together = [("organization", "code")]
        ordering = ["order", "name"]
        verbose_name_plural = "service categories"

    def __str__(self):
        return self.name


class ServiceType(TenantModel):
    """A catalogue item employees can request, with its own routing, SLA and form."""

    category = models.ForeignKey(ServiceCategory, on_delete=models.PROTECT, related_name="services")
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    default_priority = models.CharField(max_length=10, choices=PRIORITIES, default="normal")
    response_sla_hours = models.PositiveIntegerField(default=8, help_text="Time to first response.")
    resolution_sla_hours = models.PositiveIntegerField(default=72)
    team_role = models.ForeignKey("rbac.Role", null=True, blank=True, on_delete=models.SET_NULL,
                                  help_text="Tickets are routed to the least-loaded agent holding this role.")
    default_assignee = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                         related_name="+")
    form_fields = models.JSONField(default=list, blank=True,
                                   help_text='Extra fields, e.g. [{"name": "bank", "label": "Bank name", "required": true}]')
    letter_template = models.ForeignKey("documents.LetterTemplate", null=True, blank=True, on_delete=models.SET_NULL,
                                        help_text="Agents can generate this letter from the ticket in one click.")
    is_confidential = models.BooleanField(default=False, help_text="Visible only to assigned agent and desk managers.")
    self_service = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["category__order", "name"]

    def __str__(self):
        return self.name


class Ticket(TenantModel):
    STATUS = [
        ("new", "New"),
        ("open", "In progress"),
        ("pending_employee", "Waiting on employee"),
        ("resolved", "Resolved"),
        ("closed", "Closed"),
        ("cancelled", "Cancelled"),
    ]
    CHANNELS = [("portal", "Self-service portal"), ("email", "Email"), ("phone", "Phone"), ("walk_in", "Walk-in")]
    reference = models.CharField(max_length=30, db_index=True)
    service_type = models.ForeignKey(ServiceType, on_delete=models.PROTECT, related_name="tickets")
    requester = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="hr_tickets")
    employee = models.ForeignKey("employees.Employee", null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name="tickets")
    subject = models.CharField(max_length=200)
    description = models.TextField()
    form_data = models.JSONField(default=dict, blank=True)
    priority = models.CharField(max_length=10, choices=PRIORITIES, default="normal")
    status = models.CharField(max_length=20, choices=STATUS, default="new", db_index=True)
    channel = models.CharField(max_length=10, choices=CHANNELS, default="portal")
    assignee = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name="assigned_tickets")
    is_confidential = models.BooleanField(default=False)
    response_due = models.DateTimeField(null=True, blank=True)
    resolution_due = models.DateTimeField(null=True, blank=True)
    first_response_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    response_breached = models.BooleanField(default=False)
    resolution_breached = models.BooleanField(default=False)
    warned_at = models.DateTimeField(null=True, blank=True)
    escalated_at = models.DateTimeField(null=True, blank=True)
    paused_seconds = models.PositiveIntegerField(default=0, help_text="Time spent waiting on the employee.")
    paused_since = models.DateTimeField(null=True, blank=True)
    reopen_count = models.PositiveSmallIntegerField(default=0)
    rating = models.PositiveSmallIntegerField(null=True, blank=True)
    feedback = models.TextField(blank=True)
    resolution = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = [("organization", "reference")]

    def __str__(self):
        return f"{self.reference} {self.subject}"


class TicketComment(TenantModel):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    body = models.TextField()
    is_internal = models.BooleanField(default=False, help_text="Internal note visible to HR staff only.")
    attachment = models.ForeignKey("documents.Document", null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")

    class Meta:
        ordering = ["created_at", "id"]


class TicketEvent(TenantModel):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="events")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                              related_name="+")
    event = models.CharField(max_length=40)
    detail = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["created_at", "id"]


class KnowledgeArticle(TenantModel):
    category = models.ForeignKey(ServiceCategory, null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name="articles")
    title = models.CharField(max_length=200)
    body = models.TextField()
    tags = models.CharField(max_length=255, blank=True)
    is_published = models.BooleanField(default=True)
    views = models.PositiveIntegerField(default=0)
    helpful_yes = models.PositiveIntegerField(default=0)
    helpful_no = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["title"]

    def __str__(self):
        return self.title
