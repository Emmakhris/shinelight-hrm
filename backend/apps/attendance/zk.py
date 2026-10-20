"""ZKTeco terminal synchronisation (pull model via the `pyzk` library).

Each device is polled; new attendance logs are mapped to employees through BiometricEnrollment
and stored as ClockEvents (idempotent: duplicates are ignored)."""

import logging

from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import BiometricDevice, BiometricEnrollment, ClockEvent

logger = logging.getLogger(__name__)

# ZKTeco punch codes: 0 check-in, 1 check-out, 2 break-out, 3 break-in, 4 OT-in, 5 OT-out
PUNCH_DIRECTION = {0: "in", 1: "out", 4: "in", 5: "out"}


def sync_device(device: BiometricDevice, clear_after=False) -> dict:
    from zk import ZK

    zk = ZK(device.ip_address, port=device.port, timeout=10, password=device.comm_key, ommit_ping=True)
    conn = None
    created = skipped = unknown = 0
    try:
        conn = zk.connect()
        conn.disable_device()
        records = conn.get_attendance() or []
        mapping = dict(BiometricEnrollment.objects.filter(organization_id=device.organization_id)
                       .values_list("device_user_id", "employee_id"))
        tz = timezone.get_current_timezone()
        latest = device.last_record_at
        for rec in records:
            ts = rec.timestamp if timezone.is_aware(rec.timestamp) else timezone.make_aware(rec.timestamp, tz)
            if device.last_record_at and ts <= device.last_record_at:
                skipped += 1
                continue
            emp_id = mapping.get(str(rec.user_id))
            if emp_id is None:
                unknown += 1
                continue
            direction = device.direction if device.direction != "auto" else PUNCH_DIRECTION.get(rec.punch, "auto")
            try:
                with transaction.atomic():
                    ClockEvent.all_objects.create(organization_id=device.organization_id, employee_id=emp_id,
                                                  timestamp=ts, direction=direction, source="biometric",
                                                  device=device)
                created += 1
            except IntegrityError:
                skipped += 1
            latest = max(latest, ts) if latest else ts
        if clear_after and records:
            conn.clear_attendance()
        device.last_record_at = latest
        device.last_sync_status = f"OK: {created} new, {skipped} skipped, {unknown} unmapped"
    except Exception as exc:  # network / device errors are logged and retried next cycle
        logger.warning("ZKTeco sync failed for %s: %s", device, exc)
        device.last_sync_status = f"ERROR: {exc}"[:255]
    finally:
        if conn is not None:
            try:
                conn.enable_device()
                conn.disconnect()
            except Exception:  # pragma: no cover
                pass
        device.last_sync_at = timezone.now()
        device.save(update_fields=["last_sync_at", "last_sync_status", "last_record_at"])
    return {"created": created, "skipped": skipped, "unmapped": unknown, "status": device.last_sync_status}
