"""Multi-organization isolation. These tests run with two organizations present and check that nothing
from one is ever visible to, or written into, the other."""

import datetime as dt

import pytest
from django.urls import URLPattern
from rest_framework.test import APIClient

from apps.core.context import org_context
from apps.core.exceptions import BusinessRuleError

MARK = "zztenantb"


def bearer(user, host=None):
    """A client authenticated the way real requests are (through the authentication classes)."""
    from rest_framework_simplejwt.tokens import RefreshToken

    c = APIClient(HTTP_HOST=host) if host else APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return c


@pytest.fixture
def two_orgs(org, make_user, make_employee, settings):
    from apps.core.setup import setup_organization
    from apps.employees.models import Employee
    from apps.organization.models import Department, JobTitle
    from apps.servicedesk.models import KnowledgeArticle

    settings.ALLOWED_HOSTS = ["*"]
    settings.DEPLOYMENT_MODE = "cloud"
    make_employee(first="Ama")
    hrd = make_user("hrd_a", ("hr_director", "sys_admin"))
    beta, badmin = setup_organization("Beta Clinic", "beta", "beta_admin", "Passw0rd!xyz", "it@beta.test",
                                      features=["payroll"], require_mfa=False)
    with org_context(beta):
        dept = Department.objects.create(code="ZZB", name=f"{MARK} Department")
        title = JobTitle.objects.create(name=f"{MARK} Surgeon")
        emp = Employee.objects.create(first_name=MARK, last_name="Person", staff_number="ZZB001", department=dept,
                                      job_title=title, hire_date=dt.date(2021, 1, 1), work_email=f"{MARK}@beta.test")
        KnowledgeArticle.objects.create(title=f"{MARK} policy", body=f"{MARK} body")
    return {"a": org, "b": beta, "hrd": hrd, "badmin": badmin, "b_emp": emp}


def _list_urls():
    from config import api_urls

    urls = [f"/api/{prefix}/" for prefix, _, _ in api_urls.router.registry]
    for p in api_urls.urlpatterns:
        route = str(p.pattern) if isinstance(p, URLPattern) else ""
        if route and "<" not in route and not route.startswith(("^", "public/", "sso/", "assistant/ask")) \
                and route not in ("^$", "") and "format" not in route:
            urls.append(f"/api/{route}")
    return sorted(set(urls))


def test_no_endpoint_leaks_another_organizations_data(two_orgs):
    c = bearer(two_orgs["hrd"])          # real authentication sets the organization context, as in production
    checked, errors = 0, []
    for url in _list_urls():
        r = c.get(url)
        if r.status_code >= 500:
            errors.append(f"{url} -> {r.status_code}")
            continue
        if r.status_code == 200:
            checked += 1
            assert MARK not in r.content.decode(errors="ignore").lower(), f"{url} leaks organization B data"
    assert not errors, errors
    assert checked > 100
    # direct access to organization B's records by id is refused for every resource that has one
    from apps.core.models import TenantModel
    from config import api_urls

    probed = []
    for prefix, viewset, _ in api_urls.router.registry:
        model = getattr(getattr(viewset, "queryset", None), "model", None)
        if model is None or not issubclass(model, TenantModel):
            continue
        obj = model.all_objects.filter(organization=two_orgs["b"]).first()
        if obj is None:
            continue
        r = c.get(f"/api/{prefix}/{obj.pk}/")
        assert r.status_code in (403, 404), f"/api/{prefix}/{obj.pk}/ -> {r.status_code}"
        probed.append(prefix)
    assert len(probed) > 20, probed
    from apps.engagement.models import Survey

    with org_context(two_orgs["b"]):
        survey = Survey.objects.create(title=f"{MARK} survey")
    assert c.get(f"/api/engagement/surveys/{survey.pk}/results/").status_code == 404


def test_unique_constraints_are_scoped_to_an_organization():
    """A business field unique across all organizations would block a second tenant."""
    from django.apps import apps

    from apps.core.models import TenantModel

    allowed = {"integrations.ApiKey.prefix",       # random token, global by design
               "employees.Employee.user"}       # a login belongs to one person

    def scoped(model, name):
        f = model._meta.get_field(name)
        return name == "organization" or (f.is_relation and f.related_model is not None
                                          and issubclass(f.related_model, TenantModel))

    bad = []
    for m in apps.get_models():
        if not issubclass(m, TenantModel):
            continue
        for f in m._meta.fields:
            if f.unique and not f.primary_key and f"{m._meta.label}.{f.name}" not in allowed and not scoped(m, f.name):
                bad.append(f"{m._meta.label}.{f.name}")
        groups = list(m._meta.unique_together) + [c.fields for c in m._meta.constraints if getattr(c, "fields", None)]
        for g in groups:
            if not any(scoped(m, n) for n in g):
                bad.append(f"{m._meta.label} {g}")
    assert not bad, bad


def test_hosts_pin_sessions_and_logins_to_their_organization(two_orgs):
    c = bearer(two_orgs["hrd"], "beta.localhost")    # an organization A account on B's address
    r = c.get("/api/employees/")
    assert r.status_code == 401 and "different organization" in r.json()["detail"]
    assert bearer(two_orgs["hrd"], "test.localhost").get("/api/employees/").status_code == 200
    assert bearer(two_orgs["hrd"], "localhost").get("/api/employees/").status_code == 200
    # B's administrator cannot sign in on A's address
    r = APIClient(HTTP_HOST="test.localhost").post("/api/auth/login/", {"username": "beta_admin",
                                                                         "password": "Passw0rd!xyz"}, format="json")
    assert r.status_code == 401
    r = APIClient(HTTP_HOST="beta.localhost").post("/api/auth/login/", {"username": "beta_admin",
                                                                         "password": "Passw0rd!xyz"}, format="json")
    assert r.status_code == 200
    # the login page learns which organization it is on
    info = APIClient(HTTP_HOST="beta.localhost").get("/api/public/tenant/").json()
    assert info["organization"]["name"] == "Beta Clinic"
    assert APIClient(HTTP_HOST="localhost").get("/api/public/tenant/").json()["organization"] is None


def test_platform_operator_sees_organizations_but_no_hr_data(two_orgs):
    from django.contrib.auth import get_user_model

    User = get_user_model()
    op = User.objects.create_user("operator", "op@platform.test", "Passw0rd!xyz", organization=None,
                                  is_platform_admin=True)
    c = bearer(op)
    assert c.get("/api/employees/").status_code == 403
    assert c.get("/api/reports/dashboard/").status_code == 403
    assert c.get("/api/auth/me/").json()["is_platform_admin"] is True
    orgs = c.get("/api/platform/organizations/")
    assert orgs.status_code == 200 and {o["code"] for o in orgs.json()} == {"test", "beta"}
    assert MARK not in orgs.content.decode().lower()
    beta = next(o for o in orgs.json() if o["code"] == "beta")
    assert beta["usage"]["active_employees"] == 1
    # a user with no organization who is not an operator gets nothing at all
    stray = User.objects.create_user("stray", "", "Passw0rd!xyz", organization=None)
    c = bearer(stray)
    assert c.get("/api/platform/organizations/").status_code == 403
    assert c.get("/api/employees/").status_code == 403
    # an organization's own administrator is not a platform operator
    assert bearer(two_orgs["hrd"]).get("/api/platform/organizations/").status_code == 403


def test_operator_provisions_suspends_and_limits_plans(two_orgs, make_employee):
    from django.contrib.auth import get_user_model

    from apps.tenancy.models import Plan

    op = get_user_model().objects.create_user("operator", "", "Passw0rd!xyz", organization=None,
                                              is_platform_admin=True)
    starter = Plan.objects.create(code="starter", name="Starter", max_employees=2, features=["payroll"])
    c = bearer(op)
    r = c.post("/api/platform/organizations/", {"name": "Gamma Hospital", "code": "gamma",
                                               "admin_username": "gamma_admin", "admin_email": "it@gamma.test",
                                               "plan": starter.pk, "status": "trial"}, format="json")
    assert r.status_code == 201, r.content
    assert r.json()["plan_name"] == "Starter" and r.json()["status"] == "trial"
    for bad in ({"code": "admin"}, {"code": "gamma"}, {"code": "x"}):
        assert c.post("/api/platform/organizations/", {"name": "X", "admin_username": "u1", "admin_email": "a@b.test",
                                                       **bad}, format="json").status_code == 400
    # reusing another organization's username is refused instead of silently sharing the account
    assert c.post("/api/platform/organizations/", {"name": "Delta", "code": "delta", "admin_username": "beta_admin",
                                                   "admin_email": "a@b.test"}, format="json").status_code == 400
    # plan limits: employee cap and features outside the plan
    b = two_orgs["b"]
    assert c.patch(f"/api/platform/organizations/{b.pk}/", {"plan": starter.pk}, format="json").status_code == 200
    assert c.post(f"/api/platform/organizations/{b.pk}/feature/", {"code": "hospital", "enabled": True},
                  format="json").status_code == 400
    from apps.tenancy import services

    b.refresh_from_db()
    with org_context(b):
        from apps.employees.models import Employee

        Employee.objects.create(first_name="Kofi", last_name="B", staff_number="ZZB002", hire_date=dt.date(2022, 1, 1))
        with pytest.raises(BusinessRuleError):
            services.check_employee_limit(b)
    # suspension blocks sign-in and existing sessions
    assert c.post(f"/api/platform/organizations/{b.pk}/status/", {"status": "suspended", "reason": "Unpaid"},
                  format="json").json()["is_active"] is False
    r = APIClient().post("/api/auth/login/", {"username": "beta_admin", "password": "Passw0rd!xyz"}, format="json")
    assert r.status_code == 403 and r.json()["code"] == "org_suspended"
    assert bearer(two_orgs["badmin"]).get("/api/employees/").status_code == 401
    # the organization can see what the operator did in its own audit trail
    from apps.audit.models import AuditLog

    assert AuditLog.objects.filter(organization=b, changes__platform="status").exists()


def test_hire_respects_plan_cap(two_orgs, make_employee):
    from apps.tenancy.models import Plan

    a = two_orgs["a"]
    a.plan = Plan.objects.create(code="tiny", name="Tiny", max_employees=1, features=["payroll"])
    a.save()
    with pytest.raises(BusinessRuleError):
        make_employee(first="Second")


def test_records_never_fall_into_the_wrong_organization(two_orgs):
    from apps.leave.models import LeaveType
    from apps.organization.models import Department
    from apps.talent.models import TalentProfile

    with org_context(None):
        # a child record takes its parent's organization even with no context (Celery, shell)
        p = TalentProfile.objects.create(employee=two_orgs["b_emp"])
        assert p.organization_id == two_orgs["b"].pk
        # with several organizations and nothing to go on, saving refuses to guess
        with pytest.raises(RuntimeError):
            Department.objects.create(code="ORPHAN", name="Orphan")
    assert LeaveType.all_objects.filter(organization=two_orgs["b"]).exists()


def test_signup_and_trial_expiry(two_orgs, settings, mailoutbox):
    from apps.tenancy import services
    from apps.tenancy.models import Organization, Plan

    body = {"organization_name": "Delta Pharmacy", "code": "delta", "admin_name": "Akua Mensah",
            "email": "akua@delta.test", "username": "akua_delta", "password": "A-long-Passphrase-2026",
            "accept_terms": True}
    c = APIClient()
    assert c.post("/api/public/signup/", body, format="json").status_code == 404     # off by default
    settings.SAAS_SIGNUP_ENABLED = True
    Plan.objects.update_or_create(code="trial", defaults={"name": "Trial", "max_employees": 25,
                                                       "features": ["payroll", "sms"], "trial_days": 14})
    r = c.post("/api/public/signup/", body, format="json")
    assert r.status_code == 201, r.content
    delta = Organization.objects.get(code="delta")
    assert delta.status == "trial" and delta.trial_ends_at == dt.date.today() + dt.timedelta(days=14)
    assert delta.plan.code == "trial" and mailoutbox
    assert c.post("/api/public/signup/", {**body, "code": "www", "username": "x2"}, format="json").status_code == 400
    delta.trial_ends_at = dt.date.today() - dt.timedelta(days=1)
    delta.save()
    assert services.expire_trials()["suspended"] == 1
    delta.refresh_from_db()
    assert delta.status == "suspended" and not delta.is_active


@pytest.mark.django_db(transaction=True)
def test_row_level_security_backstop(org, settings):
    """PostgreSQL only: with the session variable set, the database itself hides other organizations' rows,
    even from the unfiltered manager."""
    from django.db import connection

    if connection.vendor != "postgresql":
        pytest.skip("Row-level security needs PostgreSQL")
    with connection.cursor() as cur:
        cur.execute("SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user")
        if cur.fetchone()[0]:
            pytest.skip("Connected as a superuser/BYPASSRLS role, which always bypasses row-level security")
    from apps.core.setup import setup_organization
    from apps.organization.models import Department
    from apps.tenancy import rls

    settings.DEPLOYMENT_MODE = "cloud"
    beta, _ = setup_organization("Beta Clinic", "beta", features=["payroll"], require_mfa=False)
    Department.all_objects.create(organization=beta, code="ZZB", name="B only")
    settings.DB_ROW_LEVEL_SECURITY = True
    rls.apply()
    try:
        with org_context(org):
            assert not Department.all_objects.filter(organization=beta).exists()
        with org_context(beta):
            assert Department.all_objects.filter(code="ZZB").exists()
        assert not Department.all_objects.filter(organization=beta).exists()   # the fixture runs as org A
        with org_context(None):                                                 # platform/Celery view
            assert Department.all_objects.filter(organization=beta).exists()
    finally:
        rls.remove()


def test_self_hosted_edition_serves_one_organization(org, settings, make_user):
    """On a customer's own server there is no operator console, sign-up or host routing, and no second
    organization can be created."""
    from django.contrib.auth import get_user_model

    from apps.core.setup import setup_organization
    from apps.tenancy import services

    settings.DEPLOYMENT_MODE = "self_hosted"
    settings.ALLOWED_HOSTS = ["*"]
    settings.SAAS_SIGNUP_ENABLED = True
    with pytest.raises(ValueError):
        setup_organization("Second", "second")
    with pytest.raises(BusinessRuleError):
        services.provision("Second", "second", "second_admin", "a@b.test")
    setup_organization("Test Org", "test")            # refreshing the existing organization still works
    c = APIClient()
    assert c.post("/api/public/signup/", {}, format="json").status_code == 404
    assert c.get("/api/public/signup/").json()["enabled"] is False
    assert c.get("/api/public/tls-check/", {"domain": "test.example.com"}).status_code == 404
    # the login page shows the organization whatever host name the server is reached by
    assert APIClient(HTTP_HOST="hr.customer.local").get("/api/public/tenant/").json()["organization"]["name"] == "Test Org"
    op = get_user_model().objects.create_user("operator", "", "Passw0rd!xyz", organization=None, is_platform_admin=True)
    assert bearer(op).get("/api/platform/organizations/").status_code == 404
    # any host name works for the organization's own users
    hrd = make_user("hrd", ("hr_director",))
    assert bearer(hrd, "anything.localhost").get("/api/employees/").status_code == 200
    assert c.get("/api/health/").json()["edition"] == "self_hosted"


def test_tls_check_only_vouches_for_known_hosts(two_orgs, settings):
    settings.SAAS_BASE_DOMAIN = "shinelighthrm.test"
    c = APIClient()
    assert c.get("/api/public/tls-check/", {"domain": "beta.shinelighthrm.test"}).status_code == 200
    assert c.get("/api/public/tls-check/", {"domain": "shinelighthrm.test"}).status_code == 200
    assert c.get("/api/public/tls-check/", {"domain": "nosuch.shinelighthrm.test"}).status_code == 404
    assert c.get("/api/public/tls-check/", {"domain": "evil.example.com"}).status_code == 404
    two_orgs["b"].domain = "hr.beta.test"
    two_orgs["b"].save()
    assert c.get("/api/public/tls-check/", {"domain": "hr.beta.test"}).status_code == 200
