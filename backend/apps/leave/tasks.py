from celery import shared_task

from . import services


@shared_task
def run_monthly_accrual():
    created = services.run_monthly_accrual()
    expired = services.expire_carryover()
    return {"accrued": created, "expired": expired}
