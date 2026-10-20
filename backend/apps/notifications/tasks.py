import datetime as dt
import logging

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail

from .models import DeliveryLog

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_email_task(self, to, subject, body, event_code="", organization_id=None):
    log = DeliveryLog.all_objects.create(organization_id=organization_id, channel="email", recipient=to,
                                         event_code=event_code)
    try:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [to])
        log.status = "sent"
    except Exception as exc:  # pragma: no cover - network
        log.status = "failed"
        log.error = str(exc)
        log.save()
        raise self.retry(exc=exc) from exc
    log.save()


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_sms_task(self, to, message, event_code="", organization_id=None):
    from .sms import send_sms

    log = DeliveryLog.all_objects.create(organization_id=organization_id, channel="sms", recipient=to,
                                         event_code=event_code)
    try:
        log.provider_ref = send_sms(to, message)
        log.status = "sent"
    except Exception as exc:  # pragma: no cover - network
        log.status = "failed"
        log.error = str(exc)
        log.save()
        raise self.retry(exc=exc) from exc
    log.save()


@shared_task
def send_expiry_reminders(days_ahead=(60, 30, 14, 7, 1)):
    """Daily: contract, probation, document and licence expiry reminders to HR, the employee's
    supervisor and (for documents/licences) the employee."""
    from apps.core.context import org_context
    from apps.documents.models import Document
    from apps.employees.models import ACTIVE_STATUSES, Employee
    from apps.rbac.services import has_perm
    from apps.tenancy.models import Organization

    from .services import notify

    today = dt.date.today()
    targets = [today + dt.timedelta(days=d) for d in days_ahead]
    for org in Organization.objects.filter(is_active=True):
        with org_context(org):
            hr_users = [u for u in org.users.filter(is_active=True) if has_perm(u, "employees.change")]
            active = Employee.objects.filter(status__in=ACTIVE_STATUSES)
            for emp in active.filter(contract_end_date__in=targets):
                recipients = hr_users + ([emp.supervisor.user] if emp.supervisor_id and emp.supervisor.user_id else [])
                notify("expiry.contract", recipients, {"employee": emp.full_name, "date": emp.contract_end_date,
                                                       "link": f"/employees/{emp.id}"}, related=emp)
            for emp in active.filter(probation_end_date__in=targets, confirmation_date__isnull=True):
                recipients = hr_users + ([emp.supervisor.user] if emp.supervisor_id and emp.supervisor.user_id else [])
                notify("expiry.probation", recipients, {"employee": emp.full_name, "date": emp.probation_end_date,
                                                        "link": f"/employees/{emp.id}"}, related=emp)
            for doc in Document.objects.filter(expiry_date__in=targets, is_archived=False,
                                               employee__status__in=ACTIVE_STATUSES).select_related("employee"):
                recipients = list(hr_users)
                if doc.employee and doc.employee.user_id:
                    recipients.append(doc.employee.user)
                notify("expiry.document", recipients, {"document": doc.title, "employee": doc.employee.full_name
                                                       if doc.employee else "", "date": doc.expiry_date}, related=doc)
            if org.has_feature("hospital"):
                from apps.hospital.services import send_license_reminders

                send_license_reminders(targets, hr_users)
            _celebrations(org, today)


def _celebrations(org, today):
    from apps.employees.models import ACTIVE_STATUSES, Employee

    from .services import notify

    if not org.settings.get("celebration_notifications", False):
        return
    for emp in Employee.objects.filter(status__in=ACTIVE_STATUSES, user__isnull=False,
                                       date_of_birth__month=today.month, date_of_birth__day=today.day):
        notify("celebration.birthday", [emp.user], {"name": emp.first_name}, channels=("in_app",))
    for emp in Employee.objects.filter(status__in=ACTIVE_STATUSES, user__isnull=False,
                                       hire_date__month=today.month, hire_date__day=today.day,
                                       hire_date__lt=today):
        years = today.year - emp.hire_date.year
        notify("celebration.anniversary", [emp.user], {"name": emp.first_name, "years": years}, channels=("in_app",))
