from django.conf import settings
from django.db import models

from .context import get_current_org, get_current_user


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", editable=False
    )

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self.pk and not self.created_by_id:
            user = get_current_user()
            if user is not None and getattr(user, "pk", None):
                self.created_by_id = user.pk
        super().save(*args, **kwargs)


class TenantQuerySet(models.QuerySet):
    def for_org(self, org):
        return self.filter(organization=org)


class TenantManager(models.Manager.from_queryset(TenantQuerySet)):
    """Filters automatically by the organization in the current request context.
    Outside a request (migrations, shell, celery without context) it is unfiltered."""

    def get_queryset(self):
        qs = super().get_queryset()
        org = get_current_org()
        if org is not None:
            qs = qs.filter(organization=org)
        return qs


class TenantModel(TimeStampedModel):
    organization = models.ForeignKey("tenancy.Organization", on_delete=models.CASCADE, related_name="+", editable=False)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self.organization_id:
            org = get_current_org()
            org_id = org.pk if org is not None else self._parent_org_id()
            if org_id is None:
                from apps.tenancy.models import Organization

                default = Organization.get_default()
                if default is None:
                    raise RuntimeError(f"No organization for new {type(self).__name__}: run the code inside "
                                       "org_context(org) or set organization explicitly.")
                org_id = default.pk
            self.organization_id = org_id
        super().save(*args, **kwargs)

    def _parent_org_id(self):
        """Take the organization from a tenant-scoped parent (e.g. a leave entry's employee)."""
        for f in self._meta.concrete_fields:
            if f.is_relation and (f.many_to_one or f.one_to_one) and f.name != "organization" and getattr(self, f.attname, None) \
                    and issubclass(f.related_model, TenantModel):
                return getattr(self, f.name).organization_id
        return None


class PublicHoliday(TenantModel):
    """Organization calendar. Seeded with Ghana statutory public holidays."""

    name = models.CharField(max_length=120)
    date = models.DateField()
    is_recurring = models.BooleanField(default=False, help_text="Falls on the same day every year (e.g. 1 January).")

    class Meta:
        ordering = ["date"]
        unique_together = [("organization", "date", "name")]

    def __str__(self):
        return f"{self.name} ({self.date:%d/%m/%Y})"


class NumberSequence(TenantModel):
    """Configurable numbering rules, e.g. staff IDs pattern '{prefix}{year}{seq:04d}'."""

    key = models.CharField(max_length=50)
    pattern = models.CharField(max_length=100, default="{prefix}{seq:05d}")
    prefix = models.CharField(max_length=20, blank=True)
    next_value = models.PositiveIntegerField(default=1)
    reset_yearly = models.BooleanField(default=False)
    last_year = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        unique_together = [("organization", "key")]

    def __str__(self):
        return self.key


class CustomFieldDefinition(TenantModel):
    """HR-configurable extra fields for employees and other entities."""

    TYPES = [("text", "Text"), ("number", "Number"), ("date", "Date"), ("bool", "Yes/No"), ("choice", "Choice")]
    entity = models.CharField(max_length=50, default="employee")
    key = models.SlugField(max_length=50)
    label = models.CharField(max_length=100)
    field_type = models.CharField(max_length=10, choices=TYPES, default="text")
    choices = models.JSONField(default=list, blank=True)
    required = models.BooleanField(default=False)
    is_sensitive = models.BooleanField(default=False)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        unique_together = [("organization", "entity", "key")]
        ordering = ["entity", "order"]

    def __str__(self):
        return self.label


class ConfigChange(TenantModel):
    """Versioned history of administrative configuration changes (review / rollback)."""

    area = models.CharField(max_length=50)
    object_repr = models.CharField(max_length=255)
    before = models.JSONField(null=True, blank=True)
    after = models.JSONField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
