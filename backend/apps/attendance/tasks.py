import datetime as dt

from celery import shared_task

from apps.core.context import org_context
from apps.tenancy.models import Organization


@shared_task
def sync_all_devices():
    from .models import BiometricDevice
    from .zk import sync_device

    results = {}
    for device in BiometricDevice.all_objects.filter(is_active=True):
        org = Organization.objects.get(pk=device.organization_id)
        if not org.has_feature("biometric"):
            continue
        with org_context(org):
            results[device.name] = sync_device(device)
    return results


@shared_task
def process_previous_day():
    """Nightly: build yesterday's attendance, flag missing punches, apply due personnel actions and exits."""
    from apps.employees.services import apply_due_records, process_due_exits
    from apps.notifications.services import notify

    from .services import process_range

    yesterday = dt.date.today() - dt.timedelta(days=1)
    apply_due_records()
    process_due_exits()
    for org in Organization.objects.filter(is_active=True):
        with org_context(org):
            process_range(yesterday, yesterday)
            from .models import AttendanceDay

            for day in AttendanceDay.objects.filter(date=yesterday, status="incomplete").select_related("employee__user"):
                if day.employee.user_id:
                    notify("attendance.missing_punch", [day.employee.user], {"date": yesterday,
                                                                             "link": "/attendance/my"})
