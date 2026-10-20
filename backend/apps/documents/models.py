import hashlib
import os

from django.conf import settings
from django.db import models

from apps.core.models import TenantModel

CONFIDENTIALITY = [
    ("internal", "Internal"),
    ("confidential", "Confidential (HR only)"),
    ("restricted", "Restricted (medical / disciplinary / named roles)"),
]


class DocumentCategory(TenantModel):
    code = models.SlugField(max_length=40)
    name = models.CharField(max_length=100)
    default_confidentiality = models.CharField(max_length=15, choices=CONFIDENTIALITY, default="confidential")
    retention_years = models.PositiveSmallIntegerField(default=7, help_text="Years kept after employee exit.")
    requires_expiry = models.BooleanField(default=False)
    is_mandatory = models.BooleanField(default=False, help_text="Every employee should have one (checklist).")
    visible_to_employee = models.BooleanField(default=True)

    class Meta:
        unique_together = [("organization", "code")]
        ordering = ["name"]
        verbose_name_plural = "document categories"

    def __str__(self):
        return self.name


class Document(TenantModel):
    STATUS = [("draft", "Draft"), ("pending", "Pending approval"), ("approved", "Approved"), ("void", "Void")]
    employee = models.ForeignKey("employees.Employee", null=True, blank=True, on_delete=models.CASCADE,
                                 related_name="documents", help_text="Blank for organization-wide documents/policies.")
    category = models.ForeignKey(DocumentCategory, on_delete=models.PROTECT, related_name="documents")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    reference_no = models.CharField(max_length=60, blank=True)
    confidentiality = models.CharField(max_length=15, choices=CONFIDENTIALITY, default="confidential")
    visible_to_employee = models.BooleanField(default=True)
    status = models.CharField(max_length=10, choices=STATUS, default="approved")
    issue_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True, db_index=True)
    tags = models.CharField(max_length=255, blank=True)
    is_policy = models.BooleanField(default=False)
    requires_acknowledgment = models.BooleanField(default=False)
    legal_hold = models.BooleanField(default=False)
    legal_hold_reason = models.CharField(max_length=255, blank=True)
    retention_until = models.DateField(null=True, blank=True)
    is_archived = models.BooleanField(default=False)
    allow_download = models.BooleanField(default=True, help_text="Controlled download/print.")
    current_version = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    @property
    def latest(self):
        return self.versions.order_by("-version").first()


def _upload_path(instance, filename):
    doc = instance.document
    base = f"documents/{doc.organization_id}/{doc.employee_id or 'org'}/{doc.id}"
    return f"{base}/v{instance.version}{os.path.splitext(filename)[1].lower()}"


class DocumentVersion(TenantModel):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="versions")
    version = models.PositiveIntegerField()
    file = models.FileField(upload_to=_upload_path, max_length=255)
    file_name = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100, blank=True)
    size = models.PositiveBigIntegerField(default=0)
    sha256 = models.CharField(max_length=64, blank=True)
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        unique_together = [("document", "version")]
        ordering = ["-version"]

    def save(self, *args, **kwargs):
        if self.file and not self.sha256:
            h = hashlib.sha256()
            for chunk in self.file.chunks():
                h.update(chunk)
            self.sha256 = h.hexdigest()
            self.size = self.file.size
        super().save(*args, **kwargs)


class DocumentAcknowledgment(TenantModel):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="acknowledgments")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    version = models.PositiveIntegerField(default=1)
    acknowledged_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("document", "user", "version")]


class LetterTemplate(TenantModel):
    """HR letter templates using Django template syntax, e.g. {{ employee.full_name }}, {{ today }}."""

    code = models.SlugField(max_length=50)
    name = models.CharField(max_length=150)
    letter_type = models.CharField(max_length=30, choices=[
        ("appointment", "Appointment"), ("confirmation", "Confirmation"), ("promotion", "Promotion"),
        ("transfer", "Transfer"), ("employment_confirmation", "Confirmation of employment"),
        ("introduction", "Letter of introduction"), ("warning", "Warning / query"),
        ("salary", "Salary / increment"), ("exit", "Exit / release"), ("reference", "Reference"),
        ("other", "Other")], default="other")
    body_html = models.TextField()
    output_category = models.ForeignKey(DocumentCategory, null=True, blank=True, on_delete=models.SET_NULL)
    self_service = models.BooleanField(default=False, help_text="Employees may request this letter via ESS.")
    requires_approval = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = [("organization", "code")]
        ordering = ["name"]

    def __str__(self):
        return self.name


class LetterRequest(TenantModel):
    """ESS service request for a standard letter (e.g. employment confirmation for a bank/embassy)."""

    STATUS = [("pending", "Pending"), ("approved", "Approved"), ("rejected", "Rejected"),
              ("returned", "Returned"), ("cancelled", "Cancelled"), ("issued", "Issued")]
    employee = models.ForeignKey("employees.Employee", on_delete=models.CASCADE, related_name="letter_requests")
    template = models.ForeignKey(LetterTemplate, on_delete=models.PROTECT)
    addressed_to = models.CharField(max_length=255, blank=True)
    purpose = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=STATUS, default="pending")
    document = models.ForeignKey(Document, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.template.name} for {self.employee.full_name}"
