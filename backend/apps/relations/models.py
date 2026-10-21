import os
import secrets

from django.conf import settings
from django.db import models

from apps.core.models import TenantModel


class Case(TenantModel):
    """Confidential employee-relations case. Visible only to its case officer, investigators and holders of
    relations.view_all; parties see their own submissions and the actions addressed to them."""

    TYPES = [("grievance", "Grievance"), ("harassment", "Harassment / bullying"), ("misconduct", "Misconduct"),
             ("disciplinary", "Disciplinary"), ("conflict", "Workplace conflict"),
             ("policy_violation", "Policy violation"), ("whistleblowing", "Whistleblowing")]
    SEVERITY = [("low", "Low"), ("medium", "Medium"), ("high", "High"), ("critical", "Critical")]
    STATUS = [("reported", "Reported"), ("investigating", "Under investigation"), ("hearing", "Hearing / mediation"),
              ("pending_decision", "Decision awaiting approval"), ("decided", "Decision issued"),
              ("appeal", "Under appeal"), ("closed", "Closed"), ("withdrawn", "Withdrawn")]
    OUTCOMES = [("no_case", "No case to answer"), ("resolved_informally", "Resolved informally"),
                ("mediation_agreement", "Mediation agreement"), ("counselling", "Counselling"),
                ("verbal_warning", "Verbal warning"), ("written_warning", "Written warning"),
                ("final_warning", "Final written warning"), ("suspension", "Suspension"),
                ("demotion", "Demotion"), ("dismissal", "Dismissal"), ("upheld", "Grievance upheld"),
                ("not_upheld", "Grievance not upheld"), ("other", "Other")]
    SERIOUS = ["suspension", "demotion", "dismissal"]  # need HR Director approval
    reference = models.CharField(max_length=30, blank=True)
    case_type = models.CharField(max_length=20, choices=TYPES)
    title = models.CharField(max_length=200)
    description = models.TextField()
    severity = models.CharField(max_length=10, choices=SEVERITY, default="medium")
    incident_date = models.DateField(null=True, blank=True)
    complainant = models.ForeignKey("employees.Employee", null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="er_cases_raised")
    is_anonymous = models.BooleanField(default=False, help_text="Reporter identity hidden from everyone but HR "
                                                                "Director-level reviewers.")
    reported_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="+")
    respondents = models.ManyToManyField("employees.Employee", blank=True, related_name="er_cases_against")
    policy_reference = models.CharField(max_length=200, blank=True)
    case_officer = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                     related_name="+")
    investigators = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="+")
    investigation_plan = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS, default="reported", db_index=True)
    due_date = models.DateField(null=True, blank=True)
    escalated_at = models.DateTimeField(null=True, blank=True)
    outcome = models.CharField(max_length=20, choices=OUTCOMES, blank=True)
    outcome_summary = models.TextField(blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.reference} {self.get_case_type_display()}"


def _evidence_path(instance, filename):
    return (f"relations/{instance.organization_id}/{instance.case_id}/"
            f"{secrets.token_hex(8)}{os.path.splitext(filename)[1].lower()}")


class CaseNote(TenantModel):
    KINDS = [("note", "Case note"), ("finding", "Investigation finding"), ("statement", "Statement"),
             ("evidence", "Evidence"), ("correspondence", "Correspondence")]
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="notes")
    kind = models.CharField(max_length=15, choices=KINDS, default="note")
    text = models.TextField(blank=True)
    file = models.FileField(upload_to=_evidence_path, max_length=255, blank=True)
    file_name = models.CharField(max_length=255, blank=True)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                               related_name="+")

    class Meta:
        ordering = ["created_at"]


class CaseMeeting(TenantModel):
    KINDS = [("interview", "Investigation interview"), ("hearing", "Disciplinary hearing"), ("mediation", "Mediation"),
             ("appeal", "Appeal hearing"), ("other", "Other")]
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="meetings")
    kind = models.CharField(max_length=10, choices=KINDS, default="interview")
    scheduled_at = models.DateTimeField()
    venue = models.CharField(max_length=200, blank=True)
    attendees = models.TextField(blank=True, help_text="Names and roles (including any companion or union rep).")
    invitees = models.ManyToManyField("employees.Employee", blank=True, related_name="+")
    minutes = models.TextField(blank=True)
    held = models.BooleanField(default=False)

    class Meta:
        ordering = ["scheduled_at"]


class CaseAction(TenantModel):
    """Sanction or formal outcome addressed to one employee (warning, suspension...), with their response."""

    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="actions")
    employee = models.ForeignKey("employees.Employee", on_delete=models.CASCADE, related_name="er_actions")
    action_type = models.CharField(max_length=20, choices=Case.OUTCOMES)
    details = models.TextField()
    effective_date = models.DateField()
    expires_on = models.DateField(null=True, blank=True, help_text="Warnings lapse after this date.")
    suspension_days = models.PositiveSmallIntegerField(default=0)
    letter = models.ForeignKey("documents.Document", null=True, blank=True, on_delete=models.SET_NULL,
                               related_name="+")
    issued_at = models.DateTimeField(null=True, blank=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    employee_response = models.TextField(blank=True)
    appeal_deadline = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["-effective_date"]


class Appeal(TenantModel):
    STATUS = [("submitted", "Submitted"), ("hearing", "Hearing scheduled"), ("upheld", "Appeal upheld"),
              ("varied", "Sanction varied"), ("dismissed", "Appeal dismissed"), ("withdrawn", "Withdrawn")]
    action = models.ForeignKey(CaseAction, on_delete=models.CASCADE, related_name="appeals")
    grounds = models.TextField()
    status = models.CharField(max_length=10, choices=STATUS, default="submitted")
    decision = models.TextField(blank=True)
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
