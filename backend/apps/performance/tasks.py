from celery import shared_task


@shared_task
def performance_reminders():
    """Daily: deadline reminders for appraisal steps and improvement plans ending soon."""
    from apps.core.context import org_context
    from apps.tenancy.models import Organization

    from . import services

    n = 0
    for org in Organization.objects.filter(is_active=True):
        with org_context(org):
            n += services.reminders()
    return n
