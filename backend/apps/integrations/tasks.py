from celery import shared_task
from django.utils import timezone

from .models import WebhookDelivery
from .services import deliver


@shared_task
def deliver_webhook(delivery_id):
    delivery = WebhookDelivery.all_objects.select_related("webhook").filter(pk=delivery_id).first()
    if delivery and delivery.status == "pending":
        deliver(delivery)


@shared_task
def retry_failed_deliveries():
    due = WebhookDelivery.all_objects.filter(status="pending", next_attempt_at__lte=timezone.now(),
                                             attempts__gt=0).select_related("webhook")
    for d in due[:200]:
        deliver(d)
