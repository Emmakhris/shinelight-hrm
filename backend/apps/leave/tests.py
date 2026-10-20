import datetime as dt
from decimal import Decimal as D

import pytest

from apps.core.exceptions import BusinessRuleError


@pytest.fixture
def team(org, make_employee, make_user):
    mgr = make_employee(first="Kofi", gender="male")
    staff = make_employee(first="Ama", supervisor=mgr)
    colleague = make_employee(first="Esi", supervisor=mgr)
    mgr_user = make_user("mgr", ("employee", "line_manager"), employee=mgr)
    staff_user = make_user("staff", ("employee",), employee=staff)
    hr_user = make_user("hr", ("hr_officer",))
    return {"mgr": mgr, "staff": staff, "colleague": colleague, "mgr_user": mgr_user, "staff_user": staff_user,
            "hr_user": hr_user}


def _annual():
    from apps.leave.models import LeaveType

    return LeaveType.objects.get(code="annual")


def test_working_days_exclude_weekends_and_holidays(org):
    from apps.core.models import PublicHoliday
    from apps.leave.services import calculate_days

    PublicHoliday.objects.create(name="Test holiday", date=dt.date(2026, 3, 6))
    # Mon 2 Mar - Fri 6 Mar 2026 with holiday on Friday => 4 days
    assert calculate_days(_annual(), dt.date(2026, 3, 2), dt.date(2026, 3, 6)) == D("4")
    assert calculate_days(_annual(), dt.date(2026, 3, 2), dt.date(2026, 3, 3), start_half=True) == D("1.5")


def test_entitlement_and_service_bonus(team):
    from apps.leave.services import balance

    bal = balance(team["staff"], _annual(), 2026)
    # hired 2020 => 6 years service => 15 + 3 bonus days
    assert bal["entitlement"] == D("18.00")


def test_full_leave_approval_flow(team):
    from apps.leave.models import LeaveRequest
    from apps.leave.services import balance, submit
    from apps.workflow import engine
    from apps.workflow.models import WorkflowTask

    req = LeaveRequest.objects.create(employee=team["staff"], leave_type=_annual(), start_date=dt.date(2026, 11, 2),
                                      end_date=dt.date(2026, 11, 6))
    submit(req, team["staff_user"])
    assert req.status == "pending"
    assert balance(team["staff"], _annual(), 2026)["pending"] == D("5")
    t1 = WorkflowTask.objects.get(status="pending")
    assert t1.assignee == team["mgr_user"]
    with pytest.raises(BusinessRuleError):
        engine.act(t1, team["staff_user"], "approve")
    engine.act(t1, team["mgr_user"], "approve")
    t2 = WorkflowTask.objects.get(status="pending")
    assert t2.assignee == team["hr_user"]
    engine.act(t2, team["hr_user"], "approve")
    req.refresh_from_db()
    assert req.status == "approved"
    bal = balance(team["staff"], _annual(), 2026)
    assert bal["taken"] == D("5")
    assert bal["pending"] == D("0")


def test_reject_requires_comment(team):
    from apps.leave.models import LeaveRequest
    from apps.leave.services import submit
    from apps.workflow import engine
    from apps.workflow.models import WorkflowTask

    req = LeaveRequest.objects.create(employee=team["staff"], leave_type=_annual(), start_date=dt.date(2026, 11, 2),
                                      end_date=dt.date(2026, 11, 3))
    submit(req, team["staff_user"])
    task = WorkflowTask.objects.get(status="pending")
    with pytest.raises(BusinessRuleError):
        engine.act(task, team["mgr_user"], "reject", "")
    engine.act(task, team["mgr_user"], "reject", "Busy period")
    req.refresh_from_db()
    assert req.status == "rejected"


def test_insufficient_balance_and_overlap(team):
    from apps.leave.models import LeaveRequest
    from apps.leave.services import submit

    big = LeaveRequest.objects.create(employee=team["staff"], leave_type=_annual(), start_date=dt.date(2026, 11, 2),
                                      end_date=dt.date(2026, 12, 18))
    with pytest.raises(BusinessRuleError) as exc:
        submit(big, team["staff_user"])
    assert exc.value.code == "insufficient_balance"
    ok = LeaveRequest.objects.create(employee=team["staff"], leave_type=_annual(), start_date=dt.date(2026, 11, 2),
                                     end_date=dt.date(2026, 11, 3))
    submit(ok, team["staff_user"])
    dup = LeaveRequest.objects.create(employee=team["staff"], leave_type=_annual(), start_date=dt.date(2026, 11, 3),
                                      end_date=dt.date(2026, 11, 4))
    with pytest.raises(BusinessRuleError):
        submit(dup, team["staff_user"])


def test_delegation_routes_to_delegate(team, make_user):
    from apps.leave.models import LeaveRequest
    from apps.leave.services import submit
    from apps.workflow.models import Delegation, WorkflowTask

    deputy = make_user("deputy", ("employee",))
    Delegation.objects.create(delegator=team["mgr_user"], delegate=deputy, start_date=dt.date(2020, 1, 1),
                              end_date=dt.date(2030, 1, 1))
    req = LeaveRequest.objects.create(employee=team["staff"], leave_type=_annual(), start_date=dt.date(2026, 11, 2),
                                      end_date=dt.date(2026, 11, 3))
    submit(req, team["staff_user"])
    task = WorkflowTask.objects.get(status="pending")
    assert task.assignee == deputy
    assert task.delegated_from == team["mgr_user"]


def test_recall_credits_unused_days(team):
    from apps.leave.models import LeaveRequest
    from apps.leave.services import balance, on_approved, recall

    req = LeaveRequest.objects.create(employee=team["staff"], leave_type=_annual(), start_date=dt.date(2026, 11, 2),
                                      end_date=dt.date(2026, 11, 6), days=D("5"), status="pending")
    on_approved(req)
    unused = recall(req, dt.date(2026, 11, 5), "Emergency", team["mgr_user"])
    assert unused == D("2")
    assert balance(team["staff"], _annual(), 2026)["taken"] == D("3")


def test_sla_escalation(team):
    from datetime import timedelta

    from django.utils import timezone

    from apps.leave.models import LeaveRequest
    from apps.leave.services import submit
    from apps.workflow import engine
    from apps.workflow.models import WorkflowTask

    boss = team["mgr"]
    from apps.employees.services import hire

    top = hire({"first_name": "Top", "last_name": "Boss", "hire_date": dt.date(2019, 1, 1),
                "position": boss.position}, allow_duplicate=True)
    boss.supervisor = top
    boss.save()
    from django.contrib.auth import get_user_model

    top_user = get_user_model().objects.create_user("top", "", "x" * 12, organization=boss.organization)
    top.user = top_user
    top.save()
    req = LeaveRequest.objects.create(employee=team["staff"], leave_type=_annual(), start_date=dt.date(2026, 11, 2),
                                      end_date=dt.date(2026, 11, 3))
    submit(req, team["staff_user"])
    reminded, escalated = engine.process_sla(now=timezone.now() + timedelta(hours=49))
    assert escalated == 1
    assert WorkflowTask.objects.filter(assignee=top_user, is_escalation=True, status="pending").exists()
