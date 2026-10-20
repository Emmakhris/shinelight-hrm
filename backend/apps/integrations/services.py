import hashlib
import hmac
import json
from datetime import timedelta

import requests
from django.db import transaction
from django.utils import timezone

from .models import Webhook, WebhookDelivery

MAX_ATTEMPTS = 6


def emit(event: str, payload: dict, organization_id=None):
    """Queue webhook deliveries for an event (sent after the DB transaction commits)."""
    hooks = Webhook.all_objects.filter(is_active=True)
    if organization_id:
        hooks = hooks.filter(organization_id=organization_id)
    for hook in hooks:
        if event not in (hook.events or []):
            continue
        delivery = WebhookDelivery.all_objects.create(organization_id=hook.organization_id, webhook=hook,
                                                      event=event, payload=payload, next_attempt_at=timezone.now())
        from .tasks import deliver_webhook

        transaction.on_commit(lambda d=delivery.id: deliver_webhook.delay(d))


def sign(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def deliver(delivery: WebhookDelivery):
    hook = delivery.webhook
    body = json.dumps({"event": delivery.event, "id": delivery.id, "data": delivery.payload,
                       "sent_at": timezone.now().isoformat()}, default=str).encode()
    delivery.attempts += 1
    try:
        resp = requests.post(hook.url, data=body, timeout=10, headers={
            "Content-Type": "application/json", "X-ShineLight-Event": delivery.event,
            "X-ShineLight-Signature": sign(hook.secret, body)})
        delivery.response_code = resp.status_code
        if 200 <= resp.status_code < 300:
            delivery.status = "success"
            delivery.error = ""
        else:
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
    except Exception as exc:
        delivery.error = str(exc)[:1000]
        if delivery.attempts >= MAX_ATTEMPTS:
            delivery.status = "failed"
        else:
            delivery.status = "pending"
            delivery.next_attempt_at = timezone.now() + timedelta(minutes=2 ** delivery.attempts)
    delivery.save()
    return delivery
