import datetime as dt
from decimal import Decimal as D

import pytest

from apps.core.exceptions import BusinessRuleError


@pytest.fixture
def setup(org, make_employee, make_user):
    from apps.employees.models import BankAccount
    from apps.payroll.models import EmployeePayProfile, PayGroup
    from apps.payroll.services import create_period

    mgr = make_employee(first="Kofi", gender="male")
    emp = make_employee(first="Ama", supervisor=mgr)
    BankAccount.objects.create(employee=emp, bank_name="GCB", account_number="123456789")
    EmployeePayProfile.objects.create(employee=emp, pay_group=PayGroup.objects.get(code="monthly"))
    create_period(PayGroup.objects.get(code="monthly"), dt.date.today().year, dt.date.today().month)
    return {
        "emp": emp, "user": make_user("ama", ("employee",), employee=emp),
        "mgr_user": make_user("kofi", ("employee", "line_manager"), employee=mgr),
        "finance": make_user("fin", ("finance_officer",)), "payroll": make_user("pay", ("payroll_officer",)),
    }


def approve_all(user, rtype):
    from apps.workflow import engine
    from apps.workflow.models import WorkflowTask

    for t in WorkflowTask.objects.filter(status="pending", assignee=user, instance__request_type=rtype):
        engine.act(t, user, "approve")


def test_travel_per_diem_and_routing(setup):
    from apps.expenses import services
    from apps.expenses.models import TravelRequest

    dep = dt.date.today() + dt.timedelta(days=10)
    tr = TravelRequest.objects.create(employee=setup["emp"], purpose="Training", destination="Kumasi",
                                      destination_class="national", departure_date=dep,
                                      return_date=dep + dt.timedelta(days=2), transport_estimate=D("300"),
                                      accommodation_estimate=D("900"), advance_requested=D("1000"))
    services.submit_travel(tr, setup["user"])
    tr.refresh_from_db()
    assert tr.per_diem_days == 3 and tr.per_diem_rate == D("250.00")  # grade level 3 band
    assert tr.total_estimate == D("1950.00")
    assert tr.reference.startswith("TR-")
    approve_all(setup["mgr_user"], "travel_request")
    tr.refresh_from_db()
    assert tr.status == "approved"  # dept-head step skipped (no head configured)
    with pytest.raises(BusinessRuleError):
        services.pay_advance(tr, setup["payroll"], D("1500"), "CHQ1")
    services.pay_advance(tr, setup["payroll"], D("1000"), "TRF-001")
    tr.refresh_from_db()
    assert tr.advance_paid == D("1000") and tr.retirement_due == tr.return_date + dt.timedelta(days=14)


def test_claim_retires_advance_and_recovers_via_payroll(setup):
    from apps.expenses import services
    from apps.expenses.models import ExpenseClaim, ExpenseItem, TravelRequest
    from apps.payroll.models import PayrollAdjustment

    dep = dt.date.today() - dt.timedelta(days=5)
    tr = TravelRequest.objects.create(employee=setup["emp"], purpose="Audit", destination="Tamale",
                                      destination_class="national", departure_date=dep,
                                      return_date=dep + dt.timedelta(days=1), status="approved",
                                      advance_requested=D("800"), total_estimate=D("800"))
    services.pay_advance(tr, setup["payroll"], D("800"), "TRF-9")
    claim = ExpenseClaim.objects.create(employee=setup["emp"], travel_request=tr, title="Tamale audit")
    ExpenseItem.objects.create(claim=claim, date=dep, category="transport", description="Bus", amount=D("150"),
                               receipt_missing_reason="Ticket lost")
    ExpenseItem.objects.create(claim=claim, date=dep, category="meals", description="Lunch", amount=D("40"))
    services.submit_claim(claim, setup["user"])
    claim.refresh_from_db()
    assert claim.total == D("190.00") and claim.net_payable == D("-610.00")
    assert any("No receipt" in w for w in claim.warnings)
    approve_all(setup["mgr_user"], "expense_claim")
    approve_all(setup["finance"], "expense_claim")
    claim.refresh_from_db()
    assert claim.status == "approved"
    with pytest.raises(BusinessRuleError):
        services.settle_claim(claim, setup["finance"])  # approver cannot pay
    services.settle_claim(claim, setup["payroll"], "payroll")
    claim.refresh_from_db()
    tr.refresh_from_db()
    adj = PayrollAdjustment.objects.get(pk=claim.payroll_adjustment_id)
    assert adj.element.code == "ADVANCE_RECOVERY" and adj.amount == D("610.00")
    assert claim.status == "paid" and tr.status == "retired"


def test_receipt_required(setup):
    from apps.expenses import services
    from apps.expenses.models import ExpenseClaim, ExpenseItem

    claim = ExpenseClaim.objects.create(employee=setup["emp"], title="Fuel")
    ExpenseItem.objects.create(claim=claim, date=dt.date.today(), category="fuel", description="Fuel", amount=D("200"))
    with pytest.raises(BusinessRuleError):
        services.submit_claim(claim, setup["user"])


def test_budget_warning(setup):
    from apps.expenses import services
    from apps.expenses.models import ExpenseBudget, TravelRequest

    ExpenseBudget.objects.create(department=setup["emp"].department, year=dt.date.today().year, category="travel",
                                 amount=D("500"))
    dep = dt.date.today() + dt.timedelta(days=3)
    tr = TravelRequest(employee=setup["emp"], purpose="x", destination="Ho", destination_class="national",
                       departure_date=dep, return_date=dep, transport_estimate=D("400"))
    services.compute_travel(tr)
    assert any("budget" in w for w in tr.warnings)


def test_same_approver_not_asked_twice(setup):
    """Supervisor who is also head of department approves once; the duplicate step is skipped."""
    from apps.expenses import services
    from apps.expenses.models import TravelRequest
    from apps.workflow.models import WorkflowTask

    dept = setup["emp"].department
    dept.head = setup["emp"].supervisor
    dept.save()
    dep = dt.date.today() + dt.timedelta(days=5)
    tr = TravelRequest.objects.create(employee=setup["emp"], purpose="x", destination="Ho", destination_class="national",
                                      departure_date=dep, return_date=dep)
    services.submit_travel(tr, setup["user"])
    approve_all(setup["mgr_user"], "travel_request")
    tr.refresh_from_db()
    assert tr.status == "approved"
    assert not WorkflowTask.objects.filter(status="pending", instance__request_type="travel_request").exists()
