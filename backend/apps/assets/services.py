"""Employee assets: issue, acknowledgment, transfer, return with condition, loss/damage and recovery
(features.txt §18). Kept deliberately light: detailed hardware lifecycle stays in the IT asset system, linked
through `external_ref`."""

import datetime as dt
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from apps.audit import services as audit
from apps.core.exceptions import BusinessRuleError

from .models import Asset, Assignment


def _notify(users, title, body, link):
    from apps.notifications.services import notify

    users = [u for u in users if u is not None]
    if users:
        notify("generic", users, {"title": title, "body": body, "link": link})


@transaction.atomic
def issue(user, employee, asset=None, category=None, item="", quantity=1, due_back=None, condition="good", notes=""):
    if employee.status == "exited":
        raise BusinessRuleError("Cannot issue items to an exited employee.")
    if asset is not None:
        asset = Asset.objects.select_for_update().get(pk=asset.pk)
        if asset.status != "available":
            raise BusinessRuleError(f"{asset.tag} is {asset.get_status_display().lower()}; return or repair it first.")
        category = asset.category
    elif category is None or not item:
        raise BusinessRuleError("Choose a tagged asset, or a category and item description.")
    elif category.is_tracked:
        raise BusinessRuleError(f"{category.name} items are individually tagged; choose the asset.")
    a = Assignment.objects.create(asset=asset, category=category, item=item or (asset.description if asset else ""),
                                  quantity=quantity if asset is None else 1, employee=employee,
                                  issued_on=dt.date.today(), issued_by=user, condition_out=condition,
                                  due_back=due_back, notes=notes)
    if asset is not None:
        asset.status, asset.holder = "assigned", employee
        asset.save(update_fields=["status", "holder", "updated_at"])
    _notify([employee.user], "Equipment issued to you",
            f"{a.item}{f' ({asset.tag})' if asset else ''} has been issued to you. Please acknowledge receipt.",
            "/assets/my")
    return a


def acknowledge(a: Assignment, user):
    if a.employee.user_id != user.pk:
        raise PermissionDenied()
    a.acknowledged_at = timezone.now()
    a.save(update_fields=["acknowledged_at", "updated_at"])
    return a


def report_incident(a: Assignment, user, kind, description):
    if a.employee.user_id != user.pk:
        raise PermissionDenied()
    if a.returned_on:
        raise BusinessRuleError("This item has already been returned.")
    if kind not in ("lost", "damaged") or not description:
        raise BusinessRuleError("Say whether the item was lost or damaged, and what happened.")
    a.incident_report = f"[{kind.upper()} {dt.date.today():%d/%m/%Y}] {description}"
    a.save(update_fields=["incident_report", "updated_at"])
    if a.asset_id:
        a.asset.status = kind if kind == "lost" else "damaged"
        a.asset.save(update_fields=["status", "updated_at"])
    from apps.onboarding.services import OWNER_ROLES, _role_users

    _notify(_role_users(OWNER_ROLES.get(a.category.owner, "admin_officer"), a.organization_id),
            f"{kind.title()} item reported: {a.item}", f"{a.employee.full_name}: {description}", "/assets")
    return a


@transaction.atomic
def receive(a: Assignment, user, condition, recovery_amount=None, notes="", to_payroll=False):
    """Return of an item. Lost/damaged items can be recovered from pay (with a documented amount)."""
    if a.returned_on:
        raise BusinessRuleError("Already returned.")
    if condition not in ("new", "good", "fair", "damaged", "lost"):
        raise BusinessRuleError("Record the condition.")
    a.returned_on, a.condition_in, a.received_by = dt.date.today(), condition, user
    a.notes = "\n".join(x for x in (a.notes, notes) if x)
    if condition in ("damaged", "lost"):
        amount = Decimal(str(recovery_amount if recovery_amount not in (None, "") else
                             (a.asset.replacement_value if a.asset_id else 0)))
        a.recovery_amount = amount
        a.recovery_status = "pending" if amount > 0 else "waived"
        if amount > 0 and to_payroll:
            from apps.expenses.services import _payroll_adjustment

            _payroll_adjustment(a.employee, "ASSET_RECOVERY", amount,
                                f"Recovery: {a.item}{f' ({a.asset.tag})' if a.asset_id else ''}")
            a.recovery_status = "payroll"
    a.save()
    if a.asset_id:
        asset = a.asset
        asset.holder = None
        asset.status = {"lost": "lost", "damaged": "damaged"}.get(condition, "available")
        asset.save(update_fields=["holder", "status", "updated_at"])
    audit.log("update", a.asset or a, {"action": "returned", "condition": condition,
                                       "recovery": str(a.recovery_amount)})
    return a


@transaction.atomic
def transfer(a: Assignment, user, to_employee, notes=""):
    if not a.asset_id:
        raise BusinessRuleError("Only tagged assets can be transferred.")
    receive(a, user, a.condition_out if a.condition_out in ("new", "good", "fair") else "good",
            notes=f"Transferred to {to_employee.full_name}. {notes}")
    return issue(user, to_employee, asset=a.asset, notes=f"Transferred from {a.employee.full_name}")


def outstanding(employee=None):
    qs = Assignment.objects.filter(returned_on__isnull=True, category__is_returnable=True)
    return qs.filter(employee=employee) if employee is not None else qs


def recovery_dashboard(today=None):
    today = today or dt.date.today()
    open_ = outstanding().select_related("employee", "asset", "category")
    leavers = open_.filter(Q(employee__status="exited") | Q(employee__exit_date__isnull=False))
    return {
        "assigned": open_.count(),
        "unacknowledged": open_.filter(acknowledged_at__isnull=True).count(),
        "overdue": open_.filter(due_back__lt=today).count(),
        "with_leavers": leavers.count(),
        "lost_or_damaged": Asset.objects.filter(status__in=["lost", "damaged"]).count(),
        "recovery_pending": Assignment.objects.filter(recovery_status="pending").count(),
        "leavers": [{"assignment": a.id, "employee": a.employee.full_name, "employee_id": a.employee_id,
                     "item": a.item, "tag": a.asset.tag if a.asset_id else None,
                     "exit_date": a.employee.exit_date, "value": a.asset.replacement_value if a.asset_id else None}
                    for a in leavers[:100]],
    }
