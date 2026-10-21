import datetime as dt
from decimal import Decimal as D

import pytest
from django.utils import timezone
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
def people(org, make_employee, make_user):
    boss = make_employee(first="Kojo")
    a = make_employee(first="Ama", supervisor=boss)
    b = make_employee(first="Esi", supervisor=boss)
    return {"boss": boss, "a": a, "b": b, "u_boss": make_user("boss", ("line_manager",), employee=boss),
            "u_a": make_user("ama", ("employee",), employee=a), "u_b": make_user("esi", ("employee",), employee=b),
            "trainer": make_user("trainer", ("training_officer",)), "hrd": make_user("hrd", ("hr_director",))}


def _course(code):
    from apps.learning.models import Course

    return Course.objects.get(code=code)


def test_paid_request_approval_and_budget_routing(people):
    from apps.learning import services
    from apps.learning.models import TrainingBudget

    TrainingBudget.objects.create(department=people["a"].department, year=dt.date.today().year, amount=D("10000"))
    gimpa = _course("LD-401")  # external, GHS 3,500
    with pytest.raises(BusinessRuleError):
        services.request_training(people["a"], gimpa, people["u_a"])  # reason required
    e = services.request_training(people["a"], gimpa, people["u_a"], reason="Preparing to supervise the unit")
    assert e.status == "pending" and e.cost == D("3500.00")
    assert services.budget_status(people["a"].department, dt.date.today().year)["pending"] == D("3500.00")
    with pytest.raises(BusinessRuleError):
        services.request_training(people["a"], gimpa, people["u_a"], reason="again")  # duplicate
    assert _approve_all("training_request") == 3  # supervisor, training officer, HR Director (> GHS 2,000)
    e.refresh_from_db()
    assert e.status == "enrolled"
    assert services.budget_status(people["a"].department, dt.date.today().year)["available"] == D("6500.00")
    # free internal course enrols directly; nominating someone outside your team is refused
    excel = _course("TS-501")
    e2 = services.request_training(people["b"], excel, people["u_boss"], reason="Monthly reports", source="manager")
    assert e2.status == "enrolled"
    with pytest.raises(PermissionDenied):
        services.request_training(people["boss"], excel, people["u_a"], reason="x")


def test_session_capacity_waitlist_attendance_and_evaluation(people):
    from apps.learning import services
    from apps.learning.models import Session

    bls = _course("CL-302")
    now = timezone.now()
    s = Session.objects.create(course=bls, start=now + dt.timedelta(days=3), end=now + dt.timedelta(days=3, hours=6),
                               capacity=1, venue="Skills lab", trainer="Dr Mensah")
    with pytest.raises(BusinessRuleError):
        services.request_training(people["a"], bls, people["u_a"], reason="Renewal")  # session required
    e1 = services.request_training(people["a"], bls, people["u_a"], session=s, reason="Renewal")
    e2 = services.request_training(people["b"], bls, people["u_b"], session=s, reason="Renewal")
    assert e1.status == "enrolled" and e2.status == "waitlisted"
    services.cancel(e1, people["u_a"])
    e2.refresh_from_db()
    assert e2.status == "enrolled"  # promoted from the waitlist
    with pytest.raises(BusinessRuleError):
        services.record_attendance(s, people["trainer"], [{"enrollment": e2.id, "attended": True}])  # future
    Session.objects.filter(pk=s.pk).update(start=now - dt.timedelta(days=1), end=now - dt.timedelta(hours=18))
    s.refresh_from_db()
    services.record_attendance(s, people["trainer"], [{"enrollment": e2.id, "attended": True, "score": 85}])
    e2.refresh_from_db()
    assert e2.status == "completed" and e2.expires_on and e2.cpd_record.credits == D("6.0")
    with pytest.raises(PermissionDenied):
        services.give_feedback(e2, people["u_a"], 5)
    services.give_feedback(e2, people["u_b"], 4, "Hands-on and useful")
    with pytest.raises(PermissionDenied):
        services.evaluate_effectiveness(e2, people["u_b"], 5)  # not the employee themselves
    services.evaluate_effectiveness(e2, people["u_boss"], 4, "Led a resuscitation confidently")
    rep = services.report()
    assert rep["completions"] == 1 and rep["avg_feedback"] == 4 and rep["avg_effectiveness"] == 4


def test_elearning_quiz_completion_and_hidden_answers(people):
    from apps.learning import services

    fire = _course("HS-101")
    e = services.request_training(people["a"], fire, people["u_a"])
    c = APIClient()
    c.force_authenticate(people["u_a"])
    detail = c.get(f"/api/learning/enrollments/{e.id}/").json()
    assert len(detail["questions"]) == 3 and all("correct" not in q for q in detail["questions"])
    with pytest.raises(BusinessRuleError):
        services.submit_quiz(e, people["u_a"], {})  # modules first
    for m in fire.modules.all():
        services.mark_module(e, m.id, people["u_a"])
    qs = list(fire.questions.all())
    assert services.submit_quiz(e, people["u_a"], {str(qs[0].id): [0], str(qs[1].id): [2], str(qs[2].id): [1]}) == 67
    e.refresh_from_db()
    assert e.status == "in_progress" and e.attempts == 1
    score = c.post(f"/api/learning/enrollments/{e.id}/quiz/", {"answers": {str(q.id): q.correct for q in qs}},
                   format="json").json()
    assert score["passed"] and score["status"] == "completed"
    e.refresh_from_db()
    assert e.expires_on.year == dt.date.today().year + 1


def test_mandatory_assignment_and_compliance(people):
    from apps.hospital.models import CompetencyRecord, CompetencyRequirement
    from apps.learning import services
    from apps.learning.models import Enrollment

    req = CompetencyRequirement.objects.create(name="BLS", refresh_months=24)
    bls = _course("CL-302")
    bls.job_titles.add(people["a"].job_title)
    bls.competency_requirement = req
    bls.save()
    n = services.assign_mandatory()
    # every active employee: fire safety + data protection; plus BLS for the job title (all share it here)
    assert n == 3 * 3
    assert services.assign_mandatory() == 0  # idempotent
    m = services.compliance_matrix()
    assert m["compliance_percent"] == 0 and len(m["rows"]) == 3
    e = Enrollment.objects.get(employee=people["a"], course=bls)
    services.complete(e, dt.date.today() - dt.timedelta(days=700), assessor="Skills lab")
    assert CompetencyRecord.objects.filter(employee=people["a"], requirement=req).exists()  # renews the credential
    status, _ = services.course_status(people["a"], bls)
    assert status == "expiring"  # 24 months minus 700 days leaves < 60 days
    assert services.assign_mandatory() == 1  # refresher opened before it lapses
    m = services.compliance_matrix()
    assert m["rows"][0]["cells"][str(bls.id)]["status"] in ("expiring", "missing")


def test_cpd_and_development_from_appraisal(people):
    from apps.learning import services
    from apps.learning.models import CPDRecord, CPDRequirement
    from apps.performance import services as perf
    from apps.performance.models import Appraisal, Competency, ReviewCycle

    req = CPDRequirement.objects.create(name="Nursing council renewal", credits_per_year=D("20"))
    req.job_titles.add(people["a"].job_title)
    rec = CPDRecord.objects.create(employee=people["a"], title="Wound care seminar", activity_date=dt.date.today(),
                                   credits=D("8"))
    assert services.cpd_summary(people["a"])["earned"] == 0  # pending until verified
    services.verify_cpd(rec, people["trainer"])
    s = services.cpd_summary(people["a"])
    assert s["earned"] == D("8") and s["shortfall"] == D("12")
    # training needs and IDP from an appraisal
    year = dt.date.today().year
    cycle = ReviewCycle.objects.create(name="Y", period_start=dt.date(year - 1, 1, 1), period_end=dt.date(year - 1, 12, 31))
    perf.launch_cycle(cycle, people["hrd"])
    ap = Appraisal.objects.get(cycle=cycle, employee=people["a"])
    comm = Competency.objects.get(name="Communication")
    ap.competency_ratings.filter(competency=comm).update(manager_rating=2)
    ap.final_rating, ap.development_needs = 2, "Report writing course"
    ap.save()
    _course("TS-501").competencies.add(comm)
    needs = services.training_needs()
    gap = next(g for g in needs["competency_gaps"] if g["competency"] == "Communication")
    assert gap["people"] == 1 and gap["courses"][0]["title"] == "Excel for reporting"
    c = APIClient()
    c.force_authenticate(people["u_boss"])
    r = c.post("/api/learning/development-goals/from-appraisal/", {"appraisal": ap.id}, format="json")
    assert r.status_code == 200 and r.json()["created"] == 1
    goals = c.get("/api/learning/development-goals/").json()["results"]
    assert goals[0]["competency_name"] == "Communication" and goals[0]["courses"]
    c.force_authenticate(people["u_b"])
    assert c.get("/api/learning/development-goals/").json()["count"] == 0  # not visible to a peer
