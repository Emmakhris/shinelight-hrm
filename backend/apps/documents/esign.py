"""Electronic signatures.

`InternalProvider` implements a simple electronic signature (consent + typed name + authenticated
session + audit evidence) with a certificate page appended to the PDF. Its evidence is recorded in
a hash chain (document SHA-256 before signing, each signature event in the audit log), which is
appropriate for HR letters, contracts and policy sign-offs. Organizations needing advanced/qualified
signatures can implement `ESignProvider` for an external service and set `provider` on the request.
"""

import datetime as dt
import hashlib
import io

from django.core.files.base import ContentFile
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone
from pypdf import PdfReader, PdfWriter

from apps.audit import services as audit
from apps.core.exceptions import BusinessRuleError
from apps.core.pdf import BASE_CSS, html_to_pdf
from apps.notifications.services import notify

from .models import SignatureRequest, Signer
from .services import add_version


class ESignProvider:
    name = "base"

    def send(self, request: SignatureRequest):
        raise NotImplementedError

    def finalize(self, request: SignatureRequest):
        raise NotImplementedError


class InternalProvider(ESignProvider):
    name = "internal"

    def send(self, request):
        for s in _ready_signers(request):
            s.status = "pending"
            s.save(update_fields=["status", "updated_at"])
            notify("generic", [s.user], {"title": f"Please sign: {request.document.title}",
                                         "body": request.message or "A document is waiting for your signature.",
                                         "link": "/me/signatures"})

    def finalize(self, request):
        doc = request.document
        version = doc.versions.filter(version=request.source_version).first()
        original = version.file.open("rb").read()
        version.file.close()
        cert_html = render_to_string("pdf/signature_certificate.html", {
            "req": request, "doc": doc, "signers": request.signers.select_related("user"), "css": BASE_CSS,
            "now": timezone.now()})
        cert = html_to_pdf(cert_html)
        writer = PdfWriter()
        is_pdf = original[:4] == b"%PDF"
        if is_pdf:
            for page in PdfReader(io.BytesIO(original)).pages:
                writer.add_page(page)
        for page in PdfReader(io.BytesIO(cert)).pages:
            writer.add_page(page)
        writer.add_metadata({"/Subject": f"Signed via ShineLight HRM — request {request.pk}",
                             "/Keywords": f"sha256:{request.source_sha256}"})
        out = io.BytesIO()
        writer.write(out)
        name = f"{doc.title[:60]}-signed.pdf".replace("/", "-")
        f = ContentFile(out.getvalue(), name=name)
        f.content_type = "application/pdf"
        if doc.legal_hold:
            raise BusinessRuleError("Document is under legal hold.")
        new_version = add_version(doc, f, note=f"Electronically signed (request #{request.pk})")
        request.signed_version = new_version.version
        if not is_pdf:
            request.message = (request.message + "\nOriginal was not a PDF; signed version contains the certificate only.").strip()


PROVIDERS = {"internal": InternalProvider}


def provider_for(request) -> ESignProvider:
    return PROVIDERS.get(request.provider, InternalProvider)()


def _ready_signers(request):
    pending = request.signers.exclude(status__in=["signed", "declined"]).order_by("order", "id")
    if not request.sequential:
        return list(pending.filter(status="waiting"))
    first = pending.first()
    if first is None or first.status != "waiting":
        return []
    return [s for s in pending if s.order == first.order and s.status == "waiting"]


@transaction.atomic
def request_signatures(document, signers: list[dict], message="", sequential=True, due_date=None, provider="internal"):
    """signers: [{"user": User, "role_label": "Employee", "order": 1}, ...]"""
    if not signers:
        raise BusinessRuleError("Add at least one signer.")
    version = document.latest
    if version is None:
        raise BusinessRuleError("The document has no file to sign.")
    if document.signature_requests.filter(status="pending").exists():
        raise BusinessRuleError("This document already has a signature request in progress.")
    data = version.file.open("rb").read()
    version.file.close()
    req = SignatureRequest.objects.create(document=document, message=message, provider=provider, sequential=sequential,
                                          due_date=due_date, source_version=version.version,
                                          source_sha256=hashlib.sha256(data).hexdigest())
    for i, s in enumerate(signers, start=1):
        Signer.objects.create(request=req, user=s["user"], order=s.get("order") or i, role_label=s.get("role_label", ""))
    provider_for(req).send(req)
    audit.log("create", req, {"document": document.id, "signers": [str(s["user"]) for s in signers],
                              "sha256": req.source_sha256})
    return req


@transaction.atomic
def sign(signer: Signer, user, typed_name, consent, ip=None, user_agent=""):
    req = signer.request
    if signer.user_id != user.id:
        raise BusinessRuleError("This signature is assigned to someone else.")
    if req.status != "pending" or signer.status != "pending":
        raise BusinessRuleError("This document is not awaiting your signature.")
    if not consent:
        raise BusinessRuleError("You must agree to sign electronically.")
    expected = (user.get_full_name() or user.username).strip().lower()
    if typed_name.strip().lower() != expected:
        raise BusinessRuleError(f"Type your full name exactly as '{user.get_full_name() or user.username}'.")
    if req.due_date and req.due_date < dt.date.today():
        req.status = "expired"
        req.save(update_fields=["status"])
        raise BusinessRuleError("This signature request has expired.")
    # integrity: the version being signed must be unchanged
    version = req.document.versions.filter(version=req.source_version).first()
    data = version.file.open("rb").read()
    version.file.close()
    if hashlib.sha256(data).hexdigest() != req.source_sha256:
        raise BusinessRuleError("The document changed after the signature request was created. Ask HR to resend it.")
    signer.status = "signed"
    signer.typed_name = typed_name.strip()
    signer.signed_at = timezone.now()
    signer.ip_address = ip
    signer.user_agent = user_agent[:255]
    signer.save()
    audit.log("approve", req, {"signed_by": user.username, "signer_id": signer.id, "sha256": req.source_sha256})
    if not req.signers.exclude(status="signed").exists():
        provider_for(req).finalize(req)
        req.status = "completed"
        req.completed_at = timezone.now()
        req.save()
        doc = req.document
        doc.status = "approved"
        doc.save(update_fields=["status", "updated_at"])
        creator = req.created_by
        recipients = [s.user for s in req.signers.select_related("user")] + ([creator] if creator else [])
        notify("generic", recipients, {"title": f"Signed: {doc.title}",
                                       "body": "All parties have signed. The signed copy is in the document record.",
                                       "link": "/me/signatures"})
    else:
        provider_for(req).send(req)
    return req


@transaction.atomic
def decline(signer: Signer, user, reason):
    if signer.user_id != user.id:
        raise BusinessRuleError("This signature is assigned to someone else.")
    if signer.status != "pending":
        raise BusinessRuleError("Nothing to decline.")
    if not reason.strip():
        raise BusinessRuleError("Give a reason for declining.")
    signer.status = "declined"
    signer.decline_reason = reason
    signer.save()
    req = signer.request
    req.status = "declined"
    req.save(update_fields=["status", "updated_at"])
    audit.log("reject", req, {"declined_by": user.username, "reason": reason})
    if req.created_by:
        notify("generic", [req.created_by], {"title": f"Signature declined: {req.document.title}",
                                             "body": f"{user} declined: {reason}", "link": "/documents"})
    return req
