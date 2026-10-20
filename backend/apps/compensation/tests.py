import datetime as dt
from decimal import Decimal as D

import pytest

from apps.core.exceptions import BusinessRuleError


@pytest.fixture
def people(org, make_employee, make_user):
    a = make_employee(first="Ama")
    b = make_employee(first="Esi")
    return {"a": a, "b": b, "hrd": make_user("hrd", ("hr_director",)), "hro": make_user("hro", ("hr_officer",)),
            "comp": make_user("comp", ("hr_officer",)), "user_a": make_user("ama", ("employee",), employee=a)}


def test_salary_review_guidelines_approval_and_apply(people):
    from apps.compensation import services
    from apps.compensation.models import SalaryReviewCycle
    from apps.employees.services import as_of
    from apps.workflow import engine
    from apps.workflow.models import WorkflowTask

    eff = dt.date.today().replace(day=1)
    cycle = SalaryReviewCycle.objects.create(name="2026 review", effective_date=eff, budget_percent=D("8"),
                                             default_increase_percent=D("5"),
                                             guidelines=[{"min_level": 1, "max_level": 9, "min": 3, "max": 10}])
    assert services.populate_cycle(cycle) == 2
    la = cycle.lines.get(employee=people["a"])
    assert la.proposed_basic == D("5250.00")
    services.recalc_line(la, increase_percent=15)
    assert la.outside_guideline
    with pytest.raises(BusinessRuleError):
        services.submit_cycle(cycle, people["comp"])  # justification missing
    la.justification = "Scarce skill retention"
    la.save()
    s = services.cycle_summary(cycle)
    # 15% on 5,000 + 5% on 5,000 = 1,000/month against an 8% budget of 800/month
    assert s["monthly_increase"] == D("1000.00") and s["within_budget"] is False
    services.submit_cycle(cycle, people["comp"])
    task = WorkflowTask.objects.get(status="pending", instance__request_type="salary_review")
    engine.act(task, task.assignee, "approve")
    cycle.refresh_from_db()
    assert cycle.status == "approved"
    services.apply_cycle(cycle, people["hro"])
    people["a"].refresh_from_db()
    assert people["a"].basic_salary == D("5750.00")
    assert as_of(people["a"], eff - dt.timedelta(days=1)).basic_salary == D("5000.00")


def test_bonus_scheme_posts_payroll_adjustments(people):
    from apps.compensation import services
    from apps.compensation.models import BonusAward, BonusScheme
    from apps.payroll.models import PayGroup, PayrollAdjustment
    from apps.payroll.services import create_period
    from apps.workflow import engine
    from apps.workflow.models import WorkflowTask

    period = create_period(PayGroup.objects.get(code="monthly"), 2026, 12)
    scheme = BonusScheme.objects.create(name="13th month", basis="months_basic", default_value=D("1"), pay_period=period)
    for e in (people["a"], people["b"]):
        BonusAward.objects.create(scheme=scheme, employee=e, amount=services.bonus_amount(scheme, e))
    services.submit_bonus(scheme, people["comp"])
    task = WorkflowTask.objects.get(status="pending", instance__request_type="bonus_scheme")
    engine.act(task, task.assignee, "approve")
    adj = PayrollAdjustment.objects.filter(period=period, element__code="BONUS")
    assert adj.count() == 2 and adj.first().amount == D("5000.00")


def test_benefit_eligibility_enrollment_and_payroll_deduction(people):
    from apps.compensation import services
    from apps.compensation.models import BenefitPlan
    from apps.payroll.models import EmployeePayElement
    from apps.workflow import engine
    from apps.workflow.models import WorkflowTask

    plan = BenefitPlan.objects.get(code="medical")
    plan.min_service_months = 600
    plan.save()
    assert services.eligibility(plan, people["a"])
    plan.min_service_months = 0
    plan.save()
    with pytest.raises(BusinessRuleError):
        services.enroll(plan, people["a"], people["user_a"], dt.date.today(), dependants=[{}] * 5)
    e = services.enroll(plan, people["a"], people["user_a"], dt.date.today(),
                        dependants=[{"name": "Kwesi", "relationship": "child"}])
    task = WorkflowTask.objects.filter(status="pending", instance__request_type="benefit_enrollment").first()
    engine.act(task, task.assignee, "approve")  # any one HR officer may approve
    e.refresh_from_db()
    assert e.status == "active" and e.employee_cost == D("90.00")
    pe = EmployeePayElement.objects.get(pk=e.pay_element_id)
    assert pe.amount == D("90.00") and pe.element.code == "INSURANCE_EE"
    cost = {r["plan"]: r for r in services.benefits_cost()}
    assert cost["Staff medical insurance"]["members"] == 1


def test_auto_enroll_and_total_rewards(people):
    from apps.compensation import services
    from apps.compensation.models import BenefitPlan

    plan = BenefitPlan.objects.get(code="group_life")
    assert services.auto_enroll(plan) == 2
    tr = services.total_rewards(people["a"])
    assert tr["benefits"] and tr["benefits"][0]["plan"] == "Group life assurance"


def test_esignature_flow(people, make_user):
    from django.core.files.base import ContentFile

    from apps.core.pdf import html_to_pdf
    from apps.documents import esign, services as doc_services
    from apps.documents.models import Document, DocumentCategory

    user_a = people["user_a"]
    user_a.first_name, user_a.last_name = "Ama", "Test"
    user_a.save()
    doc = Document.objects.create(employee=people["a"], category=DocumentCategory.objects.get(code="contract"),
                                  title="Employment contract")
    f = ContentFile(html_to_pdf("<p>Contract</p>"), name="contract.pdf")
    doc_services.add_version(doc, f)
    req = esign.request_signatures(doc, [{"user": user_a, "role_label": "Employee"},
                                         {"user": people["hrd"], "role_label": "For the employer"}])
    s1, s2 = list(req.signers.order_by("order"))
    assert s1.status == "pending" and s2.status == "waiting"
    with pytest.raises(BusinessRuleError):
        esign.sign(s1, user_a, "Wrong Name", True)
    with pytest.raises(BusinessRuleError):
        esign.sign(s1, user_a, "Ama Test", False)
    esign.sign(s1, user_a, "ama test", True, "10.0.0.1")
    s2.refresh_from_db()
    assert s2.status == "pending"
    hrd = people["hrd"]
    esign.sign(s2, hrd, hrd.get_full_name() or hrd.username, True)
    req.refresh_from_db()
    doc.refresh_from_db()
    assert req.status == "completed" and req.signed_version == 2 and doc.current_version == 2
    signed = doc.versions.get(version=2)
    assert signed.file.open("rb").read()[:4] == b"%PDF"
