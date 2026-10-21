"""Multi-organization (SaaS) operations: provisioning, plans and limits, access checks, trial expiry.

The platform operator manages organizations, not people's HR records: nothing here reads employee data
beyond counts.
"""

import datetime as dt
import re
import secrets

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from rest_framework import exceptions

from apps.core.exceptions import BusinessRuleError

from .models import Organization, OrganizationFeature, Plan
from .resolver import RESERVED_CODES, forget, is_cloud, request_tenant

CODE_RE = re.compile(r"^[a-z][a-z0-9-]{2,39}$")
# Endpoints an account with no organization (a platform operator) may call.
PLATFORM_PATHS = ("/api/platform/", "/api/auth/")


# ---------------------------------------------------------------- request access
def check_access(request, user):
    """Called by every authentication class once the user is known."""
    org = user.organization
    if org is None:
        if not request.path.startswith(PLATFORM_PATHS):
            raise exceptions.PermissionDenied("This account is not part of an organization.")
        return
    if not org.is_active:
        raise exceptions.AuthenticationFailed("Your organization's access is suspended. Please contact your "
                                              "administrator.", code="org_suspended")
    tenant = request_tenant(request)
    if tenant is not None and tenant.pk != org.pk:
        raise exceptions.AuthenticationFailed("This account belongs to a different organization.",
                                              code="wrong_organization")


def is_platform_admin(user):
    return bool(user and user.is_authenticated and user.organization_id is None
                and getattr(user, "is_platform_admin", False))


# ---------------------------------------------------------------- provisioning
def validate_code(code, exclude_pk=None):
    code = (code or "").strip().lower()
    if not CODE_RE.match(code):
        raise BusinessRuleError("Use 3-40 lowercase letters, numbers or hyphens, starting with a letter.",
                                code="org_code")
    if code in RESERVED_CODES:
        raise BusinessRuleError("That address is reserved. Choose another.", code="org_code")
    if Organization.objects.filter(code=code).exclude(pk=exclude_pk).exists():
        raise BusinessRuleError("That address is already taken.", code="org_code")
    return code


def login_url(org):
    base = getattr(settings, "SAAS_BASE_DOMAIN", "")
    if org.domain:
        return f"https://{org.domain}/login"
    if base:
        return f"https://{org.code}.{base}/login"
    from urllib.parse import urlsplit

    front = urlsplit(settings.FRONTEND_URL)
    if front.hostname in ("localhost", "127.0.0.1"):            # development: <code>.localhost
        return f"{front.scheme}://{org.code}.localhost{f':{front.port}' if front.port else ''}/login"
    return f"{settings.FRONTEND_URL.rstrip('/')}/login"


@transaction.atomic
def provision(name, code, admin_username, admin_email, admin_password=None, plan=None, status="active",
              created_via="platform", require_mfa=True):
    """Create an organization with its default configuration and a first administrator."""
    from django.contrib.auth import get_user_model

    from apps.core.setup import setup_organization

    if not is_cloud():
        raise BusinessRuleError("Adding organizations is only available in the cloud edition.", code="edition")
    code = validate_code(code)
    User = get_user_model()
    if User.objects.filter(username__iexact=admin_username).exists():
        raise BusinessRuleError("That administrator username is already in use. Choose another.",
                                code="username_taken")
    plan = plan or Plan.objects.filter(code=getattr(settings, "SAAS_DEFAULT_PLAN", "trial")).first()
    temp = None
    if not admin_password:
        temp = admin_password = secrets.token_urlsafe(12)
    features = list(plan.features) if plan else ["payroll"]
    org, admin = setup_organization(name, code, admin_username, admin_password, admin_email,
                                    features=[f for f in features if f != "ai_assistant"] or ["payroll"],
                                    require_mfa=require_mfa)
    org.plan = plan
    org.status = status
    org.created_via = created_via
    org.email = admin_email
    if status == "trial" and plan and plan.trial_days:
        org.trial_ends_at = dt.date.today() + dt.timedelta(days=plan.trial_days)
    org.save()
    if temp:
        admin.must_change_password = True
        admin.save(update_fields=["must_change_password"])
    if admin_email:
        body = (f"Welcome to ShineLight HRM.\n\nYour organization \"{name}\" is ready at {login_url(org)}\n"
                f"Administrator username: {admin_username}\n")
        if temp:
            body += f"Temporary password: {temp}\nYou will be asked to change it when you first sign in.\n"
        send_mail("Your ShineLight HRM organization is ready", body, settings.DEFAULT_FROM_EMAIL, [admin_email])
    return org, admin


def set_status(org, status, reason=""):
    org.status = status
    org.is_active = status in ("trial", "active")
    org.suspended_reason = reason if not org.is_active else ""
    org.save(update_fields=["status", "is_active", "suspended_reason"])
    forget(org)
    return org


# ---------------------------------------------------------------- plans and limits
def employee_cap(org):
    """(cap, source) for active employees: the plan in the cloud edition, the licence when self-hosted."""
    if not is_cloud():
        from apps.licensing.services import employee_cap as licence_cap

        return licence_cap(), "licence"
    plan = org.plan if org else None
    return (plan.max_employees if plan else None) or None, "plan"


def employee_limit_reached(org):
    from apps.employees.models import ACTIVE_STATUSES, Employee

    cap, _ = employee_cap(org)
    if not cap or org is None:
        return False
    return Employee.all_objects.filter(organization=org, status__in=ACTIVE_STATUSES).count() >= cap


def check_employee_limit(org):
    if employee_limit_reached(org):
        cap, source = employee_cap(org)
        if source == "licence":
            raise BusinessRuleError(f"Your licence allows up to {cap} active employees. Contact your ShineLight "
                                    f"provider to extend it.", code="licence_limit")
        raise BusinessRuleError(f"Your {org.plan.name} plan allows up to {cap} active employees. Upgrade the plan "
                                f"to add more.", code="plan_limit")


def check_feature_allowed(org, code):
    label = dict(OrganizationFeature.FEATURES).get(code, code)
    if not is_cloud():
        from apps.licensing.services import feature_allowed

        if not feature_allowed(code):
            raise BusinessRuleError(f"{label} is not included in your licence.", code="licence_feature")
        return
    if org.plan_id and code not in (org.plan.features or []):
        raise BusinessRuleError(f"{label} is not included in the {org.plan.name} plan.", code="plan_feature")


def apply_plan(org, plan):
    """Move an organization to a plan: switch off features the plan doesn't include."""
    org.plan = plan
    org.save(update_fields=["plan"])
    if plan is not None:
        OrganizationFeature.objects.filter(organization=org).exclude(code__in=plan.features).update(enabled=False)
    return org


def usage(org):
    """Counts only - never HR content."""
    from django.contrib.auth import get_user_model

    from apps.employees.models import ACTIVE_STATUSES, Employee

    User = get_user_model()
    users = User.objects.filter(organization=org)
    last = users.exclude(last_login__isnull=True).order_by("-last_login").values_list("last_login", flat=True).first()
    return {"active_employees": Employee.all_objects.filter(organization=org, status__in=ACTIVE_STATUSES).count(),
            "users": users.filter(is_active=True).count(), "last_login": last,
            "employee_limit": org.plan.max_employees if org.plan_id else None}


# ---------------------------------------------------------------- trials
def expire_trials(today=None):
    """Daily: warn administrators 3 days before a trial ends, suspend trials that have ended."""
    from apps.rbac.services import has_perm

    today = today or dt.date.today()
    suspended = warned = 0
    for org in Organization.objects.filter(status="trial", trial_ends_at__isnull=False):
        admins = [u.email for u in org.users.filter(is_active=True) if u.email and has_perm(u, "admin.settings")]
        if org.trial_ends_at < today:
            set_status(org, "suspended", "Trial ended")
            suspended += 1
            msg = "Your ShineLight HRM trial has ended and access is paused. Contact us to choose a plan."
        elif org.trial_ends_at == today + dt.timedelta(days=3):
            warned += 1
            msg = f"Your ShineLight HRM trial ends on {org.trial_ends_at:%d/%m/%Y}. Contact us to choose a plan."
        else:
            continue
        if admins:
            send_mail("ShineLight HRM trial", msg, settings.DEFAULT_FROM_EMAIL, admins)
    return {"suspended": suspended, "warned": warned, "at": timezone.now()}
