"""Regression tests for the v1.0 security review findings."""

import socket
import subprocess
import sys

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory
from rest_framework.test import APIClient


def test_production_refuses_development_secrets(tmp_path):
    """settings.py must refuse to load with DEBUG=False and the development SECRET_KEY / no encryption key."""
    code = "import django, os; os.environ['DJANGO_SETTINGS_MODULE']='config.settings'; django.setup()"
    base = {"DEBUG": "False", "PATH": "", "SYSTEMROOT": __import__("os").environ.get("SYSTEMROOT", "")}
    weak = subprocess.run([sys.executable, "-c", code], env={**base, "SECRET_KEY": "dev-insecure-change-me"},
                          capture_output=True, text=True, cwd=".")
    assert weak.returncode != 0 and "SECRET_KEY" in weak.stderr
    no_fernet = subprocess.run([sys.executable, "-c", code], env={**base, "SECRET_KEY": "x" * 50},
                               capture_output=True, text=True, cwd=".")
    assert no_fernet.returncode != 0 and "FIELD_ENCRYPTION_KEY" in no_fernet.stderr


def test_client_ip_ignores_spoofed_forwarded_for(settings):
    from apps.core.middleware import client_ip

    rf = RequestFactory()
    req = rf.get("/", HTTP_X_FORWARDED_FOR="6.6.6.6, 41.66.1.2, 172.18.0.5", REMOTE_ADDR="172.18.0.6")
    settings.TRUSTED_PROXY_COUNT = 0
    assert client_ip(req) == "172.18.0.6"                 # no proxies configured: the direct peer
    settings.TRUSTED_PROXY_COUNT = 2                      # Caddy + nginx
    assert client_ip(req) == "41.66.1.2"                  # not the attacker-supplied 6.6.6.6


def test_downloads_never_trust_the_uploaders_content_type(org, make_employee, make_user):
    from apps.documents.models import Document, DocumentCategory
    from apps.documents.services import add_version, safe_content_type

    assert safe_content_type("report.pdf") == "application/pdf"
    assert safe_content_type("sheet.xlsx").startswith("application/vnd.openxmlformats")
    emp = make_employee()
    hr = make_user("hr", ("hr_director",))
    cat = DocumentCategory.objects.first()
    from rest_framework_simplejwt.tokens import RefreshToken

    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(hr).access_token}")

    def upload(name, content):
        doc = Document.objects.create(employee=emp, category=cat, title=name)
        v = add_version(doc, SimpleUploadedFile(name, content, content_type="text/html"))   # the browser lies
        assert v.content_type != "text/html"
        return c.get(f"/api/documents/{doc.pk}/download/", {"inline": "1"})

    got = upload("payslip.pdf", b"<script>alert(1)</script>")
    assert got.status_code == 200, getattr(got, "data", got.content)
    assert got["Content-Type"] == "application/pdf"
    got = upload("data.xlsx", b"PK..")
    assert got["Content-Disposition"].startswith("attachment")   # only PDFs and images open in the browser


def test_cloud_blocks_internal_urls_but_self_hosted_allows_them(settings, monkeypatch):
    from apps.core.netsafe import UnsafeURL, check_url

    def fake_resolve(host, *a, **k):
        ips = {"metadata.internal": "169.254.169.254", "db": "172.18.0.2", "hooks.example.com": "93.184.216.34"}
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ips[host], 443))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_resolve)
    settings.DEPLOYMENT_MODE = "cloud"
    for bad in ("https://metadata.internal/latest", "https://db:5432/", "http://hooks.example.com/x"):
        with pytest.raises(UnsafeURL):
            check_url(bad)
    assert check_url("https://hooks.example.com/x")
    settings.DEPLOYMENT_MODE = "self_hosted"
    assert check_url("http://db:8080/finance-hook")          # the customer's own network is allowed


def test_sso_next_cannot_redirect_off_site(org, monkeypatch):
    import urllib.parse

    from django.core import signing

    from apps.sso import services
    from apps.sso.models import IdentityProvider

    monkeypatch.setattr(services, "discovery", lambda p: {"authorization_endpoint": "https://idp.test/auth"})
    p = IdentityProvider.objects.create(name="IdP", issuer="https://idp.test", client_id="c", email_domains="x.test")
    for nxt, expected in (("/leave", "/leave"), ("//evil.com", "/"), ("/\\evil.com", "/"), ("https://evil.com", "/"),
                          ("/%5Cevil.com", "/%5Cevil.com")):
        _, cookie = services.start(p, nxt)
        assert signing.loads(cookie, salt=services.STATE_SALT)["next"] == expected, nxt
    assert urllib.parse.urlsplit("/%5Cevil.com").netloc == ""


def test_organization_wide_hr_sees_employee_documents(org, make_employee, make_user):
    """Regression: `Q() | Q(employee__isnull=True)` collapsed to the right-hand side, hiding every employee
    document from organization-wide HR users."""
    from rest_framework_simplejwt.tokens import RefreshToken

    from apps.documents.models import Document, DocumentCategory

    emp = make_employee()
    doc = Document.objects.create(employee=emp, category=DocumentCategory.objects.first(), title="Contract")
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(make_user('hr', ('hr_director',))).access_token}")
    ids = [d["id"] for d in c.get("/api/documents/").json()["results"]]
    assert doc.pk in ids
