from django.db import models


class Organization(models.Model):
    """A tenant. ShineLight runs with a single organization today; every business
    record carries an organization FK so the same schema serves multi-tenant SaaS later."""

    name = models.CharField(max_length=200)
    code = models.SlugField(max_length=50, unique=True)
    legal_name = models.CharField(max_length=255, blank=True)
    tin = models.CharField("Tax Identification Number", max_length=30, blank=True)
    ssnit_employer_no = models.CharField(max_length=30, blank=True)
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    website = models.URLField(blank=True)
    logo = models.ImageField(upload_to="org/logos/", blank=True, null=True)
    currency = models.CharField(max_length=3, default="GHS")
    timezone = models.CharField(max_length=50, default="Africa/Accra")
    date_format = models.CharField(max_length=20, default="DD/MM/YYYY")
    domain = models.CharField(max_length=255, blank=True, help_text="Subdomain/host used for SaaS routing.")
    is_active = models.BooleanField(default=True)
    settings = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @classmethod
    def get_default(cls):
        return cls.objects.filter(is_active=True).order_by("id").first()

    def has_feature(self, code: str) -> bool:
        return self.features.filter(code=code, enabled=True).exists()


class OrganizationFeature(models.Model):
    """Per-tenant feature flags (e.g. hospital, payroll, sms, biometric)."""

    FEATURES = [
        ("payroll", "Payroll"),
        ("hospital", "Hospital / clinical workforce"),
        ("sms", "SMS notifications"),
        ("biometric", "Biometric attendance"),
        ("geofence", "Geofenced web clock-in"),
        ("ai_assistant", "AI HR assistant (governed)"),
    ]
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="features")
    code = models.CharField(max_length=50, choices=FEATURES)
    enabled = models.BooleanField(default=False)
    config = models.JSONField(default=dict, blank=True)

    class Meta:
        unique_together = [("organization", "code")]

    def __str__(self):
        state = "on" if self.enabled else "off"
        return f"{self.organization.code}:{self.code}={state}"
