from celery import shared_task


@shared_task
def safety_housekeeping():
    """Daily: overdue safety actions and risk assessments due for review."""
    from apps.core.context import org_context
    from apps.tenancy.models import Organization

    from . import services

    n = 0
    for org in Organization.objects.filter(is_active=True):
        with org_context(org):
            n += services.housekeeping()
    return n
