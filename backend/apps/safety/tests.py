import datetime as dt

import pytest
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APIClient

from apps.core.exceptions import BusinessRuleError


@pytest.fixture
def site(org, make_employee, make_user):
    nurse = make_employee(first="Ama")
    return {"nurse": nurse, "u_nurse": make_user("ama", ("employee",), employee=nurse),
            "safety": make_user("safety", ("safety_officer",)), "oh": make_user("oh", ("oh_professional",)),
            "hrd": make_user("hrd", ("hr_director",)), "hro": make_user("hro", ("hr_officer",))}


def _report(site, **kw):
    from apps.safety import services

    data = {"kind": "exposure", "severity": "minor", "occurred_at": timezone.now() - dt.timedelta(hours=2),
            "location": "Ward A, treatment room", "description": "Needlestick while recapping a needle.",
            "immediate_action": "Washed site, reported to in-charge"}
    data.update(kw)
    return services.report(site["u_nurse"], data, [site["nurse"]])


def test_incident_lifecycle(site):
    from apps.safety import services

    inc = _report(site)
    assert inc.reference.startswith("INC-") and inc.status == "reported"
    with pytest.raises(PermissionDenied):
        services.investigate(inc, site["u_nurse"], root_cause="x")
    services.investigate(inc, site["safety"], root_cause="Recapping against policy; no sharps bin at bedside",
                         lost_time_days=0)
    a = services.add_action(site["safety"], "Place sharps bins at every bedside", site["safety"],
                            dt.date.today() + dt.timedelta(days=7), incident=inc)
    with pytest.raises(BusinessRuleError):
        services.close_incident(inc, site["safety"])  # action still open
    services.complete_action(a, site["safety"], "Installed on Ward A")
    services.close_incident(inc, site["safety"])
    assert inc.status == "closed"
    serious = _report(site, kind="injury", severity="serious", description="Fell on wet floor")
    assert serious.reportable
    services.investigate(serious, site["safety"], root_cause="Wet floor, no sign", lost_time_days=5)
    with pytest.raises(BusinessRuleError):
        services.close_incident(serious, site["safety"])  # authority notification not recorded
    st = services.stats()
    assert st["incidents"] == 2 and st["lost_time_injuries"] == 1 and st["exposures"] == 1 and st["ltifr"] > 0


def test_reporter_sees_own_incident_only(site, make_user, make_employee):
    _report(site)
    other = make_user("bob", ("employee",), employee=make_employee(first="Bob"))
    c = APIClient()
    c.force_authenticate(other)
    assert c.get("/api/safety/incidents/").json()["count"] == 0
    c.force_authenticate(site["u_nurse"])
    assert c.get("/api/safety/incidents/").json()["count"] == 1
    c.force_authenticate(site["safety"])
    assert c.get("/api/safety/incidents/").json()["count"] == 1


def test_occupational_health_is_separated_and_blocks_rostering(site):
    from apps.hospital.services import credential_issues
    from apps.safety import services

    for u in ("hrd", "hro", "safety"):
        with pytest.raises(PermissionDenied):
            services.add_oh_record(site[u], site["nurse"], {"kind": "fitness", "date": dt.date.today()})
    services.add_oh_record(site["oh"], site["nurse"], {
        "kind": "injury_care", "date": dt.date.today(), "clinical_notes": "Back strain; analgesia; physio referral",
        "fitness": "unfit", "valid_until": dt.date.today() + dt.timedelta(days=5)})
    st = services.fitness_status(site["nurse"])
    assert st["status"] == "unfit" and "clinical_notes" not in st
    assert any("Not fit for duty" in i for i in credential_issues(site["nurse"]))
    c = APIClient()
    c.force_authenticate(site["hrd"])  # even the HR Director cannot read clinical notes
    assert c.get("/api/safety/oh-records/").status_code == 403
    board = c.get("/api/safety/fitness/").json()
    assert board[0]["name"] == site["nurse"].full_name and "clinical_notes" not in board[0]
    c.force_authenticate(site["oh"])
    assert c.get("/api/safety/oh-records/").json()["results"][0]["clinical_notes"].startswith("Back strain")
    # once the unfit period ends, rostering is no longer blocked
    assert not any("Not fit" in i for i in credential_issues(site["nurse"], dt.date.today() + dt.timedelta(days=6)))
