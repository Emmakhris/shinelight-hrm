from celery import shared_task


@shared_task
def relations_escalation():
    """Daily: escalate employee-relations cases past their resolution deadline."""
    from apps.core.context import org_context
    from apps.tenancy.models import Organization

    from . import services

    n = 0
    for org in Organization.objects.filter(is_active=True):
        with org_context(org):
            n += services.escalate_overdue()
    return n
