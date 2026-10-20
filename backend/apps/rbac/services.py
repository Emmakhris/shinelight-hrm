"""Authorization services: permission checks, data scoping and field masking.

A user's effective access = union of their active RoleAssignments. Each grant carries a
scope (own/team/department/branch/organization) which determines *which employees'*
records the permission applies to.
"""

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass

from django.db.models import Q

from .models import SCOPE_RANK, RoleAssignment


@dataclass(frozen=True)
class Grant:
    scope: str
    department_id: int | None = None
    branch_id: int | None = None


def get_grants(user) -> dict[str, list[Grant]]:
    if not user or not user.is_authenticated:
        return {}
    cached = getattr(user, "_rbac_grants", None)
    if cached is not None:
        return cached
    today = dt.date.today()
    grants: dict[str, list[Grant]] = defaultdict(list)
    qs = (
        RoleAssignment.all_objects.filter(user=user, organization_id=user.organization_id)
        .filter(Q(valid_from__isnull=True) | Q(valid_from__lte=today))
        .filter(Q(valid_to__isnull=True) | Q(valid_to__gte=today))
        .select_related("role")
        .prefetch_related("role__permissions")
    )
    for ra in qs:
        g = Grant(ra.effective_scope, ra.department_id, ra.branch_id)
        for perm in ra.role.permissions.all():
            grants[perm.code].append(g)
    user._rbac_grants = dict(grants)
    return user._rbac_grants


def clear_cache(user):
    if hasattr(user, "_rbac_grants"):
        del user._rbac_grants


def has_perm(user, code: str, min_scope: str | None = None) -> bool:
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    grants = get_grants(user).get(code)
    if not grants:
        return False
    if min_scope is None:
        return True
    return any(SCOPE_RANK[g.scope] >= SCOPE_RANK[min_scope] for g in grants)


def all_permission_codes(user) -> list[str]:
    if user.is_superuser:
        from .models import Permission

        return list(Permission.objects.values_list("code", flat=True))
    return sorted(get_grants(user).keys())


def best_scope(user, code: str) -> str | None:
    if user.is_superuser:
        return "organization"
    grants = get_grants(user).get(code) or []
    if not grants:
        return None
    return max((g.scope for g in grants), key=lambda s: SCOPE_RANK[s])


def department_descendants(dept_id: int) -> list[int]:
    from apps.organization.models import Department

    ids = [dept_id]
    frontier = [dept_id]
    while frontier:
        children = list(Department.all_objects.filter(parent_id__in=frontier).values_list("id", flat=True))
        children = [c for c in children if c not in ids]
        ids.extend(children)
        frontier = children
    return ids


def team_member_ids(employee) -> list[int]:
    """All direct and indirect reports of an employee."""
    from apps.employees.models import Employee

    ids: list[int] = []
    frontier = [employee.id]
    while frontier:
        reports = list(Employee.all_objects.filter(supervisor_id__in=frontier).values_list("id", flat=True))
        reports = [r for r in reports if r not in ids and r != employee.id]
        ids.extend(reports)
        frontier = reports
    return ids


def employee_scope_q(user, code: str, prefix: str = "") -> Q | None:
    """Q filter restricting an Employee-related queryset to what `user` may access under `code`.

    prefix: lookup path from the model to Employee, e.g. "" for Employee, "employee__" for LeaveRequest.
    Returns None if the user has no access at all.
    """
    if user.is_superuser:
        return Q()
    grants = get_grants(user).get(code)
    if not grants:
        return None
    employee = getattr(user, "employee", None)
    pk_field = f"{prefix}id" if prefix else "id"
    q = Q(pk__in=[]) if not prefix else Q(**{f"{prefix}id__in": []})
    if employee is not None:
        q = Q(**{pk_field: employee.id})
    for g in grants:
        if g.scope == "organization":
            return Q()
        if g.scope == "branch":
            branch_id = g.branch_id or (employee.branch_id if employee else None)
            if branch_id:
                q |= Q(**{f"{prefix}branch_id": branch_id})
        elif g.scope == "department":
            dept_id = g.department_id or (employee.department_id if employee else None)
            if dept_id:
                q |= Q(**{f"{prefix}department_id__in": department_descendants(dept_id)})
        elif g.scope == "team" and employee is not None:
            q |= Q(**{f"{pk_field}__in": team_member_ids(employee)})
    return q


def scope_queryset(user, qs, code: str, prefix: str = ""):
    q = employee_scope_q(user, code, prefix)
    if q is None:
        return qs.none()
    return qs.filter(q)


def can_access_employee(user, code: str, employee) -> bool:
    from apps.employees.models import Employee

    if employee is None:
        return has_perm(user, code)
    q = employee_scope_q(user, code)
    if q is None:
        return False
    return Employee.all_objects.filter(q, pk=employee.pk).exists()
