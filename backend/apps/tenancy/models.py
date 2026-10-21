from django.db import models


class Plan(models.Model):
    """A subscription plan (platform-wide, not tenant data)."""

    code = models.SlugField(max_length=30, unique=True)
    name = models.CharField(max_length=100)
    max_employees = models.PositiveIntegerField(default=0, help_text="Active employees allowed; 0 = unlimited.")
    features = models.JSONField(default=list, blank=True, help_text="Feature codes the plan includes.")
    monthly_price = models.DecimalField(max_digits=12, decimal_places=2, default=0, help_text="GHS")
    trial_days = models.PositiveSmallIntegerField(default=0)
    is_public = models.BooleanField(default=True, help_text="Offered at self-service sign-up.")

    class Meta:
        ordering = ["monthly_price", "name"]

    def __str__(self):
        return self.name


class Organization(models.Model):
    """A tenant. Every business record carries an organization FK; the host name (subdomain or custom
    domain) selects the organization for a request."""

    STATUS = [("trial", "Trial"), ("active", "Active"), ("suspended", "Suspended"), ("cancelled", "Cancelled")]

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
    domain = models.CharField(max_length=255, blank=True, help_text="Custom host name, e.g. hr.example.gov.gh "
                                                                    "(the <code> subdomain always works).")
    is_active = models.BooleanField(default=True, help_text="False while suspended or cancelled.")
    status = models.CharField(max_length=10, choices=STATUS, default="active")
    suspended_reason = models.CharField(max_length=200, blank=True)
    plan = models.ForeignKey(Plan, null=True, blank=True, on_delete=models.PROTECT, related_name="organizations")
    trial_ends_at = models.DateField(null=True, blank=True)
    created_via = models.CharField(max_length=10, default="platform", choices=[("platform", "Platform operator"),
                                                                                ("signup", "Self-service sign-up")])
    settings = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @classmethod
    def get_default(cls):
        """The only organization of a single-organization deployment; None once there are several."""
        orgs = list(cls.objects.order_by("id")[:2])
        return orgs[0] if len(orgs) == 1 else None

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
