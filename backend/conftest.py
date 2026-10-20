import datetime as dt
from decimal import Decimal

import pytest

from apps.core.context import org_context


@pytest.fixture
def org(db):
    from apps.core.setup import setup_organization

    org, _ = setup_organization("Test Org", "test", features=["payroll", "hospital"], require_mfa=False)
    with org_context(org):
        yield org


@pytest.fixture
def make_user(org):
    from django.contrib.auth import get_user_model

    from apps.rbac.models import Role, RoleAssignment

    def _make(username, roles=("employee",), employee=None):
        user = get_user_model().objects.create_user(username, f"{username}@t.local", "Passw0rd!xyz", organization=org)
        for r in roles:
            RoleAssignment.objects.create(user=user, role=Role.objects.get(code=r))
        if employee is not None:
            employee.user = user
            employee.save(update_fields=["user"])
        return user

    return _make


@pytest.fixture
def structure(org):
    from apps.organization.models import Department, Grade, GradeStep, JobTitle, Position

    dept = Department.objects.create(code="OPS", name="Operations", min_staffing=1)
    other = Department.objects.create(code="FIN", name="Finance")
    grade = Grade.objects.create(code="G3", name="Senior", level=3)
    step = GradeStep.objects.create(grade=grade, step=1, basic_salary=Decimal("5000"))
    title = JobTitle.objects.create(name="Officer")
    pos = Position.objects.create(code="P1", job_title=title, department=dept, grade=grade, headcount=10)
    pos_fin = Position.objects.create(code="P2", job_title=title, department=other, grade=grade, headcount=10)
    return {"dept": dept, "other": other, "grade": grade, "step": step, "title": title, "pos": pos, "pos_fin": pos_fin}


@pytest.fixture
def make_employee(structure):
    from apps.employees.services import hire

    counter = {"n": 0}

    def _make(first="Ama", last=None, supervisor=None, position=None, hire_date=None, **extra):
        counter["n"] += 1
        data = {"first_name": first, "last_name": last or f"Test{counter['n']}", "gender": extra.pop("gender", "female"),
                "hire_date": hire_date or dt.date(2020, 1, 1), "position": position or structure["pos"],
                "grade_step": structure["step"], "supervisor": supervisor}
        data.update(extra)
        return hire(data, allow_duplicate=True)

    return _make
