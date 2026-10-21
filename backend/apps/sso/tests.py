import time
import urllib.parse
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from rest_framework.test import APIClient

ISSUER = "https://login.example-idp.test/tenant/v2.0"
DOC = {"issuer": ISSUER, "authorization_endpoint": f"{ISSUER}/authorize", "token_endpoint": f"{ISSUER}/token",
       "jwks_uri": f"{ISSUER}/keys"}


@pytest.fixture
def idp(org, monkeypatch, settings):
    from apps.sso import services
    from apps.sso.models import IdentityProvider

    settings.FRONTEND_URL = "http://hr.test"
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key(), as_dict=True)
    jwk.update({"kid": "k1", "use": "sig", "alg": "RS256"})
    monkeypatch.setattr(services, "discovery", lambda p: DOC)
    monkeypatch.setattr(services, "jwks", lambda p, uri: {"keys": [jwk]})
    provider = IdentityProvider.objects.create(name="Microsoft 365", issuer=ISSUER, client_id="client-123",
                                               client_secret="s3cret", email_domains="hospital.test")
    issued = {}

    def token(**claims):
        now = int(time.time())
        body = {"iss": ISSUER, "aud": "client-123", "iat": now, "exp": now + 300, "sub": "sub-1",
                "email": "ama@hospital.test", "nonce": issued.get("nonce", ""), **claims}
        return jwt.encode(body, key, algorithm="RS256", headers={"kid": "k1"})

    def fake_post(url, data=None, timeout=None):
        assert url == DOC["token_endpoint"] and data["code_verifier"] and data["client_secret"] == "s3cret"
        tok = issued.pop("next_token", None) or token()
        return SimpleNamespace(status_code=200, json=lambda: {"id_token": tok})

    monkeypatch.setattr(services.requests, "post", fake_post)
    return {"provider": provider, "token": token, "issued": issued}


def _sign_in(client, idp, **claims):
    r = client.get(f"/api/sso/{idp['provider'].pk}/start/", {"next": "/leave"})
    assert r.status_code == 302 and r["Location"].startswith(DOC["authorization_endpoint"])
    q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(r["Location"]).query))
    assert q["code_challenge_method"] == "S256" and q["redirect_uri"].endswith("/api/sso/callback/")
    idp["issued"]["nonce"] = q["nonce"]
    if claims:
        idp["issued"]["next_token"] = idp["token"](**claims)
    return client.get("/api/sso/callback/", {"code": "abc", "state": q["state"]})


def test_sso_sign_in_links_existing_user_and_sets_session(idp, make_employee, make_user, settings):
    from apps.accounts.models import LoginAttempt
    from apps.sso.models import ExternalIdentity

    emp = make_employee(first="Ama", work_email="ama@hospital.test")
    user = make_user("ama", ("employee",), employee=emp)
    c = APIClient()
    r = _sign_in(c, idp)
    assert r.status_code == 302 and r["Location"] == "http://hr.test/leave"
    assert settings.AUTH_COOKIE_ACCESS in r.cookies
    assert ExternalIdentity.objects.get(subject="sub-1").user == user
    assert LoginAttempt.objects.filter(user=user, success=True, reason="sso").exists()
    me = c.get("/api/auth/me/")
    assert me.status_code == 200 and me.json()["username"] == "ama"
    # next time the stable subject is used even if the email changed at the IdP
    r = _sign_in(APIClient(), idp, email="ama.new@hospital.test")
    assert r["Location"] == "http://hr.test/leave"


def test_sso_rejects_tampering_and_unknown_people(idp, make_employee):
    c = APIClient()
    # forged state (no cookie from this browser)
    r = c.get("/api/sso/callback/", {"code": "abc", "state": "forged"})
    assert "sso_error=expired" in r["Location"]
    # wrong nonce in the ID token
    r = _sign_in(APIClient(), idp, nonce="other")
    assert "sso_error=bad_token" in r["Location"]
    # wrong audience
    r = _sign_in(APIClient(), idp, aud="someone-else")
    assert "sso_error=bad_token" in r["Location"]
    # outside the configured domain
    r = _sign_in(APIClient(), idp, sub="x2", email="kofi@gmail.com")
    assert "sso_error=domain_not_allowed" in r["Location"]
    # employee exists but has no login and auto-creation is off
    make_employee(first="Esi", work_email="esi@hospital.test")
    r = _sign_in(APIClient(), idp, sub="x3", email="esi@hospital.test")
    assert "sso_error=no_account" in r["Location"]
    # with auto-creation a login (not an employee) is created with the employee role only
    idp["provider"].auto_create_accounts = True
    idp["provider"].save()
    r = _sign_in(APIClient(), idp, sub="x3", email="esi@hospital.test")
    assert r["Location"] == "http://hr.test/leave"
    from apps.employees.models import Employee

    esi = Employee.objects.get(work_email="esi@hospital.test")
    assert esi.user and not esi.user.has_usable_password()
    assert list(esi.user.role_assignments.values_list("role__code", flat=True)) == ["employee"]


def test_discovery_password_enforcement_and_admin(idp, make_employee, make_user):
    from apps.sso.models import IdentityProvider

    c = APIClient()
    assert c.post("/api/sso/discover/", {"email": "x@hospital.test"}, format="json").json()["start_url"] \
        == f"/api/sso/{idp['provider'].pk}/start/"
    assert c.post("/api/sso/discover/", {"email": "x@other.test"}, format="json").status_code == 404
    emp = make_employee(first="Ama", work_email="ama@hospital.test")
    user = make_user("ama", ("employee",), employee=emp)
    user.email = "ama@hospital.test"
    user.save()
    admin = make_user("sysadmin", ("sys_admin",))
    admin.email = "it@hospital.test"
    admin.save()
    login = {"username": "ama", "password": "Passw0rd!xyz"}
    assert c.post("/api/auth/login/", login, format="json").status_code == 200
    idp["provider"].allow_password_login = False
    idp["provider"].save()
    r = c.post("/api/auth/login/", login, format="json")
    assert r.status_code == 403 and r.json()["code"] == "sso_required"
    # break-glass: an organization administrator can still use a password
    assert c.post("/api/auth/login/", {"username": "sysadmin", "password": "Passw0rd!xyz"},
                  format="json").status_code == 200
    # admin API: secret is write-only, domains are unique across organizations
    c.force_authenticate(admin)
    rows = c.get("/api/admin/sso-providers/").json()
    assert rows[0]["has_secret"] is True and "client_secret" not in rows[0]
    assert rows[0]["redirect_uri"].endswith("/api/sso/callback/")
    dup = c.post("/api/admin/sso-providers/", {"name": "Google", "issuer": "https://accounts.google.com",
                                               "client_id": "g", "email_domains": "HOSPITAL.test"}, format="json")
    assert dup.status_code == 400
    c.patch(f"/api/admin/sso-providers/{idp['provider'].pk}/", {"name": "Entra ID", "client_secret": ""},
            format="json")
    assert IdentityProvider.objects.get().client_secret == "s3cret"   # blank keeps the stored secret
    c.force_authenticate(user)
    assert c.get("/api/admin/sso-providers/").status_code == 403
