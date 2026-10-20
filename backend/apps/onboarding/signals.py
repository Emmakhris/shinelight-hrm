import datetime as dt

from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.employees.models import Employee


@receiver(post_save, sender=Employee, dispatch_uid="onboarding_auto_start")
def auto_start_onboarding(sender, instance, created, raw=False, **kwargs):
    """New hires get their onboarding checklist automatically (skipped for historical records/imports
    with old hire dates and when no template is configured)."""
    if not created or raw or instance.status == "exited":
        return
    if instance.hire_date < dt.date.today() - dt.timedelta(days=30):
        return
    from apps.core.exceptions import BusinessRuleError

    from . import services

    if services.choose_template(instance) is None:
        return
    try:
        services.start(instance)
    except BusinessRuleError:
        pass
