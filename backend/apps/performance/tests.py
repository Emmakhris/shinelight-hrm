import datetime as dt
from decimal import Decimal as D

import pytest
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APIClient

from apps.core.exceptions import BusinessRuleError


def _approve_all(rtype):
    from apps.workflow import engine
    from apps.workflow.models import WorkflowTask

    n = 0
    while (t := WorkflowTask.objects.filter(status="pending", instance__request_type=rtype).first()) is not None:
        engine.act(t, t.assignee, "approve", "OK")
        n += 1
    return n


@pytest.fixture
def team(org, make_employee, make_user):
    from apps.performance.models import ReviewCycle

    boss = make_employee(first="Kojo")
    a = make_employee(first="Ama", supervisor=boss)
    b = make_employee(first="Esi", supervisor=boss)
    users = {"boss": make_user("boss", ("line_manager",), employee=boss), "a": make_user("ama", ("employee",), employee=a),
             "b": make_user("esi", ("employee",), employee=b), "hro": make_user("hro", ("hr_officer",)),
             "p1": make_user("p1", ("employee",)), "p2": make_user("p2", ("employee",)),
             "p3": make_user("p3", ("employee",))}
    year = dt.date.today().year
    cycle = ReviewCycle.objects.create(name=f"Appraisal {year}", period_start=dt.date(year, 1, 1),
                                       period_end=dt.date(year, 12, 31), target_distribution={"5": 10, "3": 60})
    return {"cycle": cycle, "emp_a": a, "emp_b": b, **users}


def _objectives(ap, weights=(40, 30, 30)):
    from apps.performance.models import Objective

    for i, w in enumerate(weights):
        Objective.objects.create(appraisal=ap, title=f"Objective {i + 1}", measure="KPI", weight=D(w))


def _launched(team):
    from apps.performance import services
    from apps.performance.models import Appraisal

    res = services.launch_cycle(team["cycle"], team["hro"])
    assert res["created"] == 3  # boss, Ama, Esi
    return Appraisal.objects.get(employee=team["emp_a"]), Appraisal.objects.get(employee=team["emp_b"])


def _rate(ap, field, value):
    return {"objectives": [{"id": o.id, field: value} for o in ap.objectives.all()],
            "competencies": [{"id": c.id, field: value} for c in ap.competency_ratings.all()]}


def _to_review(team, a, b):
    from apps.performance import services

    for ap in (a, b):
        _objectives(ap)
    services.submit_objectives(a, team["a"])
    services.submit_objectives(b, team["boss"])  # reviewer sets them: agreed directly
    assert _approve_all("appraisal_objectives") == 1
    services.advance_cycle(team["cycle"], team["hro"])  # -> in progress
    services.advance_cycle(team["cycle"], team["hro"])  # -> year-end review
    a.refresh_from_db()
    b.refresh_from_db()
    assert a.status == b.status == "self_review"


def test_launch_templates_and_objectives(team):
    from apps.performance import services

    a, b = _launched(team)
    assert a.template.name == "Standard staff appraisal" and a.reviewer == team["boss"]
    assert a.competency_ratings.count() == 7
    _objectives(a, (50, 30))
    with pytest.raises(BusinessRuleError):  # 2 objectives < minimum 3, weights 80
        services.submit_objectives(a, team["a"])
    _objectives(a, (20,))
    with pytest.raises(PermissionDenied):
        services.submit_objectives(a, team["b"])
    services.submit_objectives(a, team["a"])
    a.refresh_from_db()
    assert a.status == "objectives_pending"
    assert _approve_all("appraisal_objectives") == 1
    a.refresh_from_db()
    assert a.status == "objectives_agreed"
    services.record_midyear(a, team["boss"], [{"id": a.objectives.first().id, "midyear_status": "at_risk"}],
                            "Behind on objective 1")
    assert a.objectives.first().midyear_status == "at_risk"


def test_review_scoring_calibration_and_acknowledgment(team):
    from apps.performance import services

    a, b = _launched(team)
    _to_review(team, a, b)
    with pytest.raises(BusinessRuleError):
        services.save_self_review(a, team["a"], {}, submit=True)  # everything must be rated
    services.save_self_review(a, team["a"], {**_rate(a, "self_rating", 4), "self_comments": "Good year"}, submit=True)
    a.refresh_from_db()
    assert a.status == "manager_review"
    with pytest.raises(PermissionDenied):
        services.save_manager_review(a, team["a"], _rate(a, "manager_rating", 5), submit=True)
    # employee must not see manager ratings before release
    services.save_manager_review(a, team["boss"], _rate(a, "manager_rating", 4), submit=False)
    c = APIClient()
    c.force_authenticate(team["a"])
    r = c.get(f"/api/performance/appraisals/{a.id}/").json()
    assert r["role"] == "employee" and r["objectives"][0]["manager_rating"] is None and r["overall_score"] is None
    data = _rate(a, "manager_rating", 4)
    data["objectives"][0]["manager_rating"] = 3  # 40% x 3 + 30% x 4 + 30% x 4 = 3.6 ; competencies 4
    services.save_manager_review(a, team["boss"], data, submit=True)
    a.refresh_from_db()
    assert a.objectives_score == D("3.60") and a.competencies_score == D("4.00")
    assert a.overall_score == D("3.72") and a.manager_rating == a.final_rating == 4 and a.status == "calibration"
    # a low rating needs comments and a development plan
    services.save_self_review(b, team["b"], _rate(b, "self_rating", 3), submit=True)
    b.refresh_from_db()
    with pytest.raises(BusinessRuleError):
        services.save_manager_review(b, team["boss"], _rate(b, "manager_rating", 2), submit=True)
    services.save_manager_review(b, team["boss"], {**_rate(b, "manager_rating", 2), "manager_comments": "Missed targets",
                                                   "development_needs": "Excel training"}, submit=True)
    with pytest.raises(BusinessRuleError):
        services.calibrate(a, team["hro"], 5)  # change needs a reason
    services.calibrate(a, team["hro"], 5, "Led the ward accreditation project")
    summary = services.cycle_summary(team["cycle"])
    assert summary["calibrated_changes"] == 1 and summary["low_ratings_without_plan"] == 1
    services.advance_cycle(team["cycle"], team["hro"])  # -> calibration
    out = services.advance_cycle(team["cycle"], team["hro"])  # release + close
    assert out["released"] == 2 and team["cycle"].status == "closed"
    r = c.get(f"/api/performance/appraisals/{a.id}/").json()
    assert r["final_rating"] == 5 and r["final_rating_label"] == "Outstanding" and r["calibration_reason"] == ""
    with pytest.raises(BusinessRuleError):
        services.acknowledge(a, team["a"], False)
    a.refresh_from_db()
    services.acknowledge(a, team["a"], True, "Thank you")
    assert a.status == "completed" and services.latest_rating(team["emp_a"]) == 5


def test_360_feedback_is_anonymous_with_threshold(team):
    from apps.performance import services
    from apps.performance.models import AppraisalTemplate, FeedbackRequest

    AppraisalTemplate.objects.filter(name="Standard staff appraisal").update(include_360=True)
    a, _ = _launched(team)
    services.request_feedback(a, team["a"], [{"user": team[p].id, "relationship": "peer"} for p in ("p1", "p2", "p3")]
                              + [{"user": team["a"].id}])  # self is ignored
    reqs = list(FeedbackRequest.objects.filter(appraisal=a))
    assert len(reqs) == 3
    comp = a.competency_ratings.first().competency_id
    with pytest.raises(PermissionDenied):
        services.submit_feedback(reqs[0], team["p2"], {comp: 4})
    services.submit_feedback(reqs[0], team["p1"], {comp: 4}, "Very helpful")
    services.submit_feedback(reqs[1], team["p2"], {comp: 2}, improvements="Late replies")
    s = services.feedback_summary(a)
    assert s["sufficient"] is False and "competencies" not in s
    services.submit_feedback(reqs[2], team["p3"], {comp: 3})
    s = services.feedback_summary(a)
    assert s["sufficient"] and s["competencies"][0]["average"] == D("3.00")
    assert "p1" not in str(s) and s["strengths"] == ["Very helpful"]
    c = APIClient()
    c.force_authenticate(team["p1"])
    assert c.get("/api/performance/feedback/").json()["count"] == 1
    c.force_authenticate(team["a"])
    assert c.get("/api/performance/feedback/").json()["count"] == 0
    # the employee sees the summary only after the review is released
    assert c.get(f"/api/performance/appraisals/{a.id}/feedback-summary/").json() == {"available_after_review": True}


def test_improvement_plan_flow(team):
    from apps.performance import services
    from apps.performance.models import ImprovementPlan, PlanMilestone

    today = dt.date.today()
    plan = ImprovementPlan.objects.create(employee=team["emp_b"], supervisor=team["boss"], reason="Targets missed",
                                          start_date=today, end_date=today + dt.timedelta(days=60))
    with pytest.raises(BusinessRuleError):
        services.submit_plan(plan, team["boss"])  # no milestones / support
    PlanMilestone.objects.create(plan=plan, objective="Close 20 files a week", due_date=today + dt.timedelta(days=30))
    plan.support = "Weekly coaching with the supervisor"
    plan.save()
    services.submit_plan(plan, team["boss"])
    c = APIClient()
    c.force_authenticate(team["b"])
    assert c.get("/api/performance/plans/").json()["count"] == 0  # not visible to the employee until approved
    assert _approve_all("improvement_plan") == 1
    plan.refresh_from_db()
    assert plan.status == "active"
    assert c.get("/api/performance/plans/").json()["count"] == 1
    assert c.post(f"/api/performance/plans/{plan.id}/acknowledge/", {"comments": "I will try"},
                  format="json").status_code == 200
    with pytest.raises(PermissionDenied):
        services.close_plan(plan, team["b"], "successful", "x")
    services.close_plan(plan, team["boss"], "successful", "All milestones met")
    assert plan.status == "successful" and plan.closed_at


def test_salary_review_guideline_uses_rating(team):
    from apps.compensation import services as comp
    from apps.compensation.models import SalaryReviewCycle
    from apps.performance import services
    from apps.performance.models import Appraisal

    a, b = _launched(team)
    Appraisal.objects.filter(pk=a.pk).update(final_rating=5, status="completed")
    Appraisal.objects.filter(pk=b.pk).update(final_rating=2, status="completed")
    year = team["cycle"].period_end.year
    cycle = SalaryReviewCycle.objects.create(name="Merit", effective_date=dt.date(year + 1, 1, 1),
                                             default_increase_percent=D("5"), guidelines=[
                                                 {"min_level": 0, "max_level": 99, "rating": 5, "min": 8, "max": 12,
                                                  "default": 10},
                                                 {"min_level": 0, "max_level": 99, "rating": 2, "min": 0, "max": 3,
                                                  "default": 0},
                                                 {"min_level": 0, "max_level": 99, "min": 3, "max": 6}])
    comp.populate_cycle(cycle)
    la = cycle.lines.get(employee=team["emp_a"])
    lb = cycle.lines.get(employee=team["emp_b"])
    assert la.increase_percent == D("10") and not la.outside_guideline
    assert lb.increase_percent == D("0") and comp.guideline_for(cycle, team["emp_b"]) == (D("0"), D("3"))
    assert services.latest_rating(team["emp_a"]) == 5
