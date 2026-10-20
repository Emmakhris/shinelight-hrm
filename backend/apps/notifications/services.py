from django.template import Context, Template

from apps.core.context import get_current_org

from .defaults import DEFAULTS
from .models import Notification, NotificationTemplate

# Events that may also go out by SMS when the org has the "sms" feature enabled.
SMS_EVENTS = {"workflow.task_assigned", "workflow.approved", "workflow.rejected", "leave.recalled",
              "payroll.payslip_ready", "expiry.license"}


def _render(text, context):
    return Template(text).render(Context(context, autoescape=False)).strip()


def _template(event_code, channel, department=None):
    qs = NotificationTemplate.objects.filter(event_code=event_code, channel=channel, is_active=True)
    if department is not None:
        t = qs.filter(department=department).first()
        if t:
            return t
    return qs.filter(department__isnull=True).first()


def render_event(event_code, channel, context, department=None):
    tpl = _template(event_code, channel, department)
    default = DEFAULTS.get(event_code, DEFAULTS["generic"])
    if tpl:
        return _render(tpl.subject or default.get("title", ""), context), _render(tpl.body, context)
    if channel == "sms":
        sms = default.get("sms")
        return "", _render(sms, context) if sms else ""
    return _render(default["title"], context), _render(default["body"], context)


def notify(event_code, users, context=None, related=None, channels=("in_app", "email", "sms")):
    """Notify users of an event across channels. Email/SMS go through Celery."""
    from .tasks import send_email_task, send_sms_task

    context = dict(context or {})
    org = get_current_org()
    if org:
        context.setdefault("organization", org.name)
    sms_enabled = bool(org and org.has_feature("sms"))
    sent = []
    for user in {u for u in users if u is not None and getattr(u, "is_active", False)}:
        emp = getattr(user, "employee", None)
        dept = emp.department if emp and emp.department_id else None
        title, body = render_event(event_code, "in_app", context, dept)
        if "in_app" in channels:
            n = Notification.objects.create(
                organization=user.organization or org, recipient=user, event_code=event_code, title=title[:200],
                body=body, link=context.get("link", "") or "",
                related_type=related._meta.label_lower if related is not None else "",
                related_id=str(related.pk) if related is not None else "",
            )
            sent.append(n)
        prefs = user.preferences.get("notifications", {}) if isinstance(user.preferences, dict) else {}
        if "email" in channels and user.email and prefs.get("email", True):
            subject, text = render_event(event_code, "email", context, dept)
            send_email_task.delay(user.email, subject or title, text or body, event_code,
                                  (user.organization_id or getattr(org, "id", None)))
        if "sms" in channels and sms_enabled and event_code in SMS_EVENTS and user.phone and prefs.get("sms", True):
            _, sms_text = render_event(event_code, "sms", context, dept)
            if sms_text:
                send_sms_task.delay(user.phone, sms_text, event_code,
                                    (user.organization_id or getattr(org, "id", None)))
    return sent
