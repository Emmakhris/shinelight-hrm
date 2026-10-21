from celery import shared_task


@shared_task
def licence_reminders():
    """Remind administrators before the licence expires and while it is in its grace period."""
    from .services import reminders

    return reminders()
