from celery import shared_task


@shared_task
def onboarding_housekeeping():
    """Daily: escalate overdue onboarding tasks and remind reviewers of probation reviews."""
    from apps.core.context import org_context
    from apps.tenancy.models import Organization

    from . import services

    out = {"escalated": 0, "reminded": 0}
    for org in Organization.objects.filter(is_active=True):
        with org_context(org):
            out["escalated"] += services.escalate_overdue()
            out["reminded"] += services.remind_due_reviews()
    return out
