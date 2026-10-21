from celery import shared_task


@shared_task
def close_due_surveys():
    """Daily: close surveys past their closing date."""
    import datetime as dt

    from apps.core.context import org_context
    from apps.tenancy.models import Organization

    from . import services
    from .models import Survey

    n = 0
    for org in Organization.objects.filter(is_active=True):
        with org_context(org):
            for s in Survey.objects.filter(status="open", closes_on__lt=dt.date.today()):
                services.close(s)
                n += 1
    return n
