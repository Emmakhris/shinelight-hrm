from django.conf import settings
from django.db import models

from apps.core.models import TenantModel

SCOPE_CHOICES = [
    ("own", "Own records"),
    ("team", "Direct and indirect reports"),
    ("department", "Department (incl. sub-units)"),
    ("branch", "Branch"),
    ("organization", "Whole organization"),
]
SCOPE_RANK = {code: i for i, (code, _) in enumerate(SCOPE_CHOICES)}


class Permission(models.Model):
    """Global permission catalogue (seeded from rbac.catalog)."""

    code = models.CharField(max_length=80, unique=True)
    name = models.CharField(max_length=200)
    module = models.CharField(max_length=40)
    is_sensitive = models.BooleanField(default=False)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return self.code


class Role(TenantModel):
    code = models.SlugField(max_length=50)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    default_scope = models.CharField(max_length=20, choices=SCOPE_CHOICES, default="own")
    is_system = models.BooleanField(default=False)
    requires_mfa = models.BooleanField(default=False)
    permissions = models.ManyToManyField(Permission, blank=True, related_name="roles")

    class Meta:
        unique_together = [("organization", "code")]
        ordering = ["name"]

    def __str__(self):
        return self.name


class RoleAssignment(TenantModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="role_assignments")
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="assignments")
    scope = models.CharField(max_length=20, choices=SCOPE_CHOICES, blank=True, help_text="Blank = role default.")
    department = models.ForeignKey(
        "organization.Department", null=True, blank=True, on_delete=models.CASCADE,
        help_text="For department scope: limit to this department (defaults to the user's own).",
    )
    branch = models.ForeignKey("organization.Branch", null=True, blank=True, on_delete=models.CASCADE)
    valid_from = models.DateField(null=True, blank=True)
    valid_to = models.DateField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["user", "role"]

    def __str__(self):
        return f"{self.user} -> {self.role} ({self.effective_scope})"

    @property
    def effective_scope(self):
        return self.scope or self.role.default_scope
