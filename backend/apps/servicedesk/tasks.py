from celery import shared_task

from . import services


@shared_task
def process_ticket_sla():
    warned, escalated, closed = services.process_sla()
    return {"warned": warned, "escalated": escalated, "auto_closed": closed}
