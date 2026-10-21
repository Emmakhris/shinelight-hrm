import datetime as dt

from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMessage
from django.utils import timezone


@shared_task
def send_scheduled_reports():
    """Email scheduled reports to authorised recipients. Each recipient gets data within their own scope."""
    from apps.core.context import org_context
    from apps.core.exports import xlsx_bytes
    from apps.rbac.services import has_perm
    from apps.tenancy.models import Organization

    from .models import ScheduledReport
    from .services import get_report

    today = dt.date.today()
    sent = 0
    for org in Organization.objects.filter(is_active=True):
        with org_context(org):
            for sched in ScheduledReport.objects.filter(is_active=True):
                due = (sched.frequency == "daily" or (sched.frequency == "weekly" and today.weekday() == 0)
                       or (sched.frequency == "monthly" and today.day == 1))
                if not due:
                    continue
                for user in sched.recipients.filter(is_active=True):
                    report = get_report(sched.report_code, user)       # custom reports must be shared with them
                    if report is None or not user.email or not has_perm(user, "reports.view"):
                        continue
                    name, fn = report
                    headers, rows = fn(user, sched.params)
                    msg = EmailMessage(f"[ShineLight HRM] {sched.name} - {today:%d/%m/%Y}",
                                       f"Attached: {name}. This report contains confidential HR information.",
                                       settings.DEFAULT_FROM_EMAIL, [user.email])
                    msg.attach(f"{sched.report_code.replace(':', '-')}-{today:%Y%m%d}.xlsx", xlsx_bytes(headers, rows, name[:31]),
                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                    msg.send()
                    sent += 1
                sched.last_sent_at = timezone.now()
                sched.save(update_fields=["last_sent_at"])
    return sent
