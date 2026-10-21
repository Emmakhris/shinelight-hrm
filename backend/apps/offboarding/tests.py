import datetime as dt

import pytest
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APIClient

from apps.core.exceptions import BusinessRuleError


@pytest.fixture
def leaver(org, make_employee, make_user):
    boss = make_employee(first="Kojo")
    a = make_employee(first="Ama", supervisor=boss)
    return {"boss": boss, "a": a, "u_boss": make_user("boss", ("line_manager",), employee=boss),
            "u_a": make_user("ama", ("employee",), employee=a), "hro": make_user("hro", ("hr_officer",)),
            "hrd": make_user("hrd", ("hr_director",)), "it": make_user("it", ("it_support",)),
            "adm": make_user("adm", ("admin_officer",)), "fin": make_user("fin", ("finance_officer",)),
            "pay": make_user("pay", ("payroll_officer",))}


def _approve_all(rtype):
    from apps.workflow import engine
    from apps.workflow.models import WorkflowTask

    n = 0
    while (t := WorkflowTask.objects.filter(status="pending", instance__request_type=rtype).first()) is not None:
        engine.act(t, t.assignee, "approve", "OK")
        n += 1
    return n


def _resign(leaver, days=20):
    from apps.offboarding import services

    today = dt.date.today()
    return services.initiate(leaver["u_a"], leaver["a"], {
        "exit_type": "resignation", "reason": "career", "details": "Moving to a teaching hospital",
        "notice_date": today, "last_working_day": today + dt.timedelta(days=days)})


def test_resignation_notice_approval_and_clearance_items(leaver):
    from apps.offboarding import services

    with pytest.raises(PermissionDenied):
        services.initiate(leaver["u_a"], leaver["a"], {"exit_type": "termination", "last_working_day": dt.date.today()})
    sep = _resign(leaver)
    assert sep.notice_required_days == 30 and sep.notice_shortfall_days == 10  # 6 years' service: one month
    with pytest.raises(BusinessRuleError):
        _resign(leaver)  # one open exit at a time
    assert _approve_all("separation") == 2  # supervisor acknowledgment + HR
    sep.refresh_from_db()
    leaver["a"].refresh_from_db()
    assert sep.status == "clearance" and sep.clearance.count() == 7
    assert leaver["a"].exit_date == sep.last_working_day and leaver["a"].user.is_active  # until the last day


def test_clearance_checks_and_completion(leaver):
    from apps.assets import services as assets
    from apps.assets.models import Asset, AssetCategory
    from apps.documents.models import Document
    from apps.offboarding import services

    laptop = Asset.objects.create(tag="IT-9", category=AssetCategory.objects.get(code="laptop"), description="HP")
    asg = assets.issue(leaver["it"], leaver["a"], asset=laptop)
    sep = _resign(leaver)
    _approve_all("separation")
    items = {i.auto_check or i.title: i for i in sep.clearance.all()}
    it_item = items["assets_it"]
    with pytest.raises(PermissionDenied):
        services.clear(it_item, leaver["fin"])  # finance cannot clear IT's item
    with pytest.raises(BusinessRuleError):
        services.clear(it_item, leaver["it"])  # laptop still out
    assets.receive(asg, leaver["it"], "good")
    services.clear(it_item, leaver["it"], "Laptop returned, accounts closed")
    services.clear(items["assets_admin"], leaver["adm"])
    services.clear(items["loans"], leaver["fin"])
    with pytest.raises(BusinessRuleError):
        services.clear(items["exit_interview"], leaver["hro"])
    c = APIClient()
    c.force_authenticate(leaver["u_a"])
    r = c.post(f"/api/offboarding/separations/{sep.id}/interview/", {
        "ratings": {"Pay and benefits": 2, "Career growth and training": 3}, "primary_reason": "career",
        "would_recommend": True, "what_to_improve": "Clearer promotion path"}, format="json")
    assert r.status_code == 200, r.content
    services.clear(items["exit_interview"], leaver["hro"])
    with pytest.raises(BusinessRuleError):
        services.clear(items["final_pay"], leaver["pay"])  # no final run yet
    with pytest.raises(BusinessRuleError):
        services.clear(items["final_pay"], leaver["pay"], "x", waive=True)  # only HR waives
    services.clear(items["final_pay"], leaver["hro"], "Paid in the October final run (manual)", waive=True)
    for i in sep.clearance.filter(status="pending"):
        services.clear(i, leaver["hrd"], "Done")
    sep.refresh_from_db()
    assert sep.status == "completed" and sep.certificate_id
    assert Document.objects.get(pk=sep.certificate_id).title == "Certificate of service"
    a = services.analytics()
    assert a["exits"] == 0  # last working day still in the future
    assert a["in_clearance"] == 0


def test_access_extension_and_revocation(leaver):
    from apps.offboarding import services
    from apps.offboarding.models import Separation

    today = dt.date.today()
    sep = services.initiate(leaver["hro"], leaver["a"], {"exit_type": "mutual", "details": "Agreed exit",
                                                         "notice_date": today - dt.timedelta(days=5),
                                                         "last_working_day": today - dt.timedelta(days=1)})
    services.extend_access(sep, leaver["hrd"], today + dt.timedelta(days=5), "Handover of patient records system")
    _approve_all("separation")
    leaver["a"].refresh_from_db()
    leaver["a"].user.refresh_from_db()
    assert leaver["a"].status == "exited" and leaver["a"].user.is_active  # kept active for the handover
    Separation.objects.filter(pk=sep.pk).update(access_extension_until=today - dt.timedelta(days=1))
    assert services.housekeeping() == 1
    leaver["a"].user.refresh_from_db()
    assert not leaver["a"].user.is_active
    assert services.analytics()["exits"] == 1


def test_involuntary_exit_routing_and_withdrawal(leaver):
    from apps.offboarding import services

    today = dt.date.today()
    with pytest.raises(BusinessRuleError):
        services.initiate(leaver["hro"], leaver["a"], {"exit_type": "termination",
                                                       "last_working_day": today + dt.timedelta(days=30)})
    sep = services.initiate(leaver["hro"], leaver["a"], {"exit_type": "redundancy", "details": "Unit closed",
                                                         "last_working_day": today + dt.timedelta(days=30)})
    assert _approve_all("separation") == 1  # HR Director only: the HR officer who recorded it cannot approve it
    sep.refresh_from_db()
    services.withdraw(sep, leaver["hrd"], "Redeployed instead")
    leaver["a"].refresh_from_db()
    assert sep.status == "withdrawn" and leaver["a"].exit_date is None and not sep.clearance.exists()
