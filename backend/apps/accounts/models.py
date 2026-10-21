from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models
from django.utils import timezone


class User(AbstractUser):
    """Login account. Linked 1:1 to an Employee (Employee.user) for staff; service accounts may have none.
    No shared accounts: every HR officer has an individual login (features.txt section 24)."""

    organization = models.ForeignKey("tenancy.Organization", null=True, on_delete=models.PROTECT, related_name="users")
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    must_change_password = models.BooleanField(default=False)
    mfa_enabled = models.BooleanField(default=False)
    failed_login_count = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    password_changed_at = models.DateTimeField(null=True, blank=True)
    preferences = models.JSONField(default=dict, blank=True)
    is_platform_admin = models.BooleanField(
        default=False, help_text="Platform operator (no organization): manages organizations and plans, "
                                 "never sees HR data.")

    objects = UserManager()

    class Meta:
        ordering = ["username"]

    def __str__(self):
        return self.get_full_name() or self.username

    @property
    def is_locked(self):
        return bool(self.locked_until and self.locked_until > timezone.now())

    def requires_mfa(self) -> bool:
        if self.mfa_enabled:
            return True
        return self.role_assignments.filter(role__requires_mfa=True).exists()


class LoginAttempt(models.Model):
    """Login monitoring: every success/failure with IP and user agent."""

    username = models.CharField(max_length=150, db_index=True)
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="login_attempts")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    success = models.BooleanField(default=False)
    reason = models.CharField(max_length=50, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-timestamp"]
