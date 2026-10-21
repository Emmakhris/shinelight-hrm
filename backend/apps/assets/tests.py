from decimal import Decimal as D

import pytest
from rest_framework.exceptions import PermissionDenied

from apps.core.exceptions import BusinessRuleError


@pytest.fixture
def kit(org, make_employee, make_user):
    from apps.assets.models import Asset, AssetCategory

    a = make_employee(first="Ama")
    b = make_employee(first="Esi")
    laptop = Asset.objects.create(tag="IT-0001", category=AssetCategory.objects.get(code="laptop"),
                                  description="Dell Latitude 5440", serial_number="SN123", replacement_value=D("6500"))
    return {"a": a, "b": b, "laptop": laptop, "u_a": make_user("ama", ("employee",), employee=a),
            "it": make_user("it", ("it_support",))}


def test_issue_acknowledge_transfer_and_return(kit):
    from apps.assets import services

    asg = services.issue(kit["it"], kit["a"], asset=kit["laptop"])
    kit["laptop"].refresh_from_db()
    assert kit["laptop"].status == "assigned" and kit["laptop"].holder == kit["a"]
    with pytest.raises(BusinessRuleError):
        services.issue(kit["it"], kit["b"], asset=kit["laptop"])  # already out
    with pytest.raises(PermissionDenied):
        services.acknowledge(asg, kit["it"])
    services.acknowledge(asg, kit["u_a"])
    new = services.transfer(asg, kit["it"], kit["b"])
    asg.refresh_from_db()
    kit["laptop"].refresh_from_db()
    assert asg.returned_on and new.employee == kit["b"] and kit["laptop"].holder == kit["b"]
    assert services.outstanding(kit["a"]).count() == 0 and services.outstanding(kit["b"]).count() == 1


def test_uniforms_are_not_outstanding(kit):
    from apps.assets import services
    from apps.assets.models import AssetCategory

    uniform = AssetCategory.objects.get(code="uniform")
    with pytest.raises(BusinessRuleError):
        services.issue(kit["it"], kit["a"], category=AssetCategory.objects.get(code="laptop"), item="Some laptop")
    services.issue(kit["it"], kit["a"], category=uniform, item="Scrubs (blue), size M", quantity=3)
    assert services.outstanding(kit["a"]).count() == 0


def test_loss_recovered_through_payroll(kit):
    from apps.assets import services
    from apps.payroll.models import EmployeePayProfile, PayGroup, PayrollAdjustment
    from apps.payroll.services import create_period

    group = PayGroup.objects.get(code="monthly")
    EmployeePayProfile.objects.create(employee=kit["a"], pay_group=group)
    create_period(group, 2026, 12)
    asg = services.issue(kit["it"], kit["a"], asset=kit["laptop"])
    with pytest.raises(BusinessRuleError):
        services.report_incident(asg, kit["u_a"], "stolen", "x")
    services.report_incident(asg, kit["u_a"], "lost", "Left on a trotro")
    kit["laptop"].refresh_from_db()
    assert kit["laptop"].status == "lost"
    services.receive(asg, kit["it"], "lost", to_payroll=True)
    asg.refresh_from_db()
    assert asg.recovery_amount == D("6500.00") and asg.recovery_status == "payroll"
    adj = PayrollAdjustment.objects.get(employee=kit["a"], element__code="ASSET_RECOVERY")
    assert adj.amount == D("6500.00")
    assert services.recovery_dashboard()["lost_or_damaged"] == 1
