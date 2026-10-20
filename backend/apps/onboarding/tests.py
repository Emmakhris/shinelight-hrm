import datetime as dt

import pytest
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APIClient

from apps.core.exceptions import BusinessRuleError


@pytest.fixture
def newhire(org, make_employee, make_user):
    sup = make_employee(first="Kojo")
    sup_user = make_user("kojo", ("line_manager",), employee=sup)
    today = dt.date.today()
    emp = make_employee(first="Efua", supervisor=sup, hire_date=today,
                        probation_end_date=today + dt.timedelta(days=180))
    return {"sup": sup, "emp": emp, "sup_user": sup_user,
            "emp_user": make_user("efua", ("employee",), employee=emp), "hro": make_user("hro", ("hr_officer",)),
            "hrd": make_user("hrd", ("hr_director",)), "it": make_user("it", ("it_support",)),
            "adm": make_user("adm", ("admin_officer",)), "pay": make_user("pay", ("payroll_officer",))}


def _ob(emp):
    from apps.onboarding.models import Onboarding

    return Onboarding.objects.get(employee=emp)


def test_auto_start_and_routing(newhire, make_employee):
    from apps.onboarding import services
    from apps.onboarding.models import Onboarding

    ob = _ob(newhire["emp"])
    assert ob.status == "in_progress" and ob.start_date == newhire["emp"].hire_date
    mine = lambda u: set(services.tasks_for_user(newhire[u]).values_list("owner_type", flat=True))  # noqa: E731
    assert mine("it") == {"it"} and mine("adm") == {"admin"} and mine("pay") == {"finance"}
    assert mine("sup_user") == {"manager"} and mine("emp_user") == {"employee"}
    assert {"hr"} <= mine("hro")
    # historic hires (older than the auto-start window) are not onboarded
    old = make_employee(first="Old", hire_date=dt.date(2019, 1, 1))
    assert not Onboarding.objects.filter(employee=old).exists()
    with pytest.raises(BusinessRuleError):
        services.start(newhire["emp"])  # already in progress


def test_task_completion_rules_and_completion(newhire):
    from django.core.files.base import ContentFile

    from apps.documents.models import Document, DocumentCategory
    from apps.documents.services import add_version
    from apps.onboarding import services

    ob = _ob(newhire["emp"])
    it_task = ob.tasks.filter(owner_type="it").first()
    with pytest.raises(PermissionDenied):
        services.complete_task(it_task, newhire["emp_user"])
    services.complete_task(it_task, newhire["it"], notes="Account jdoe created")
    doc_task = ob.tasks.exclude(document_category=None).first()
    with pytest.raises(BusinessRuleError):
        services.complete_task(doc_task, newhire["hro"])
    doc = Document.objects.create(employee=newhire["emp"], category=doc_task.document_category, title="Upload")
    add_version(doc, ContentFile(b"%PDF-1.4", name="x.pdf"))
    services.complete_task(doc_task, newhire["hro"])
    survey = ob.tasks.get(category="survey")
    with pytest.raises(BusinessRuleError):
        services.complete_task(survey, newhire["emp_user"], {"welcome": 9})
    services.complete_task(survey, newhire["emp_user"], {"welcome": 5, "clarity": 4, "tools": 3, "comments": "Great"})
    assert survey.response["welcome"] == 5
    assert services.progress(ob)["done"] == 3
    for t in ob.tasks.filter(status="pending"):
        services.waive_task(t, newhire["hro"], "Not applicable")
    ob.refresh_from_db()
    assert ob.status == "completed" and ob.completed_at
    assert DocumentCategory.objects.filter(code="cv").exists()


def test_overdue_escalation_once(newhire):
    from apps.onboarding import services
    from apps.onboarding.models import OnboardingTask

    ob = _ob(newhire["emp"])
    n_overdue = ob.tasks.filter(due_date__lt=dt.date.today()).count()
    assert n_overdue > 0  # pre-boarding tasks are due before day one
    assert services.escalate_overdue() == n_overdue
    assert services.escalate_overdue() == 0
    assert OnboardingTask.objects.filter(escalated_at__isnull=False).count() == n_overdue
    assert services.dashboard()["overdue_tasks"] == n_overdue


def _final(emp):
    from apps.onboarding.models import ProbationReview

    return ProbationReview.objects.get(employee=emp, review_type="final", status="scheduled")


def _ratings(v=4):
    from apps.onboarding.models import ProbationReview

    return {c: v for c in ProbationReview.CRITERIA}


def _approve_all(rtype):
    from apps.workflow import engine
    from apps.workflow.models import WorkflowTask

    n = 0
    while (t := WorkflowTask.objects.filter(status="pending", instance__request_type=rtype).first()) is not None:
        engine.act(t, t.assignee, "approve", "Agreed")
        n += 1
    return n


def test_probation_confirmation(newhire):
    from apps.employees.models import EmploymentRecord
    from apps.onboarding import services
    from apps.onboarding.models import ProbationReview

    emp = newhire["emp"]
    reviews = ProbationReview.objects.filter(employee=emp)
    assert set(reviews.values_list("review_type", flat=True)) == {"midpoint", "final"}
    assert reviews.get(review_type="final").reviewer == newhire["sup_user"]
    final = _final(emp)
    with pytest.raises(PermissionDenied):
        services.submit_review(final, newhire["it"], {"ratings": _ratings(), "recommendation": "confirm"})
    with pytest.raises(BusinessRuleError):
        services.submit_review(final, newhire["sup_user"], {"ratings": _ratings(), "recommendation": "continue"})
    services.submit_review(final, newhire["sup_user"], {"ratings": _ratings(), "recommendation": "confirm",
                                                        "strengths": "Reliable"})
    assert final.status == "submitted" and final.overall_rating == 4
    # the employee cannot see the content before submission, but can after
    c = APIClient()
    c.force_authenticate(newhire["emp_user"])
    r = c.get("/api/onboarding/probation/")
    assert r.json()["results"][0]["recommendation"] == "confirm"
    assert _approve_all("probation_outcome") == 1  # confirmation: HR review only
    emp.refresh_from_db()
    final.refresh_from_db()
    assert final.status == "completed" and emp.confirmation_date == emp.probation_end_date
    # confirmation is effective-dated to the end of probation and applied on that day
    rec = EmploymentRecord.objects.get(employee=emp, event_type="confirmation")
    assert rec.effective_from == emp.probation_end_date and emp.status == "probation"
    from apps.employees.services import apply_due_records

    apply_due_records(today=emp.probation_end_date)
    emp.refresh_from_db()
    assert emp.status == "active"
    services.acknowledge_review(final, newhire["emp_user"], "Thank you")


def test_probation_extension_and_termination(newhire):
    from apps.onboarding import services
    from apps.onboarding.models import ProbationReview

    emp = newhire["emp"]
    old_end = emp.probation_end_date
    final = _final(emp)
    with pytest.raises(BusinessRuleError):
        services.submit_review(final, newhire["sup_user"], {"ratings": _ratings(2), "recommendation": "extend",
                                                            "extend_months": 3})  # gaps required
    services.submit_review(final, newhire["sup_user"], {"ratings": _ratings(2), "recommendation": "extend",
                                                        "extend_months": 3, "improvements": "Punctuality"})
    assert _approve_all("probation_outcome") == 2  # HR review + HR Director
    emp.refresh_from_db()
    assert emp.status == "probation" and emp.probation_end_date > old_end
    new_final = _final(emp)
    assert new_final.due_date == emp.probation_end_date - dt.timedelta(days=14)
    services.submit_review(new_final, newhire["sup_user"], {"ratings": _ratings(1), "recommendation": "terminate",
                                                            "improvements": "No improvement"})
    _approve_all("probation_outcome")
    emp.refresh_from_db()
    assert emp.status == "exited" and emp.exit_reason == "probation_termination" and not emp.rehire_eligible
    assert not ProbationReview.objects.filter(employee=emp, status="scheduled").exists()


def test_my_tasks_api_and_reminders(newhire):
    from apps.onboarding import services

    c = APIClient()
    c.force_authenticate(newhire["it"])
    r = c.get("/api/onboarding/tasks/", {"mine": 1})
    assert r.status_code == 200 and r.json()["count"] == 2
    tid = r.json()["results"][0]["id"]
    assert c.post(f"/api/onboarding/tasks/{tid}/complete/", {"notes": "Done"}, format="json").status_code == 200
    assert c.get("/api/onboarding/records/").status_code == 403
    c.force_authenticate(newhire["emp_user"])
    me = c.get("/api/me/onboarding/").json()
    assert me["onboarding"]["employee_name"] == newhire["emp"].full_name and len(me["my_tasks"]) == 4
    c.force_authenticate(newhire["hro"])
    assert c.get("/api/onboarding/records/dashboard/").json()["active"] == 1
    # reminders fire only for reviews due within a week
    from apps.onboarding.models import ProbationReview

    ProbationReview.objects.filter(review_type="midpoint").update(due_date=dt.date.today() + dt.timedelta(days=3))
    assert services.remind_due_reviews() == 1
    assert services.remind_due_reviews() == 0
