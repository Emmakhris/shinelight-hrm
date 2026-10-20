"""HR service desk: ticket lifecycle, routing, SLA tracking and service metrics.

SLA clocks run in wall-clock hours; time spent "waiting on employee" is paused and added back
to both due times when the ticket resumes."""

import datetime as dt
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from apps.audit import services as audit
from apps.core.exceptions import BusinessRuleError
from apps.core.services import next_number
from apps.notifications.services import notify
from apps.rbac.models import RoleAssignment
from apps.rbac.services import has_perm

from .models import Ticket, TicketComment, TicketEvent

User = get_user_model()
OPEN = ["new", "open", "pending_employee"]
REOPEN_WINDOW_DAYS = 14
AUTO_CLOSE_DAYS = 5
PRIORITY_FACTOR = {"urgent": 0.25, "high": 0.5, "normal": 1.0, "low": 1.5}


def _event(ticket, event, actor=None, detail=""):
    TicketEvent.objects.create(ticket=ticket, actor=actor, event=event, detail=detail[:255])


def is_agent(user):
    return has_perm(user, "servicedesk.agent") or has_perm(user, "servicedesk.manage")


def route(service_type):
    """Pick the default assignee, else the active team member with the fewest open tickets."""
    if service_type.default_assignee_id and service_type.default_assignee.is_active:
        return service_type.default_assignee
    if not service_type.team_role_id:
        return None
    today = dt.date.today()
    users = [ra.user for ra in RoleAssignment.objects.filter(role=service_type.team_role, user__is_active=True)
             .filter(Q(valid_to__isnull=True) | Q(valid_to__gte=today)).select_related("user")]
    if not users:
        return None
    load = dict(Ticket.objects.filter(assignee__in=users, status__in=OPEN).values_list("assignee")
                .annotate(n=Count("id")))
    return min(users, key=lambda u: (load.get(u.id, 0), u.id))


@transaction.atomic
def create_ticket(service_type, requester, subject, description, employee=None, priority=None, form_data=None,
                  channel="portal"):
    if not service_type.is_active:
        raise BusinessRuleError("This service is not available.")
    missing = [f["label"] for f in service_type.form_fields or [] if f.get("required") and not (form_data or {}).get(f["name"])]
    if missing:
        raise BusinessRuleError(f"Please provide: {', '.join(missing)}.")
    priority = priority or service_type.default_priority
    factor = PRIORITY_FACTOR.get(priority, 1.0)
    now = timezone.now()
    if employee is None:
        employee = getattr(requester, "employee", None)
    ticket = Ticket.objects.create(
        reference=next_number("hr_ticket", default_prefix="HR", default_pattern="{prefix}-{year}-{seq:05d}"),
        service_type=service_type, requester=requester, employee=employee, subject=subject[:200],
        description=description, form_data=form_data or {}, priority=priority, channel=channel,
        is_confidential=service_type.is_confidential,
        response_due=now + timedelta(hours=service_type.response_sla_hours * factor),
        resolution_due=now + timedelta(hours=service_type.resolution_sla_hours * factor),
    )
    _event(ticket, "created", requester, f"via {channel}")
    assignee = route(service_type)
    if assignee:
        _assign(ticket, assignee, None)
    notify("generic", [requester], {"title": f"Request received: {ticket.reference}",
                                    "body": f"We have received your request '{ticket.subject}'. "
                                            f"Expected resolution by {timezone.localtime(ticket.resolution_due):%d/%m/%Y %H:%M}.",
                                    "link": f"/helpdesk/tickets/{ticket.id}"})
    return ticket


def _assign(ticket, user, actor):
    ticket.assignee = user
    if ticket.status == "new":
        ticket.status = "open"
    ticket.save(update_fields=["assignee", "status", "updated_at"])
    _event(ticket, "assigned", actor, str(user))
    notify("generic", [user], {"title": f"Ticket assigned: {ticket.reference}", "body": ticket.subject,
                               "link": f"/helpdesk/tickets/{ticket.id}"})


@transaction.atomic
def assign(ticket, user, actor):
    if not is_agent(user):
        raise BusinessRuleError("Tickets can only be assigned to service desk agents.")
    _assign(ticket, user, actor)
    return ticket


@transaction.atomic
def add_comment(ticket, author, body, internal=False, attachment=None):
    agent = is_agent(author)
    if internal and not agent:
        raise BusinessRuleError("Only HR staff can add internal notes.")
    if ticket.status in ("closed", "cancelled"):
        raise BusinessRuleError("This ticket is closed. Reopen it or raise a new request.")
    c = TicketComment.objects.create(ticket=ticket, author=author, body=body, is_internal=internal,
                                     attachment=attachment)
    now = timezone.now()
    if agent and not internal and author != ticket.requester:
        if ticket.first_response_at is None:
            ticket.first_response_at = now
            ticket.response_breached = bool(ticket.response_due and now > ticket.response_due)
        if ticket.status == "new":
            ticket.status = "open"
        ticket.save()
        notify("generic", [ticket.requester], {"title": f"Update on {ticket.reference}", "body": body[:300],
                                               "link": f"/helpdesk/tickets/{ticket.id}"})
    elif not agent or author == ticket.requester:
        if ticket.status == "pending_employee":
            _resume(ticket)
        if ticket.assignee_id:
            notify("generic", [ticket.assignee], {"title": f"Employee replied: {ticket.reference}", "body": body[:300],
                                                  "link": f"/helpdesk/tickets/{ticket.id}"})
    return c


def _resume(ticket):
    if ticket.paused_since:
        paused = timezone.now() - ticket.paused_since
        ticket.paused_seconds += int(paused.total_seconds())
        if ticket.resolution_due:
            ticket.resolution_due += paused
        if ticket.response_due and not ticket.first_response_at:
            ticket.response_due += paused
        ticket.paused_since = None
    ticket.status = "open"
    ticket.save()
    _event(ticket, "resumed")


@transaction.atomic
def set_status(ticket, status, actor, note=""):
    if not is_agent(actor):
        raise BusinessRuleError("Only HR staff can change ticket status.")
    if status == "pending_employee":
        ticket.status = "pending_employee"
        ticket.paused_since = timezone.now()
        ticket.save()
        if note:
            add_comment(ticket, actor, note)
        notify("generic", [ticket.requester], {"title": f"Action needed on {ticket.reference}",
                                               "body": note or "HR needs more information from you.",
                                               "link": f"/helpdesk/tickets/{ticket.id}"})
    elif status == "open":
        _resume(ticket)
    else:
        raise BusinessRuleError("Use resolve, close or cancel for that status change.")
    _event(ticket, f"status:{status}", actor, note)
    return ticket


@transaction.atomic
def resolve(ticket, actor, resolution):
    if not is_agent(actor):
        raise BusinessRuleError("Only HR staff can resolve tickets.")
    if ticket.status not in OPEN:
        raise BusinessRuleError("Ticket is not open.")
    if not resolution.strip():
        raise BusinessRuleError("Describe how the request was resolved.")
    if ticket.paused_since:
        _resume(ticket)
    now = timezone.now()
    ticket.status = "resolved"
    ticket.resolution = resolution
    ticket.resolved_at = now
    if ticket.first_response_at is None:
        ticket.first_response_at = now
        ticket.response_breached = bool(ticket.response_due and now > ticket.response_due)
    # a breach already recorded (e.g. by the SLA job) is never cleared
    ticket.resolution_breached = ticket.resolution_breached or bool(ticket.resolution_due and now > ticket.resolution_due)
    ticket.save()
    _event(ticket, "resolved", actor)
    audit.log("update", ticket, {"status": "resolved"})
    notify("generic", [ticket.requester], {"title": f"Resolved: {ticket.reference}",
                                           "body": f"{resolution[:250]} — please rate the service.",
                                           "link": f"/helpdesk/tickets/{ticket.id}"})
    return ticket


@transaction.atomic
def reopen(ticket, actor, reason):
    if ticket.status != "resolved" and not (ticket.status == "closed" and is_agent(actor)):
        raise BusinessRuleError("Only resolved tickets can be reopened.")
    if actor != ticket.requester and not is_agent(actor):
        raise BusinessRuleError("Not permitted.")
    if ticket.resolved_at and timezone.now() - ticket.resolved_at > timedelta(days=REOPEN_WINDOW_DAYS) \
            and not is_agent(actor):
        raise BusinessRuleError(f"Tickets can be reopened within {REOPEN_WINDOW_DAYS} days. Please raise a new request.")
    if not reason.strip():
        raise BusinessRuleError("Tell us why the issue is not resolved.")
    ticket.status = "open"
    ticket.reopen_count += 1
    ticket.resolved_at = None
    ticket.closed_at = None
    ticket.rating = None
    ticket.resolution_due = timezone.now() + timedelta(hours=ticket.service_type.resolution_sla_hours
                                                       * PRIORITY_FACTOR.get(ticket.priority, 1))
    ticket.resolution_breached = False
    ticket.save()
    add_comment(ticket, actor, f"Reopened: {reason}")
    _event(ticket, "reopened", actor, reason)
    return ticket


@transaction.atomic
def rate(ticket, user, rating, feedback=""):
    if user != ticket.requester:
        raise BusinessRuleError("Only the requester can rate this ticket.")
    if ticket.status not in ("resolved", "closed"):
        raise BusinessRuleError("You can rate once the request is resolved.")
    if not 1 <= int(rating) <= 5:
        raise BusinessRuleError("Rating must be 1 to 5.")
    ticket.rating = int(rating)
    ticket.feedback = feedback
    if ticket.status == "resolved":
        ticket.status = "closed"
        ticket.closed_at = timezone.now()
    ticket.save()
    _event(ticket, "rated", user, f"{rating}/5")
    return ticket


@transaction.atomic
def cancel(ticket, user, reason=""):
    if ticket.status not in OPEN:
        raise BusinessRuleError("Only open tickets can be cancelled.")
    if user != ticket.requester and not has_perm(user, "servicedesk.manage"):
        raise BusinessRuleError("Not permitted.")
    ticket.status = "cancelled"
    ticket.closed_at = timezone.now()
    ticket.save()
    _event(ticket, "cancelled", user, reason)
    return ticket


def process_sla(now=None):
    """Warn agents at 80% of the resolution SLA, escalate on breach, auto-close resolved tickets."""
    from apps.core.context import org_context
    from apps.tenancy.models import Organization

    now = now or timezone.now()
    warned = escalated = closed = 0
    for org in Organization.objects.filter(is_active=True):
        with org_context(org):
            for t in Ticket.objects.filter(status__in=["new", "open"], resolution_due__isnull=False).select_related(
                    "service_type", "assignee"):
                total = t.resolution_due - t.created_at
                remaining = t.resolution_due - now
                if remaining <= timedelta(0) and t.escalated_at is None:
                    t.resolution_breached = True
                    t.escalated_at = now
                    t.save(update_fields=["resolution_breached", "escalated_at"])
                    managers = [u for u in User.objects.filter(organization=org, is_active=True)
                                if has_perm(u, "servicedesk.manage")]
                    notify("generic", managers + ([t.assignee] if t.assignee else []),
                           {"title": f"SLA breached: {t.reference}", "body": t.subject,
                            "link": f"/helpdesk/tickets/{t.id}"})
                    _event(t, "escalated", None, "Resolution SLA exceeded")
                    escalated += 1
                elif t.warned_at is None and remaining <= total * 0.2 and t.assignee:
                    t.warned_at = now
                    t.save(update_fields=["warned_at"])
                    notify("generic", [t.assignee], {"title": f"Due soon: {t.reference}", "body": t.subject,
                                                     "link": f"/helpdesk/tickets/{t.id}"})
                    warned += 1
                if t.first_response_at is None and t.response_due and now > t.response_due and not t.response_breached:
                    t.response_breached = True
                    t.save(update_fields=["response_breached"])
            cutoff = now - timedelta(days=AUTO_CLOSE_DAYS)
            for t in Ticket.objects.filter(status="resolved", resolved_at__lt=cutoff):
                t.status = "closed"
                t.closed_at = now
                t.save(update_fields=["status", "closed_at"])
                _event(t, "auto_closed")
                closed += 1
    return warned, escalated, closed


def metrics(qs, since=None):
    """Service KPIs: volume, backlog, response/resolution times, SLA compliance, CSAT, per agent."""
    since = since or (timezone.now() - timedelta(days=90))
    period = qs.filter(created_at__gte=since)
    resolved = period.filter(resolved_at__isnull=False)

    def avg_hours(items, start, end):
        vals = [(getattr(t, end) - getattr(t, start)).total_seconds() / 3600 - t.paused_seconds / 3600
                for t in items if getattr(t, end) and getattr(t, start)]
        return round(sum(vals) / len(vals), 1) if vals else None

    resolved_list = list(resolved.only("created_at", "resolved_at", "first_response_at", "paused_seconds",
                                       "resolution_breached", "rating", "assignee_id"))
    rated = [t.rating for t in resolved_list if t.rating]
    per_agent = []
    for row in period.values("assignee", "assignee__first_name", "assignee__last_name").annotate(
            total=Count("id"), open=Count("id", filter=Q(status__in=OPEN)),
            done=Count("id", filter=Q(resolved_at__isnull=False))):
        mine = [t for t in resolved_list if t.assignee_id == row["assignee"]]
        per_agent.append({"agent": f"{row['assignee__first_name'] or ''} {row['assignee__last_name'] or ''}".strip()
                          or "Unassigned", "total": row["total"], "open": row["open"], "resolved": row["done"],
                          "avg_resolution_hours": avg_hours(mine, "created_at", "resolved_at"),
                          "sla_percent": round(100 * sum(not t.resolution_breached for t in mine) / len(mine), 1)
                          if mine else None})
    by_category = list(period.values("service_type__category__name").annotate(n=Count("id")).order_by("-n"))
    by_channel = list(period.values("channel").annotate(n=Count("id")).order_by("-n"))
    return {
        "period_days": (timezone.now() - since).days,
        "created": period.count(),
        "backlog": qs.filter(status__in=OPEN).count(),
        "overdue": qs.filter(status__in=["new", "open"], resolution_due__lt=timezone.now()).count(),
        "resolved": len(resolved_list),
        "avg_first_response_hours": avg_hours(resolved_list, "created_at", "first_response_at"),
        "avg_resolution_hours": avg_hours(resolved_list, "created_at", "resolved_at"),
        "sla_compliance_percent": round(100 * sum(not t.resolution_breached for t in resolved_list)
                                        / len(resolved_list), 1) if resolved_list else None,
        "csat_average": round(sum(rated) / len(rated), 2) if rated else None,
        "csat_responses": len(rated),
        "reopened": period.filter(reopen_count__gt=0).count(),
        "self_service_percent": round(100 * period.filter(channel="portal").count() / period.count(), 1)
        if period.count() else None,
        "by_category": [{"label": r["service_type__category__name"], "value": r["n"]} for r in by_category],
        "by_channel": [{"label": r["channel"], "value": r["n"]} for r in by_channel],
        "agents": per_agent,
    }
