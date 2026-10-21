from celery import shared_task


@shared_task
def purge_assistant_conversations():
    """Delete assistant conversations past each organization's retention period."""
    from .services import purge

    return purge()
