from celery import shared_task


@shared_task
def learning_housekeeping():
    """Daily: assign due mandatory training and send training reminders."""
    from apps.core.context import org_context
    from apps.tenancy.models import Organization

    from . import services

    out = {"assigned": 0, "reminders": 0}
    for org in Organization.objects.filter(is_active=True):
        with org_context(org):
            out["assigned"] += services.assign_mandatory()
            out["reminders"] += services.reminders()
    return out
