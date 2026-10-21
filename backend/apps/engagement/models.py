from django.conf import settings
from django.db import models

from apps.core.models import TenantModel


class Survey(TenantModel):
    KINDS = [("engagement", "Engagement survey"), ("pulse", "Pulse survey"), ("stay", "Stay interview"),
             ("wellbeing", "Wellbeing check"), ("other", "Other")]
    STATUS = [("draft", "Draft"), ("open", "Open"), ("closed", "Closed")]
    title = models.CharField(max_length=200)
    kind = models.CharField(max_length=12, choices=KINDS, default="pulse")
    intro = models.TextField(blank=True)
    anonymous = models.BooleanField(default=True, help_text="Responses are never linked to the person.")
    min_group_size = models.PositiveSmallIntegerField(default=5,
                                                      help_text="Results are hidden for groups smaller than this.")
    departments = models.ManyToManyField("organization.Department", blank=True, related_name="+",
                                         help_text="Blank = everyone.")
    # [{"key": "q1", "text": "...", "type": "rating|enps|text|choice", "options": [...], "dimension": "engagement"}]
    questions = models.JSONField(default=list)
    opens_on = models.DateField(null=True, blank=True)
    closes_on = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=6, choices=STATUS, default="draft", db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class SurveyInvite(TenantModel):
    """Who was invited and whether they responded - kept apart from the answers when anonymous."""

    survey = models.ForeignKey(Survey, on_delete=models.CASCADE, related_name="invites")
    employee = models.ForeignKey("employees.Employee", on_delete=models.CASCADE, related_name="+")
    responded = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["survey", "employee"], name="uniq_survey_invite")]


class SurveyResponse(TenantModel):
    survey = models.ForeignKey(Survey, on_delete=models.CASCADE, related_name="responses")
    department = models.ForeignKey("organization.Department", null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+", help_text="Snapshot for breakdowns (shown only for big groups).")
    employee = models.ForeignKey("employees.Employee", null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name="+", help_text="Only for non-anonymous surveys.")
    answers = models.JSONField(default=dict)
    submitted_on = models.DateField(help_text="Date only, to make re-identification harder.")


class ActionPlan(TenantModel):
    STATUS = [("planned", "Planned"), ("in_progress", "In progress"), ("done", "Done")]
    survey = models.ForeignKey(Survey, null=True, blank=True, on_delete=models.SET_NULL, related_name="actions")
    department = models.ForeignKey("organization.Department", null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    issue = models.CharField(max_length=255)
    action = models.TextField()
    owner = models.ForeignKey("employees.Employee", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=12, choices=STATUS, default="planned")
    progress_note = models.TextField(blank=True)

    class Meta:
        ordering = ["status", "due_date"]


class Recognition(TenantModel):
    VALUES = [("teamwork", "Teamwork"), ("patient_care", "Patient / customer care"), ("integrity", "Integrity"),
              ("innovation", "Innovation"), ("extra_mile", "Going the extra mile"), ("leadership", "Leadership")]
    giver = models.ForeignKey("employees.Employee", on_delete=models.CASCADE, related_name="recognitions_given")
    recipient = models.ForeignKey("employees.Employee", on_delete=models.CASCADE,
                                  related_name="recognitions_received")
    value = models.CharField(max_length=15, choices=VALUES)
    message = models.TextField()
    is_public = models.BooleanField(default=True)
    likes = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="+")

    class Meta:
        ordering = ["-created_at"]


class Suggestion(TenantModel):
    STATUS = [("new", "New"), ("under_review", "Under review"), ("accepted", "Accepted"),
              ("implemented", "Implemented"), ("declined", "Declined")]
    CATEGORIES = [("process", "Process / efficiency"), ("patient", "Patient / customer experience"),
                  ("welfare", "Staff welfare"), ("safety", "Health & safety"), ("cost", "Cost saving"),
                  ("other", "Other")]
    author = models.ForeignKey("employees.Employee", null=True, blank=True, on_delete=models.SET_NULL,
                               related_name="+", help_text="Blank when submitted anonymously.")
    category = models.CharField(max_length=10, choices=CATEGORIES, default="process")
    title = models.CharField(max_length=200)
    text = models.TextField()
    status = models.CharField(max_length=14, choices=STATUS, default="new", db_index=True)
    response = models.TextField(blank=True)
    votes = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="+")

    class Meta:
        ordering = ["-created_at"]


class Event(TenantModel):
    KINDS = [("welfare", "Welfare"), ("wellness", "Wellness / health screening"), ("social", "Social / team"),
             ("eap", "Employee assistance (counselling)"), ("celebration", "Celebration")]
    title = models.CharField(max_length=200)
    kind = models.CharField(max_length=12, choices=KINDS, default="social")
    description = models.TextField(blank=True)
    starts_at = models.DateTimeField()
    location = models.CharField(max_length=200, blank=True)
    capacity = models.PositiveSmallIntegerField(null=True, blank=True)
    attendees = models.ManyToManyField("employees.Employee", blank=True, related_name="+")

    class Meta:
        ordering = ["starts_at"]
