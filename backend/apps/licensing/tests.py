import base64
import datetime as dt

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.core.exceptions import BusinessRuleError


@pytest.fixture
def vendor(org, settings, monkeypatch):
    """Self-hosted edition with a throwaway signing key trusted for the test."""
    from apps.licensing import keys

    settings.DEPLOYMENT_MODE = "self_hosted"
    key = Ed25519PrivateKey.generate()
    raw = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    monkeypatch.setattr(keys, "TRUSTED_PUBLIC_KEYS", [base64.urlsafe_b64encode(raw).decode().rstrip("=")])
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption())
    cache.delete("licence:state")

    def issue(expires_in=365, employees=3, features=("payroll", "sms"), organization="test", signing_key=pem):
        from apps.licensing.services import sign

        return sign({"licence_id": "L-1", "customer": "Test Hospital", "organization": organization,
                     "max_employees": employees, "features": list(features), "issued": str(dt.date.today()),
                     "expires": str(dt.date.today() + dt.timedelta(days=expires_in)), "grace_days": 30,
                     "edition": "self_hosted"}, signing_key)

    yield issue
    cache.delete("licence:state")


def test_evaluation_then_licensed_limits(vendor, make_employee, make_user):
    from apps.licensing import services

    assert services.state(refresh=True)["state"] == "evaluation"
    assert services.employee_cap() == services.EVALUATION_EMPLOYEES
    services.install(vendor(employees=2))
    s = services.state()
    assert s["state"] == "active" and s["max_employees"] == 2 and s["customer"] == "Test Hospital"
    make_employee(first="One")
    make_employee(first="Two")
    with pytest.raises(BusinessRuleError) as exc:
        make_employee(first="Three")
    assert exc.value.code == "licence_limit"
    # modules outside the licence can't be switched on
    from rest_framework_simplejwt.tokens import RefreshToken

    admin = make_user("sysadmin", ("sys_admin",))
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(admin).access_token}")
    r = c.post("/api/organization/features/", {"code": "hospital", "enabled": True}, format="json")
    assert r.status_code == 400 and r.json()["code"] == "licence_feature"
    assert c.post("/api/organization/features/", {"code": "sms", "enabled": True}, format="json").status_code == 200


def test_tampered_foreign_or_misdirected_licences_are_rejected(vendor):
    from apps.licensing import services

    good = vendor()
    body = good.split("\n")[1]
    payload, sig = body.split(".")
    raw = base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)).replace(b'"max_employees":3', b'"max_employees":9999')
    forged = f"{services.HEADER}\n{base64.urlsafe_b64encode(raw).decode().rstrip('=')}.{sig}\n{services.FOOTER}"
    with pytest.raises(BusinessRuleError) as exc:
        services.install(forged)
    assert exc.value.code == "licence_invalid"
    other_key = Ed25519PrivateKey.generate().private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                                           serialization.NoEncryption())
    with pytest.raises(BusinessRuleError):
        services.install(vendor(signing_key=other_key))            # signed by someone else
    with pytest.raises(BusinessRuleError) as exc:
        services.install(vendor(organization="another-hospital"))  # issued to a different organization
    assert exc.value.code == "licence_wrong_org"
    with pytest.raises(BusinessRuleError):
        services.install("not a licence")
    assert services.state(refresh=True)["state"] == "evaluation"    # nothing was installed


def test_expiry_grace_then_read_only_but_data_stays_readable(vendor, make_user, mailoutbox):
    from apps.licensing import services

    admin = make_user("sysadmin", ("sys_admin", "hr_director"))
    admin.email = "it@test.local"
    admin.save()
    services.install(vendor(expires_in=30))
    assert services.state(refresh=True)["state"] == "expiring"
    assert services.reminders(today=dt.date.today()) == 1 and mailoutbox      # 30 days before
    expiry = dt.date.today() + dt.timedelta(days=30)
    assert services.state(today=expiry + dt.timedelta(days=5))["state"] == "grace"
    late = services.state(today=expiry + dt.timedelta(days=31))
    assert late["state"] == "expired" and late["read_only"]

    # make the expired state the live one: re-issue a licence that ended 31 days ago
    services.install(vendor(expires_in=-31))
    c = APIClient()
    c.force_authenticate(admin)
    assert c.get("/api/employees/").status_code == 200                       # reading still works
    r = c.post("/api/org/departments/", {"code": "NEW", "name": "New"}, format="json")
    assert r.status_code == 402 and r.json()["code"] == "licence_expired"   # changes are refused
    banner = c.get("/api/licence/status/").json()
    assert banner["state"] == "expired" and banner["read_only"] is True
    # installing a renewal is always possible and lifts read-only immediately
    r = c.post("/api/licence/", {"licence": vendor(expires_in=365)}, format="json")
    assert r.status_code == 200 and r.json()["state"] == "active"
    assert c.post("/api/org/departments/", {"code": "NEW", "name": "New"}, format="json").status_code == 201


def test_cloud_edition_ignores_licences(org, settings):
    from apps.licensing import services

    settings.DEPLOYMENT_MODE = "cloud"
    cache.delete("licence:state")
    assert services.state(refresh=True) == {"state": "not_applicable", "read_only": False}
    assert services.employee_cap() is None and services.feature_allowed("hospital")


def test_only_administrators_see_licence_details(vendor, make_user):
    from apps.licensing import services

    services.install(vendor())
    c = APIClient()
    c.force_authenticate(make_user("emp", ("employee",)))
    assert c.get("/api/licence/").status_code == 403
    assert c.post("/api/licence/", {"licence": vendor()}, format="json").status_code == 403
    assert set(c.get("/api/licence/status/").json()) == {"state", "read_only", "message", "days_left"}
