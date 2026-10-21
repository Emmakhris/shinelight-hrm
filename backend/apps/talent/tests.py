import datetime as dt
from decimal import Decimal as D

import pytest
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APIClient

from apps.core.exceptions import BusinessRuleError


@pytest.fixture
def team(org, make_employee, make_user, structure):
    boss = make_employee(first="Kojo")
    a = make_employee(first="Ama", supervisor=boss)
    b = make_employee(first="Esi", supervisor=boss)
    return {"boss": boss, "a": a, "b": b, "u_boss": make_user("boss", ("line_manager",), employee=boss),
            "u_a": make_user("ama", ("employee",), employee=a), "u_b": make_user("esi", ("employee",), employee=b),
            "hrd": make_user("hrd", ("hr_director",)), **structure}


CRITERIA3 = {"learning_agility": {"met": True, "evidence": "Mastered the new LIS in 2 weeks"},
             "leadership": {"met": True, "evidence": "Led the night team during the outage"},
             "aspiration": {"met": True, "evidence": "Asked for supervisory training"}}


def test_transparent_nine_box(team):
    from apps.talent import services
    from apps.talent.models import TalentAssessment

    with pytest.raises(PermissionDenied):
        services.assess(team["u_a"], team["a"], "2026", 3, 3, CRITERIA3, "self")
    with pytest.raises(PermissionDenied):
        services.assess(team["u_b"], team["a"], "2026", 3, 3, CRITERIA3, "peer")
    with pytest.raises(BusinessRuleError):  # high potential needs 3 evidenced criteria
        services.assess(team["u_boss"], team["a"], "2026", 3, 3, {"leadership": CRITERIA3["leadership"]}, "x")
    with pytest.raises(BusinessRuleError):  # evidence is mandatory
        services.assess(team["u_boss"], team["a"], "2026", 3, 2, {"leadership": {"met": True}}, "x")
    with pytest.raises(BusinessRuleError):
        services.assess(team["u_boss"], team["a"], "2026", 3, 3, CRITERIA3, "")  # rationale required
    a = services.assess(team["u_boss"], team["a"], "2026", 3, 3, CRITERIA3, "Consistently strong; ready to grow")
    assert a.box == 9
    services.assess(team["u_boss"], team["b"], "2026", 2, 1, {}, "Solid in role")
    grid = {b["box"]: b["count"] for b in services.nine_box("2026", TalentAssessment.objects.all())}
    assert grid[9] == 1 and grid[4] == 1
    c = APIClient()
    c.force_authenticate(team["u_b"])  # a peer sees nothing
    assert c.get("/api/talent/assessments/").json()["count"] == 0
    c.force_authenticate(team["u_boss"])
    assert c.get("/api/talent/assessments/").json()["count"] == 2


def test_succession_risk_flags_and_bench_strength(team, make_employee):
    from apps.talent import services
    from apps.talent.models import SuccessionPlan

    from apps.organization.models import JobTitle, Position

    pos = Position.objects.create(code="CRIT1", job_title=JobTitle.objects.create(name="Lab Manager"),
                                  department=team["dept"], grade=team["grade"], headcount=1, is_critical=True)
    head = make_employee(first="Grace", position=pos, retirement_date=dt.date.today() + dt.timedelta(days=300))
    r = services.succession_risk()["positions"][0]
    assert "No successor identified" in r["flags"] and "Single-person dependency" in r["flags"]
    assert any(f.startswith("Incumbent retires") for f in r["flags"]) and r["risk"] == "high"
    plan = SuccessionPlan.objects.create(position=pos)
    with pytest.raises(BusinessRuleError):
        services.add_successor(team["hrd"], plan, head, "ready_now")  # incumbent
    with pytest.raises(PermissionDenied):
        services.add_successor(team["u_boss"], plan, team["a"], "ready_now")
    services.add_successor(team["hrd"], plan, team["b"], "1_2_years")
    assert "No ready-now successor" in services.succession_risk()["positions"][0]["flags"]
    services.add_successor(team["hrd"], plan, team["a"], "ready_now")
    risk = services.succession_risk()
    assert risk["bench_strength_percent"] == 100 and risk["single_person_dependencies"] == 0


def test_promotion_eligibility(team):
    from apps.learning.models import Course, Enrollment
    from apps.learning.services import complete
    from apps.organization.models import JobTitle
    from apps.performance.models import Appraisal, ReviewCycle
    from apps.talent import services
    from apps.talent.models import CareerPath

    senior = JobTitle.objects.create(name="Senior Officer")
    path = CareerPath.objects.create(from_title=team["title"], to_title=senior, min_years_in_role=D("2"), min_rating=3,
                                     required_qualification="Professional certificate")
    course = Course.objects.get(code="LD-401")
    path.required_courses.add(course)
    res = services.promotion_eligibility(team["a"])[0]
    assert not res["eligible"] and any("rating" in g for g in res["gaps"]) and any("Course" in g for g in res["gaps"])
    assert res["years_in_role"] > 6  # hired 2020
    y = dt.date.today().year - 1
    cycle = ReviewCycle.objects.create(name="Y", period_start=dt.date(y, 1, 1), period_end=dt.date(y, 12, 31))
    from apps.performance.models import AppraisalTemplate

    Appraisal.objects.create(cycle=cycle, employee=team["a"], template=AppraisalTemplate.objects.first(),
                             final_rating=4, status="completed")
    complete(Enrollment.objects.create(employee=team["a"], course=course, status="enrolled"))
    res = services.promotion_eligibility(team["a"])[0]
    assert res["eligible"] and res["qualification_to_verify"] == "Professional certificate"


def test_projection_arithmetic():
    from apps.talent.services import project

    lines = [{"key": 1, "department_id": 7, "label": "Ward", "current": 10, "planned": 12, "avg_monthly": D("1000"),
              "retirements": {1: 1}}]
    r = project(lines, 2, D("0.10"), D("0"), D("0"), D("0.13"))
    y1 = r["lines"][0]
    # start 10 - 1 retirement - 0.9 attrition = 8.1 supply; target 12 -> hire 3.9; cost 12 x 1000 x 12 x 1.13
    assert (y1["retirements"], y1["attrition"], y1["hires"], y1["end"]) == (1.0, 0.9, 3.9, 12.0)
    assert y1["cost"] == D("162720.00")
    frozen = project(lines, 1, D("0.10"), D("0"), D("0"), D("0.13"), freeze=True)["lines"][0]
    assert frozen["hires"] == 0 and frozen["end"] == 8.1 and frozen["gap"] == 3.9
    cut = project(lines, 1, D("0"), D("0.05"), D("0"), D("0.13"), dept_adjust={"7": -25},
                  budget_cap=D("100000"))
    assert cut["lines"][0]["target"] == 9.0 and cut["years"][0]["over_budget"] is True


def test_plan_api_uses_live_data(team):
    from apps.talent.models import PlanLine, Scenario, WorkforcePlan

    plan = WorkforcePlan.objects.create(name="2027 plan", year=dt.date.today().year + 1, horizon_years=2)
    PlanLine.objects.create(plan=plan, department=team["dept"], planned_headcount=5, workload_units=D("20"),
                            workload_label="beds", target_ratio=D("0.25"))
    sc = Scenario.objects.create(plan=plan, name="Freeze", hiring_freeze=True, attrition_percent=D("0"))
    c = APIClient()
    c.force_authenticate(team["hrd"])
    r = c.get(f"/api/planning/plans/{plan.id}/project/", {"scenario": sc.id}).json()
    assert r["inputs"][0]["current"] == 3 and r["on_cost_percent"] == 13.0  # boss, Ama, Esi; employer SSNIT table
    assert r["lines"][0]["hires"] == 0 and r["workload"][0]["needed"] == 5.0
    est = c.get("/api/planning/establishment/").json()
    ops = next(d for d in est["departments"] if d["department"] == "Operations")
    assert ops["occupied"] == 3 and ops["actual"] == 3 * 5000 * 12
    c.force_authenticate(team["u_a"])
    assert c.get("/api/planning/establishment/").status_code == 403
