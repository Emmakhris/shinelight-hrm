import datetime as dt

import pytest
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APIClient

from apps.core.exceptions import BusinessRuleError


@pytest.fixture
def er(org, make_employee, make_user):
    boss = make_employee(first="Kojo")
    a = make_employee(first="Ama", supervisor=boss)
    b = make_employee(first="Esi", supervisor=boss)
    return {"boss": boss, "a": a, "b": b,
            "u_boss": make_user("boss", ("line_manager", "employee"), employee=boss),
            "u_a": make_user("ama", ("employee",), employee=a), "u_b": make_user("esi", ("employee",), employee=b),
            "hro": make_user("hro", ("hr_officer",)), "hrd": make_user("hrd", ("hr_director",))}


def _approve_all(rtype):
    from apps.workflow import engine
    from apps.workflow.models import WorkflowTask

    n = 0
    while (t := WorkflowTask.objects.filter(status="pending", instance__request_type=rtype).first()) is not None:
        engine.act(t, t.assignee, "approve", "OK")
        n += 1
    return n


def test_confidential_report_and_access(er):
    from apps.relations import services

    case = services.open_case(er["u_a"], {"case_type": "harassment", "description": "Repeated remarks",
                                          "is_anonymous": True, "severity": "high"}, respondents=[er["b"]])
    assert case.reference.startswith("ER-") and case.case_officer == er["hro"]  # least-loaded handler, not HRD
    assert case.due_date == dt.date.today() + dt.timedelta(days=14)
    with pytest.raises(PermissionDenied):
        services.open_case(er["u_a"], {"case_type": "disciplinary", "description": "x"})
    c = APIClient()
    c.force_authenticate(er["hro"])
    r = c.get(f"/api/relations/cases/{case.id}/").json()
    assert r["reporter_name"] == "Anonymous" and r["complainant_name"] == "Anonymous"
    c.force_authenticate(er["hrd"])
    assert c.get(f"/api/relations/cases/{case.id}/").json()["complainant_name"] == er["a"].full_name
    # the line manager and the respondent cannot see the case at all
    for u in ("u_boss", "u_b"):
        c.force_authenticate(er[u])
        assert c.get(f"/api/relations/cases/{case.id}/").status_code == 404
        assert c.get("/api/relations/cases/").json()["count"] == 0
    c.force_authenticate(er["u_a"])
    mine = c.get("/api/relations/my/").json()
    assert mine["raised"][0]["reference"] == case.reference and "description" not in mine["raised"][0]


def test_disciplinary_needs_hearing_and_appeal_is_independent(er):
    from apps.documents.models import Document
    from apps.relations import services

    case = services.open_case(er["hro"], {"case_type": "misconduct", "description": "Absent without leave 3 days",
                                          "severity": "medium"}, respondents=[er["a"]])
    assert case.complainant is None and case.case_officer == er["hro"]
    action = {"employee": er["a"], "action_type": "written_warning", "details": "Unauthorised absence"}
    with pytest.raises(BusinessRuleError):
        services.decide(case, er["hro"], "written_warning", "Proven", [action])  # no hearing yet
    m = services.schedule_meeting(case, er["hro"], {"kind": "hearing", "scheduled_at": timezone.now()}, [er["a"]])
    case.refresh_from_db()
    assert case.status == "hearing"
    services.record_minutes(m, er["hro"], "Employee admitted absence; no mitigating evidence.")
    services.decide(case, er["hro"], "written_warning", "Absence proven at hearing", [action])
    case.refresh_from_db()
    a = case.actions.get()
    assert case.status == "decided" and a.issued_at and a.expires_on and a.appeal_deadline
    doc = Document.objects.get(pk=a.letter_id)
    assert doc.category.code == "disciplinary" and doc.confidentiality == "restricted"
    assert services.active_warnings(er["a"]).count() == 1
    with pytest.raises(PermissionDenied):
        services.lodge_appeal(a, er["u_b"], "not mine")
    services.respond(a, er["u_a"], "I was caring for a sick parent.")
    appeal = services.lodge_appeal(a, er["u_a"], "Mitigating circumstances not considered")
    with pytest.raises(BusinessRuleError):
        services.lodge_appeal(a, er["u_a"], "again")
    with pytest.raises(PermissionDenied):
        services.decide_appeal(appeal, er["hro"], "upheld", "x")  # not senior
    services.decide_appeal(appeal, er["hrd"], "upheld", "Medical evidence accepted")
    a.refresh_from_db()
    assert "Rescinded" in a.details and services.active_warnings(er["a"]).count() == 0
    services.close(case, er["hro"], "Done")
    assert case.status == "closed"


def test_dismissal_needs_hr_director_and_starts_offboarding(er):
    from apps.offboarding.models import Separation
    from apps.relations import services

    case = services.open_case(er["hro"], {"case_type": "misconduct", "description": "Theft of drugs",
                                          "severity": "critical"}, respondents=[er["b"]])
    m = services.schedule_meeting(case, er["hro"], {"kind": "hearing", "scheduled_at": timezone.now()}, [er["b"]])
    services.record_minutes(m, er["hro"], "Evidence presented; employee heard.")
    services.decide(case, er["hro"], "dismissal", "Gross misconduct proven",
                    [{"employee": er["b"], "action_type": "dismissal", "details": "Summary dismissal"}])
    case.refresh_from_db()
    assert case.status == "pending_decision" and not case.actions.get().issued_at
    assert _approve_all("disciplinary_decision") == 1
    case.refresh_from_db()
    assert case.status == "decided"
    sep = Separation.objects.get(employee=er["b"])
    er["b"].refresh_from_db()
    assert sep.exit_type == "dismissal" and sep.status == "clearance" and not sep.rehire_eligible
    assert er["b"].exit_date == dt.date.today() and not er["b"].rehire_eligible


def test_escalation_and_report(er):
    from apps.relations import services
    from apps.relations.models import Case

    case = services.open_case(er["u_a"], {"case_type": "grievance", "description": "Unfair roster"})
    Case.objects.filter(pk=case.pk).update(due_date=dt.date.today() - dt.timedelta(days=1))
    assert services.escalate_overdue() == 1
    assert services.escalate_overdue() == 0
    r = services.report()
    assert r["cases"] == 1 and r["overdue"] == 1 and r["by_type"][0]["label"] == "Grievance"
    services.withdraw(case, er["u_a"], "Resolved with supervisor")
    assert case.status == "withdrawn"


def test_hr_registering_a_case_is_not_the_complainant(er):
    from apps.relations import services

    case = services.open_case(er["hro"], {"case_type": "conflict", "description": "Dispute over weekend cover"})
    assert case.complainant is None and case.case_officer == er["hro"]
    # anyone raising their own concern is recorded as the complainant
    own = services.open_case(er["u_boss"], {"case_type": "grievance", "description": "My own grievance", "own": True})
    assert own.complainant == er["boss"]


def test_only_the_addressee_reads_their_letter(er):
    from apps.relations import services

    case = services.open_case(er["hro"], {"case_type": "misconduct", "description": "Late"}, respondents=[er["a"]])
    services.decide(case, er["hro"], "verbal_warning", "Lateness",
                    [{"employee": er["a"], "action_type": "verbal_warning", "details": "Lateness"}])
    action = case.actions.get()
    c = APIClient()
    c.force_authenticate(er["u_a"])
    r = c.get(f"/api/relations/my/letter/{action.id}/")
    assert r.status_code == 200 and b"".join(r.streaming_content)[:4] == b"%PDF"
    c.force_authenticate(er["u_b"])
    assert c.get(f"/api/relations/my/letter/{action.id}/").status_code == 404
    c.force_authenticate(er["u_boss"])  # the line manager cannot open the restricted document either
    assert c.get(f"/api/documents/{action.letter_id}/download/").status_code in (403, 404)
