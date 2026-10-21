from celery import shared_task

from . import services


@shared_task
def run_monthly_accrual():
    from apps.core.context import org_context
    from apps.tenancy.models import Organization

    created = expired = 0
    for org in Organization.objects.filter(is_active=True):
        with org_context(org):
            created += services.run_monthly_accrual(organization=org)
            expired += services.expire_carryover(organization=org)
    return {"accrued": created, "expired": expired}
