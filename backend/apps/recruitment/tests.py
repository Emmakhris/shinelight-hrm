import datetime as dt
from decimal import Decimal as D

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APIClient

from apps.core.exceptions import BusinessRuleError


def _approve_all(rtype):
    from apps.workflow import engine
    from apps.workflow.models import WorkflowTask

    n = 0
    while True:
        task = WorkflowTask.objects.filter(status="pending", instance__request_type=rtype).first()
        if task is None:
            return n
        engine.act(task, task.assignee, "approve", "OK")
        n += 1


@pytest.fixture
def setup(org, structure, make_employee, make_user):
    mgr = make_employee(first="Kojo")
    users = {
        "mgr": make_user("mgr", ("line_manager",), employee=mgr),
        "rec": make_user("rec", ("recruitment_officer",)),
        "hrd": make_user("hrd", ("hr_director",)),
        "fin": make_user("fin", ("finance_officer",)),
        "panel": make_user("panel", ("employee",)),
        "hro": make_user("hro", ("hr_officer",)),
        "it": make_user("it", ("it_support",)),
    }
    return {"mgr_emp": mgr, **users, **structure}


def _requisition(s, **kw):
    from apps.recruitment.models import Requisition

    data = {"job_title": s["title"], "department": s["dept"], "position": s["pos"], "grade": s["grade"],
            "headcount": 1, "reason": "new", "justification": "Workload has doubled", "salary_min": D("4000"),
            "salary_max": D("5000"), "requested_by": s["mgr_emp"], "created_by": s["mgr"]}
    data.update(kw)
    return Requisition.objects.create(**data)


def _open_vacancy(s, **kw):
    from apps.recruitment import services

    req = _requisition(s)
    services.submit_requisition(req, s["mgr"])
    assert _approve_all("job_requisition") == 2  # HOD step skipped (no head); HR Director + finance
    req.refresh_from_db()
    assert req.status == "approved" and req.approved_at
    v = services.vacancy_from_requisition(req, s["rec"])
    v.summary = "Lead operations"
    v.closing_date = dt.date.today() + dt.timedelta(days=14)
    v.min_qualification = "degree"
    v.min_experience_years = 3
    v.screening_questions = [{"key": "license", "question": "Do you hold a valid driving licence?",
                              "type": "yes_no", "knockout": "no"}]
    for k, val in kw.items():
        setattr(v, k, val)
    v.save()
    return services.publish_vacancy(v, s["rec"])


def _cv():
    return SimpleUploadedFile("cv.pdf", b"%PDF-1.4 test cv", content_type="application/pdf")


def test_requisition_approval_and_vacancy_publish(setup):
    v = _open_vacancy(setup)
    assert v.status == "published" and v.reference.startswith("VAC-") and "career_site" in v.channels


def test_requisition_blocks_frozen_position(setup):
    from apps.recruitment import services

    setup["pos"].status = "frozen"
    setup["pos"].save()
    with pytest.raises(BusinessRuleError):
        services.submit_requisition(_requisition(setup), setup["mgr"])


def test_public_application_screening_and_rules(setup, org):
    from apps.recruitment.models import Application

    v = _open_vacancy(setup)
    c = APIClient()
    url = f"/api/public/careers/{org.code}/{v.id}/apply/"
    base = {"first_name": "Akosua", "last_name": "Owusu", "email": "akosua@example.com", "phone": "0241234567",
            "highest_qualification": "degree", "years_experience": "1.5", "answers": '{"license": "no"}'}
    r = c.post(url, {**base, "cv": _cv(), "consent": "false"}, format="multipart")
    assert r.status_code == 400 and "consent" in r.json()["detail"].lower()
    r = c.post(url, {**base, "cv": _cv(), "consent": "true", "talent_pool": "true"}, format="multipart")
    assert r.status_code == 201, r.content
    app = Application.objects.get(reference=r.json()["reference"])
    # advisory screening: knock-out flagged, experience short, but never auto-rejected
    assert app.stage == "applied" and app.knocked_out and app.screening_score < 100
    assert any("experience" in f for f in app.screening_flags)
    assert app.candidate.talent_pool and app.candidate.retain_until
    r = c.post(url, {**base, "cv": _cv(), "consent": "true"}, format="multipart")
    assert r.status_code == 400 and r.json()["code"] == "duplicate_application"
    # listing is public and hides internal-only vacancies
    assert c.get(f"/api/public/careers/{org.code}/").json()["vacancies"][0]["id"] == v.id
    v.visibility = "internal"
    v.save()
    assert c.get(f"/api/public/careers/{org.code}/").json()["vacancies"] == []
    assert c.get("/api/public/careers/nope/").status_code == 404


def test_internal_application(setup, make_employee, make_user):
    v = _open_vacancy(setup, visibility="internal")
    emp = make_employee(first="Yaw")
    user = make_user("yaw", ("employee",), employee=emp)
    c = APIClient()
    c.force_authenticate(user)
    r = c.get("/api/me/vacancies/")
    assert [x["id"] for x in r.json()["vacancies"]] == [v.id]
    r = c.post("/api/me/vacancies/", {"vacancy": v.id, "consent": True, "highest_qualification": "degree",
                                      "years_experience": 4, "answers": {"license": "yes"}}, format="json")
    assert r.status_code == 201, r.content
    assert c.get("/api/me/vacancies/").json()["my_applications"][0]["reference"] == r.json()["reference"]


def _applied(setup, email="ama@example.com"):
    from apps.recruitment import services

    v = _open_vacancy(setup)
    return services.apply(v, {"first_name": "Ama", "last_name": "Serwaa", "email": email, "phone": "0201234567",
                              "highest_qualification": "masters", "years_experience": 6, "gender": "female"},
                          cv=_cv(), answers={"license": "yes"}, consent=True)


def test_pipeline_interview_scorecards_and_checks(setup):
    from apps.recruitment import services

    app = _applied(setup)
    assert not app.knocked_out and app.screening_score == 100
    with pytest.raises(BusinessRuleError):
        services.move_stage(app, "rejected", setup["rec"])  # reason required
    with pytest.raises(BusinessRuleError):
        services.move_stage(app, "hired", setup["rec"])
    services.move_stage(app, "shortlisted", setup["rec"])
    iv = services.schedule_interview(app, {"round_name": "Panel interview",
                                           "scheduled_at": timezone.now() + dt.timedelta(minutes=10)},
                                     [setup["panel"], setup["hrd"]], setup["rec"])
    app.refresh_from_db()
    assert app.stage == "interview" and iv.candidate_notified
    crit = {c["name"]: 4 for c in app.vacancy.criteria}
    with pytest.raises(PermissionDenied):
        services.submit_scorecard(iv, setup["fin"], crit, "yes")
    with pytest.raises(BusinessRuleError):
        services.submit_scorecard(iv, setup["panel"], crit, "no")  # concerns required
    sc = services.submit_scorecard(iv, setup["panel"], crit, "yes", strengths="Strong ops background")
    assert sc.overall_score == D("80.00")
    services.submit_scorecard(iv, setup["hrd"], {k: 5 for k in crit}, "strong_yes")
    iv.refresh_from_db()
    assert iv.status == "completed"
    summary = services.interview_summary(app)
    assert summary["scorecards"] == 2 and summary["average_score"] == D("90.00")
    from apps.recruitment.models import ReferenceCheck

    chk = ReferenceCheck.objects.create(application=app, referee_name="Mr Boateng", check_type="reference")
    with pytest.raises(BusinessRuleError):
        services.update_check(chk, setup["rec"], "verified", "Good")  # no consent yet
    chk.consent_obtained = True
    services.update_check(chk, setup["rec"], "verified", "Confirmed dates and conduct")
    app.refresh_from_db()
    assert app.stage == "reference_check"


def _accepted_offer(setup, salary="5500"):
    from apps.recruitment import services

    app = _applied(setup)
    services.schedule_interview(app, {"scheduled_at": timezone.now() + dt.timedelta(minutes=5)}, [setup["panel"]],
                                setup["rec"], notify=False)
    offer = services.create_offer(app, {
        "job_title": setup["title"], "department": setup["dept"], "grade_step": setup["step"],
        "basic_salary": D(salary), "allowances": [{"name": "Transport", "amount": 300}],
        "start_date": dt.date.today() + dt.timedelta(days=14), "probation_months": 6,
        "expiry_date": dt.date.today() + dt.timedelta(days=7)}, setup["rec"])
    assert offer.reference.startswith("OFF-") and offer.supervisor == setup["mgr_emp"]
    assert any("budget" in w for w in services.offer_warnings(offer))
    services.submit_offer(offer, setup["rec"])
    assert _approve_all("job_offer") == 2  # above budget: HR Director + finance
    offer.refresh_from_db()
    assert offer.status == "approved"
    services.send_offer(offer, setup["rec"])
    assert offer.token and offer.letter
    return offer


def test_offer_digital_acceptance_and_hire(setup, org):
    from apps.documents.models import Document
    from apps.onboarding.models import Onboarding, ProbationReview
    from apps.recruitment import services

    offer = _accepted_offer(setup)
    c = APIClient()
    r = c.get(f"/api/public/offers/{offer.token}/")
    assert r.status_code == 200 and r.json()["candidate_name"] == "Ama Serwaa"
    assert c.get(f"/api/public/offers/{offer.token}/?letter=1").status_code == 200
    r = c.post(f"/api/public/offers/{offer.token}/", {"decision": "accept", "typed_name": "Someone Else"},
               format="json")
    assert r.status_code == 400
    r = c.post(f"/api/public/offers/{offer.token}/", {"decision": "accept", "typed_name": "ama  serwaa"},
               format="json")
    assert r.status_code == 200 and r.json()["status"] == "accepted"
    offer.refresh_from_db()
    emp = services.hire_from_offer(offer, setup["rec"])
    assert emp.status == "probation" and emp.basic_salary == D("5500.00") and emp.supervisor == setup["mgr_emp"]
    assert emp.probation_end_date == offer.start_date + dt.timedelta(days=180)
    app = offer.application
    app.refresh_from_db()
    assert app.stage == "hired" and app.hired_employee == emp
    req = app.vacancy.requisition
    req.refresh_from_db()
    app.vacancy.refresh_from_db()
    assert req.status == "filled" and app.vacancy.status == "filled"
    assert set(Document.objects.filter(employee=emp).values_list("category__code", flat=True)) == {"cv",
                                                                                                    "appointment"}
    ob = Onboarding.objects.get(employee=emp)  # started automatically on hire
    assert ob.offer == offer and ob.tasks.count() > 10
    assert ProbationReview.objects.filter(employee=emp).count() == 2
    with pytest.raises(BusinessRuleError):
        services.hire_from_offer(offer, setup["rec"])


def test_offer_revision_and_decline(setup):
    from apps.recruitment import services

    offer = _accepted_offer(setup)
    services.respond_offer(offer, "negotiate", note="Could the transport allowance be GHS 500?")
    assert offer.status == "negotiating"
    rev = services.create_offer(offer.application, {
        "job_title": setup["title"], "department": setup["dept"], "basic_salary": D("4800"),
        "start_date": offer.start_date, "expiry_date": offer.expiry_date}, setup["rec"])
    offer.refresh_from_db()
    assert rev.revision == 2 and rev.reference == offer.reference and offer.status == "superseded"
    services.submit_offer(rev, setup["rec"])
    assert _approve_all("job_offer") == 1  # within budget: HR Director only
    rev.refresh_from_db()
    services.send_offer(rev, setup["rec"])
    services.respond_offer(rev, "decline", note="Accepted another role")
    rev.application.refresh_from_db()
    assert rev.application.stage == "withdrawn"
    with pytest.raises(BusinessRuleError):
        services.respond_offer(rev, "accept", "Ama Serwaa")


def test_retention_anonymises_unsuccessful_candidates(setup):
    from apps.recruitment import services

    app = _applied(setup, email="old@example.com")
    services.move_stage(app, "rejected", setup["rec"], reason="Not shortlisted")
    cand = app.candidate
    cand.retain_until = dt.date.today() - dt.timedelta(days=1)
    cand.save()
    assert services.purge_expired_candidates() == 1
    cand.refresh_from_db()
    app.refresh_from_db()
    assert cand.anonymised and cand.email.endswith("redacted.invalid") and not app.cv


def test_analytics_and_permissions(setup):
    _accepted_offer(setup)
    c = APIClient()
    c.force_authenticate(setup["rec"])
    r = c.get("/api/recruitment/analytics/")
    assert r.status_code == 200
    data = r.json()
    assert data["applications"] == 1 and data["funnel"][0]["count"] == 1 and data["open_vacancies"] == 1
    c.force_authenticate(setup["panel"])
    assert c.get("/api/recruitment/analytics/").status_code == 403
    assert c.get("/api/recruitment/applications/").status_code == 403
    assert c.get("/api/recruitment/offers/").status_code == 403
    # panel members only see their own interviews
    r = c.get("/api/recruitment/interviews/")
    assert r.status_code == 200 and r.json()["count"] == 1
    c.force_authenticate(setup["mgr"])
    r = c.post("/api/recruitment/requisitions/", {
        "job_title": setup["title"].id, "department": setup["dept"].id, "headcount": 1, "reason": "expansion",
        "justification": "New shift", "salary_max": "4000", "submit": True}, format="json")
    assert r.status_code == 201, r.content
    assert r.json()["status"] == "pending"
    assert c.get("/api/recruitment/requisitions/").json()["count"] == 2  # fixture requisition + this one
