import datetime as dt
from decimal import Decimal as D

import pytest
from rest_framework.test import APIClient

from apps.core.exceptions import BusinessRuleError


def test_effective_dated_promotion_keeps_history(make_employee, structure):
    from apps.employees.services import apply_change, as_of
    from apps.organization.models import Grade, GradeStep

    emp = make_employee()
    g4 = Grade.objects.create(code="G4", name="Senior II", level=4)
    s4 = GradeStep.objects.create(grade=g4, step=1, basic_salary=D("7000"))
    apply_change(emp, "promotion", dt.date(2024, 1, 1), {"grade": g4, "grade_step": s4}, reason="Promoted")
    emp.refresh_from_db()
    assert emp.grade == g4
    assert emp.basic_salary == D("7000")
    assert emp.employment_records.count() == 2
    old = as_of(emp, dt.date(2023, 6, 1))
    assert old.grade == structure["grade"] and old.basic_salary == D("5000")
    assert old.effective_to == dt.date(2023, 12, 31)


def test_future_dated_change_applied_when_due(make_employee, structure):
    from apps.employees.services import apply_change, apply_due_records

    emp = make_employee()
    future = dt.date.today() + dt.timedelta(days=10)
    apply_change(emp, "transfer", future, {"department": structure["other"]})
    emp.refresh_from_db()
    assert emp.department == structure["dept"]
    apply_due_records(today=future)
    emp.refresh_from_db()
    assert emp.department == structure["other"]


def test_duplicate_detection_and_rehire(make_employee):
    from apps.employees.services import hire, rehire, separate

    emp = make_employee(first="Kojo", last="Ansah", ghana_card_no="GHA-123456789-0", date_of_birth=dt.date(1990, 1, 1))
    with pytest.raises(BusinessRuleError) as exc:
        hire({"first_name": "Kojo", "last_name": "Ansah", "ghana_card_no": "GHA-123456789-0",
              "hire_date": dt.date(2025, 1, 1)})
    assert exc.value.code == "duplicate"
    separate(emp, dt.date(2025, 1, 31), "resignation")
    emp.refresh_from_db()
    assert emp.status == "exited"
    with pytest.raises(BusinessRuleError) as exc:
        hire({"first_name": "Kojo", "last_name": "Ansah", "ghana_card_no": "GHA-123456789-0",
              "hire_date": dt.date(2026, 1, 1)})
    assert exc.value.code == "rehire_required"
    new = rehire(emp, dt.date(2026, 1, 1), {"position": emp.position})
    assert new.previous_record == emp
    assert new.original_hire_date == emp.hire_date


def test_vacancy_control(make_employee, structure):
    pos = structure["pos"]
    pos.headcount = 1
    pos.save()
    make_employee()
    with pytest.raises(BusinessRuleError) as exc:
        make_employee()
    assert exc.value.code == "no_vacancy"


def test_rbac_scoping_and_masking(org, make_employee, make_user, structure):
    mgr = make_employee(first="Boss")
    report = make_employee(first="Report", supervisor=mgr, ghana_card_no="GHA-111111111-1")
    outsider = make_employee(first="Outsider", position=structure["pos_fin"])
    mgr_user = make_user("boss", ("employee", "line_manager"), employee=mgr)
    client = APIClient()
    client.force_authenticate(mgr_user)
    ids = {e["id"] for e in client.get("/api/employees/?page_size=100").json()["results"]}
    assert report.id in ids and mgr.id in ids and outsider.id not in ids
    # line manager has no view_personal for the report: national ID masked/hidden
    data = client.get(f"/api/employees/{report.id}/").json()
    assert data["ghana_card_no"] != "GHA-111111111-1"
    assert data["basic_salary"] is None
    # own record: employee role can see own salary
    own = client.get(f"/api/employees/{mgr.id}/").json()
    assert own["basic_salary"] is not None
    assert client.get(f"/api/employees/{outsider.id}/").status_code == 404


def test_change_request_flow(org, make_employee, make_user):
    from apps.workflow.models import WorkflowTask

    emp = make_employee(first="Abena")
    user = make_user("abena", ("employee",), employee=emp)
    hr = make_user("hro", ("hr_officer",))
    c = APIClient()
    c.force_authenticate(user)
    r = c.post("/api/me/change-requests/", {"changes": {"phone": "0241234567"}, "reason": "New number"},
               format="json")
    assert r.status_code == 201, r.content
    task = WorkflowTask.objects.get(status="pending")
    assert task.assignee == hr
    c.force_authenticate(hr)
    r = c.post(f"/api/workflow/inbox/{task.id}/act/", {"action": "approve"}, format="json")
    assert r.status_code == 200, r.content
    emp.refresh_from_db()
    assert emp.phone == "0241234567"
    # disallowed field via self-service
    c.force_authenticate(user)
    r = c.post("/api/me/change-requests/", {"changes": {"basic_salary": "99999"}}, format="json")
    assert r.status_code == 400


def test_audit_chain_detects_tampering(org, make_employee):
    from apps.audit.models import AuditLog
    from apps.audit.services import verify_chain

    make_employee()
    assert verify_chain(org.id) == (True, None)
    entry = AuditLog.objects.filter(organization=org).order_by("id").first()
    with pytest.raises(PermissionError):
        entry.save()
    with pytest.raises(PermissionError):
        AuditLog.objects.filter(pk=entry.pk).update(message="x")
    # simulate DB-level tampering bypassing the ORM guard
    from django.db import connection

    with connection.cursor() as cur:
        cur.execute(f"UPDATE {AuditLog._meta.db_table} SET message = 'tampered' WHERE id = %s", [entry.pk])
    ok, bad = verify_chain(org.id)
    assert not ok and bad == entry.pk


def test_login_lockout_and_me(org, make_user):
    user = make_user("lock")
    c = APIClient()
    for _ in range(5):
        c.post("/api/auth/login/", {"username": "lock", "password": "wrong"}, format="json")
    r = c.post("/api/auth/login/", {"username": "lock", "password": "Passw0rd!xyz"}, format="json")
    assert r.status_code == 423
    user.refresh_from_db()
    user.locked_until = None
    user.save()
    r = c.post("/api/auth/login/", {"username": "lock", "password": "Passw0rd!xyz"}, format="json")
    assert r.status_code == 200
    assert "employees.view" in r.json()["permissions"]
    assert c.get("/api/auth/me/").status_code == 200


def test_mfa_required_for_sensitive_roles(org, make_user):
    from apps.rbac.models import Role

    Role.objects.filter(code="payroll_officer").update(requires_mfa=True)
    make_user("payuser", ("payroll_officer",))
    r = APIClient().post("/api/auth/login/", {"username": "payuser", "password": "Passw0rd!xyz"}, format="json")
    assert r.status_code == 200
    assert r.json()["mfa_required"] is True
    assert "sl_access" not in r.cookies
