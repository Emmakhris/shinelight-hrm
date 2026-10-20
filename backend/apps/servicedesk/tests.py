from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.exceptions import BusinessRuleError


@pytest.fixture
def desk(org, make_employee, make_user):
    from apps.servicedesk.models import ServiceType

    emp = make_employee(first="Ama")
    requester = make_user("req", ("employee",), employee=emp)
    agent1 = make_user("agent1", ("hr_officer",))
    agent2 = make_user("agent2", ("hr_officer",))
    svc = ServiceType.objects.get(name="Employment confirmation letter")
    return {"emp": emp, "requester": requester, "agent1": agent1, "agent2": agent2, "svc": svc}


def test_ticket_routing_and_reference(desk):
    from apps.servicedesk import services

    t1 = services.create_ticket(desk["svc"], desk["requester"], "Letter for bank", "Need it",
                                form_data={"addressed_to": "GCB"})
    t2 = services.create_ticket(desk["svc"], desk["requester"], "Another", "x", form_data={"addressed_to": "Ecobank"})
    assert t1.reference.startswith("HR-") and t1.reference != t2.reference
    assert {t1.assignee, t2.assignee} == {desk["agent1"], desk["agent2"]}  # least-loaded round robin
    assert t1.status == "open"


def test_required_form_fields(desk):
    from apps.servicedesk import services

    with pytest.raises(BusinessRuleError):
        services.create_ticket(desk["svc"], desk["requester"], "Letter", "x", form_data={})


def test_lifecycle_sla_pause_rate(desk):
    from apps.servicedesk import services

    t = services.create_ticket(desk["svc"], desk["requester"], "Letter", "x", form_data={"addressed_to": "GCB"})
    agent = t.assignee
    due_before = t.resolution_due
    services.set_status(t, "pending_employee", agent, "Please confirm the branch")
    t.paused_since = timezone.now() - timedelta(hours=5)
    t.save()
    services.add_comment(t, desk["requester"], "Ridge branch")  # employee reply resumes the clock
    t.refresh_from_db()
    assert t.status == "open"
    assert t.resolution_due >= due_before + timedelta(hours=4, minutes=59)
    assert t.first_response_at is not None
    with pytest.raises(BusinessRuleError):
        services.add_comment(t, desk["requester"], "secret", internal=True)
    services.resolve(t, agent, "Letter issued")
    with pytest.raises(BusinessRuleError):
        services.rate(t, agent, 5)
    services.rate(t, desk["requester"], 4, "Quick")
    t.refresh_from_db()
    assert t.status == "closed" and t.rating == 4 and not t.resolution_breached


def test_breach_escalation_and_metrics(desk):
    from apps.servicedesk import services
    from apps.servicedesk.models import Ticket

    t = services.create_ticket(desk["svc"], desk["requester"], "Letter", "x", form_data={"addressed_to": "GCB"})
    warned, escalated, closed = services.process_sla(now=t.resolution_due + timedelta(minutes=1))
    t.refresh_from_db()
    assert escalated == 1 and t.resolution_breached and t.escalated_at
    services.resolve(t, t.assignee, "Done late")
    m = services.metrics(Ticket.objects.all())
    assert m["resolved"] == 1 and m["sla_compliance_percent"] == 0.0


def test_confidential_ticket_visibility(desk, make_user):
    from apps.servicedesk import services
    from apps.servicedesk.models import ServiceType

    grievance = ServiceType.objects.get(name="Raise a grievance")
    t = services.create_ticket(grievance, desk["requester"], "Issue with supervisor", "details")
    other = desk["agent2"] if t.assignee == desk["agent1"] else desk["agent1"]
    c = APIClient()
    c.force_authenticate(other)
    ids = [x["id"] for x in c.get("/api/helpdesk/tickets/").json()["results"]]
    assert t.id not in ids
    c.force_authenticate(t.assignee)
    assert t.id in [x["id"] for x in c.get("/api/helpdesk/tickets/").json()["results"]]
    c.force_authenticate(desk["requester"])
    detail = c.get(f"/api/helpdesk/tickets/{t.id}/").json()
    assert detail["reference"] == t.reference


def test_internal_notes_hidden_from_requester(desk):
    from apps.servicedesk import services

    t = services.create_ticket(desk["svc"], desk["requester"], "Letter", "x", form_data={"addressed_to": "GCB"})
    services.add_comment(t, t.assignee, "check salary first", internal=True)
    services.add_comment(t, t.assignee, "Working on it")
    c = APIClient()
    c.force_authenticate(desk["requester"])
    bodies = [x["body"] for x in c.get(f"/api/helpdesk/tickets/{t.id}/").json()["comments"]]
    assert "Working on it" in bodies and "check salary first" not in bodies
