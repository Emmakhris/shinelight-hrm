import datetime as dt
from decimal import Decimal as D

import pytest

from apps.payroll import engine

BANDS_2024 = [(D("490"), D("0")), (D("110"), D("5")), (D("130"), D("10")), (D("3166.67"), D("17.5")),
              (D("16000"), D("25")), (D("30520"), D("30")), (None, D("35"))]


def rules(**kw):
    return engine.Rules(bands=BANDS_2024, ssnit_cap=D("61000"), ot_qualifying_income=D("18000"), **kw)


def inputs(basic="5000", **kw):
    base = dict(monthly_basic=D(basic), days_in_period=D("22"), days_payable=D("22"))
    base.update(kw)
    return engine.PayInputs(**base)


# ------------------------------------------------------------------ pure engine golden tests
def test_graduated_tax_bands():
    assert engine.graduated_tax(D("490"), BANDS_2024) == D("0.00")
    assert engine.graduated_tax(D("600"), BANDS_2024) == D("5.50")
    assert engine.graduated_tax(D("730"), BANDS_2024) == D("18.50")
    assert engine.graduated_tax(D("4725"), BANDS_2024) == D("779.75")


def test_basic_gross_to_net():
    r = engine.calculate(inputs("5000"), rules())
    assert r.gross == D("5000.00")
    assert r.ssnit_employee == D("275.00")
    assert r.ssnit_employer == D("650.00")
    assert r.tier1 == D("675.00")
    assert r.tier2 == D("250.00")
    assert r.taxable_income == D("4725.00")
    assert r.paye == D("779.75")
    assert r.net == D("3945.25")
    assert r.employer_cost == D("5650.00")
    assert r.status == "ok"


def test_allowances_and_deductions():
    els = [engine.ElementInput("TRANSPORT", "Transport", "earning", amount=D("500")),
           engine.ElementInput("HOUSING", "Housing", "earning", calculation="percent_basic", percent=D("10")),
           engine.ElementInput("UNION", "Union", "deduction", calculation="percent_basic", percent=D("2"))]
    r = engine.calculate(inputs("5000", elements=els), rules())
    assert r.gross == D("6000.00")
    # SSNIT on basic only
    assert r.ssnit_employee == D("275.00")
    assert r.taxable_income == D("5725.00")
    assert r.paye == engine.graduated_tax(D("5725"), BANDS_2024)
    union = next(ln for ln in r.lines if ln.code == "UNION")
    assert union.amount == D("100.00")
    assert r.net == r.gross - r.total_deductions


def test_proration_for_partial_month():
    r = engine.calculate(inputs("3000", days_payable=D("11")), rules())
    assert r.basic_pay == D("1500.00")
    assert r.ssnit_employee == D("82.50")


def test_bonus_within_and_above_15_percent():
    bonus = [engine.ElementInput("BONUS", "Bonus", "earning", amount=D("10000"), tax_treatment="bonus", prorate=False)]
    r = engine.calculate(inputs("5000", elements=bonus), rules())
    # 15% of annual basic (60,000) = 9,000 at 5%; 1,000 excess taxed with income
    assert r.bonus_tax == D("450.00")
    assert r.taxable_income == D("5725.00")
    assert r.paye == engine.graduated_tax(D("5725"), BANDS_2024)


def test_bonus_allowance_reduced_by_ytd():
    bonus = [engine.ElementInput("BONUS", "Bonus", "earning", amount=D("2000"), tax_treatment="bonus", prorate=False)]
    r = engine.calculate(inputs("5000", elements=bonus, ytd_bonus=D("8000")), rules())
    assert r.bonus_tax == D("50.00")  # only 1,000 left at 5%
    assert r.taxable_income == D("5725.00")


def test_overtime_for_qualifying_junior_staff():
    r = engine.calculate(inputs("1000", ot_hours_normal=D("10"), hours_per_month=D("100"),
                                ot_weekday_multiplier=D("6")), rules())
    # hourly 10 x 6 = 60 x 10h = 600 overtime; threshold 50% of basic = 500 @5% + 100 @10%
    assert r.overtime_tax == D("35.00")
    assert r.taxable_income == D("945.00")  # OT excluded from PAYE base


def test_overtime_for_non_qualifying_staff_is_taxed_as_income():
    r = engine.calculate(inputs("5000", ot_hours_normal=D("10"), hours_per_month=D("100")), rules())
    ot = D("10") * D("75.00")
    assert r.overtime_tax == D("0")
    assert r.taxable_income == D("4725") + ot


def test_tier3_exemption_and_reliefs():
    r = engine.calculate(inputs("5000", tier3_employee_percent=D("5"), annual_reliefs=D("1200")), rules())
    assert r.tier3_employee == D("250.00")
    assert r.reliefs == D("100.00")
    assert r.taxable_income == D("5000") - D("275") - D("250") - D("100")


def test_non_resident_flat_rate():
    r = engine.calculate(inputs("5000", is_resident=False), rules())
    assert r.paye == D("1181.25")  # 25% of 4725


def test_loan_deduction_capped_and_full_recovery():
    loans = [engine.LoanInput(1, "Staff loan", D("1000"), D("400"))]
    r = engine.calculate(inputs("5000", loans=loans), rules())
    assert r.loan_deductions == {1: D("400.00")}
    r2 = engine.calculate(inputs("5000", loans=[engine.LoanInput(1, "Loan", D("100"), D("2000"))],
                                 recover_full_loans=True), rules())
    assert r2.loan_deductions == {1: D("2000.00")}


def test_negative_net_is_error():
    els = [engine.ElementInput("X", "Big deduction", "deduction", amount=D("10000"))]
    r = engine.calculate(inputs("5000", elements=els), rules())
    assert r.status == "error"


def test_formula_element():
    els = [engine.ElementInput("RISK", "Risk allowance", "earning", calculation="formula",
                               formula="min(basic * 0.1, 300)")]
    r = engine.calculate(inputs("5000", elements=els), rules())
    assert next(ln for ln in r.lines if ln.code == "RISK").amount == D("300.00")


def test_ssnit_cap():
    r = engine.calculate(inputs("80000"), rules())
    assert r.ssnit_employee == D("3355.00")  # 5.5% of 61,000


# ------------------------------------------------------------------ end-to-end run with maker-checker
@pytest.fixture
def payroll_setup(org, make_employee, make_user):
    from apps.employees.models import BankAccount
    from apps.payroll.models import EmployeePayProfile, PayGroup
    from apps.payroll.services import create_period

    group = PayGroup.objects.get(code="monthly")
    emps = []
    for i in range(3):
        e = make_employee(first=f"E{i}")
        EmployeePayProfile.objects.create(employee=e, pay_group=group)
        BankAccount.objects.create(employee=e, bank_name="GCB", account_number=f"12345678{i}", account_name="x")
        emps.append(e)
    period = create_period(group, 2026, 9)
    preparer = make_user("prep", ("payroll_officer",))
    approver = make_user("appr", ("payroll_approver",))
    return {"emps": emps, "period": period, "preparer": preparer, "approver": approver}


def test_payroll_run_pipeline(payroll_setup):
    from apps.core.exceptions import BusinessRuleError
    from apps.payroll.models import PayrollRun
    from apps.payroll.services import calculate_run, release_run, submit_run
    from apps.workflow import engine as wf
    from apps.workflow.models import WorkflowTask

    s = payroll_setup
    run = PayrollRun.objects.create(period=s["period"])
    run = calculate_run(run, s["preparer"])
    assert run.status == "calculated"
    assert run.payslips.count() == 3
    slip = run.payslips.first()
    assert slip.net_pay == D("3945.25")
    assert run.totals["employees"] == 3

    submit_run(run, s["preparer"])
    run.refresh_from_db()
    assert run.status == "submitted"
    task = WorkflowTask.objects.get(instance__request_type="payroll_run", status="pending")
    assert task.assignee == s["approver"]
    with pytest.raises(BusinessRuleError):
        wf.act(task, s["preparer"], "approve")  # preparer cannot approve
    wf.act(task, s["approver"], "approve")
    run.refresh_from_db()
    assert run.status == "approved"
    with pytest.raises(BusinessRuleError):
        release_run(run, s["preparer"])  # preparer cannot release
    release_run(run, s["approver"])
    run.refresh_from_db()
    assert run.status == "paid"
    assert run.payslips.filter(published_at__isnull=False).count() == 3


def test_unpaid_leave_reduces_pay(payroll_setup):
    from apps.leave.models import LeaveRequest, LeaveType
    from apps.payroll.models import PayrollRun
    from apps.payroll.services import calculate_run

    s = payroll_setup
    emp = s["emps"][0]
    unpaid = LeaveType.objects.get(code="unpaid")
    LeaveRequest.objects.create(employee=emp, leave_type=unpaid, start_date=dt.date(2026, 9, 7),
                                end_date=dt.date(2026, 9, 11), days=D("5"), status="approved")
    LeaveRequest.objects.create(employee=s["emps"][1], leave_type=unpaid, start_date=dt.date(2026, 9, 7),
                                end_date=dt.date(2026, 9, 11), days=D("5"), status="pending")
    run = calculate_run(PayrollRun.objects.create(period=s["period"]), s["preparer"])
    slip = run.payslips.get(employee=emp)
    assert slip.days_payable == slip.days_in_period - 5
    assert slip.basic_pay < D("5000")
    # pending (unapproved) leave must not affect payroll
    assert run.payslips.get(employee=s["emps"][1]).basic_pay == D("5000.00")


def test_reversal_restores_loans(payroll_setup):
    from apps.payroll.models import Loan, PayrollRun
    from apps.payroll.services import calculate_run, release_run, reverse_run, submit_run
    from apps.workflow import engine as wf
    from apps.workflow.models import WorkflowTask

    s = payroll_setup
    loan = Loan.objects.create(employee=s["emps"][0], loan_type="staff_loan", principal=D("1000"), installments=2,
                               installment_amount=D("500"), total_repayable=D("1000"), balance=D("1000"),
                               start_date=dt.date(2026, 9, 1), status="active")
    run = calculate_run(PayrollRun.objects.create(period=s["period"]), s["preparer"])
    submit_run(run, s["preparer"])
    wf.act(WorkflowTask.objects.get(status="pending"), s["approver"], "approve")
    run.refresh_from_db()
    run = release_run(run, s["approver"])
    loan.refresh_from_db()
    assert loan.balance == D("500.00")
    rev = reverse_run(run, s["approver"], "Bank file error")
    loan.refresh_from_db()
    assert loan.balance == D("1000.00")
    assert rev.payslips.first().net_pay < 0
