from celery import shared_task


@shared_task
def expire_trials():
    """Warn before trials end and suspend organizations whose trial has ended."""
    from .services import expire_trials as run

    return run()
