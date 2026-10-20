import datetime as dt
import decimal

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils import timezone

from apps.core.context import get_current_ip, get_current_org, get_current_user

from .models import AuditChainHead, AuditLog


def _jsonable(value):
    if isinstance(value, (dt.date, dt.datetime, dt.time)):
        return value.isoformat()
    if isinstance(value, decimal.Decimal):
        return str(value)
    if hasattr(value, "pk"):
        return value.pk
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def log(action, obj=None, changes=None, message="", actor=None, organization=None, object_repr=None):
    """Append an entry to the hash-chained audit log."""
    actor = actor if actor is not None else get_current_user()
    if actor is not None and not getattr(actor, "pk", None):
        actor = None
    org = organization or get_current_org() or getattr(obj, "organization", None) or getattr(actor, "organization", None)
    org_id = getattr(org, "pk", None)
    with transaction.atomic():
        head, _ = AuditChainHead.objects.get_or_create(organization_id=org_id)
        head = AuditChainHead.objects.select_for_update().get(pk=head.pk)
        entry = AuditLog(
            organization_id=org_id,
            timestamp=timezone.now(),
            actor=actor,
            actor_repr=str(actor) if actor else "system",
            ip_address=get_current_ip(),
            action=action,
            content_type=ContentType.objects.get_for_model(obj) if obj is not None else None,
            object_id=str(obj.pk) if obj is not None and obj.pk is not None else "",
            object_repr=(object_repr or (str(obj) if obj is not None else ""))[:255],
            changes={k: _jsonable(v) for k, v in (changes or {}).items()},
            message=message,
            prev_hash=head.last_hash,
        )
        entry.hash = entry.compute_hash()
        entry.save()
        head.last_hash = entry.hash
        head.save(update_fields=["last_hash"])
    return entry


def verify_chain(organization_id=None) -> tuple[bool, int | None]:
    """Walk the chain in insertion order. Returns (ok, first_bad_entry_id)."""
    prev = ""
    for entry in AuditLog.objects.filter(organization_id=organization_id).order_by("id").iterator():
        if entry.prev_hash != prev or entry.compute_hash() != entry.hash:
            return False, entry.id
        prev = entry.hash
    head = AuditChainHead.objects.filter(organization_id=organization_id).first()
    if head and head.last_hash != prev:
        return False, None
    return True, None
