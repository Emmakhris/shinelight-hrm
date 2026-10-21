from django.conf import settings
from django.db import models

from apps.core.fields import EncryptedCharField
from apps.core.models import TenantModel


class IdentityProvider(TenantModel):
    """An OpenID Connect identity provider (Microsoft Entra ID / Microsoft 365, Google Workspace, Okta, Keycloak...)."""

    PROTOCOLS = [("oidc", "OpenID Connect")]
    name = models.CharField(max_length=100, help_text='Shown on the sign-in button, e.g. "Microsoft 365".')
    protocol = models.CharField(max_length=10, choices=PROTOCOLS, default="oidc")
    issuer = models.URLField(help_text="Issuer URL; its /.well-known/openid-configuration must be reachable. "
                                       "Microsoft: https://login.microsoftonline.com/<tenant-id>/v2.0")
    client_id = models.CharField(max_length=255)
    client_secret = EncryptedCharField(blank=True)
    scopes = models.CharField(max_length=255, default="openid email profile")
    email_domains = models.CharField(max_length=500, help_text="Comma-separated work email domains that sign in "
                                                               "here, e.g. korlebu.gov.gh")
    email_claim = models.CharField(max_length=50, default="email",
                                   help_text='Claim holding the work email (Microsoft often uses "preferred_username").')
    allow_password_login = models.BooleanField(
        default=True, help_text="When off, staff in these domains must use SSO. Users who can manage "
                                "organization settings keep password sign-in as a break-glass route.")
    auto_create_accounts = models.BooleanField(
        default=False, help_text="Create a login on first sign-in for an existing active employee whose work "
                                 "email matches. Never creates employee records.")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def domains(self):
        return [d.strip().lower().lstrip("@") for d in self.email_domains.split(",") if d.strip()]


class ExternalIdentity(TenantModel):
    """Links a ShineLight user to the stable subject identifier issued by an identity provider."""

    provider = models.ForeignKey(IdentityProvider, on_delete=models.CASCADE, related_name="identities")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="external_identities")
    subject = models.CharField(max_length=255)
    email = models.EmailField(blank=True)
    last_login_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["provider", "subject"], name="uniq_sso_subject")]

    def __str__(self):
        return f"{self.user} @ {self.provider}"
