import datetime as dt
import mimetypes
import os

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction

from apps.audit import services as audit
from apps.core.context import get_current_org
from apps.core.exceptions import BusinessRuleError
from apps.core.pdf import letter_pdf
from apps.rbac.services import can_access_employee, has_perm

from .models import Document, DocumentCategory, DocumentVersion, LetterTemplate


def validate_upload(f):
    ext = os.path.splitext(f.name)[1].lower()
    if ext not in settings.ALLOWED_UPLOAD_EXTENSIONS:
        raise BusinessRuleError(f"File type {ext} is not allowed.")
    if f.size > 15 * 1024 * 1024:
        raise BusinessRuleError("Files must be 15 MB or smaller.")


@transaction.atomic
def add_version(document: Document, file, note="") -> DocumentVersion:
    validate_upload(file)
    if document.legal_hold:
        raise BusinessRuleError("Document is under legal hold and cannot be changed.")
    document.current_version += 1
    document.save(update_fields=["current_version", "updated_at"])
    version = DocumentVersion(document=document, version=document.current_version, file_name=file.name,
                              content_type=getattr(file, "content_type", "") or mimetypes.guess_type(file.name)[0] or "",
                              note=note)
    version.file.save(file.name, file, save=False)
    version.save()
    return version


def can_view_document(user, doc: Document) -> bool:
    if doc.confidentiality in ("confidential", "restricted"):
        own = doc.employee_id and getattr(user, "employee", None) and user.employee.id == doc.employee_id
        if doc.confidentiality == "restricted" and not has_perm(user, "documents.view_confidential"):
            return False
        if doc.confidentiality == "confidential" and not (own and doc.visible_to_employee) and \
                not has_perm(user, "documents.view", min_scope="department") and \
                not has_perm(user, "documents.view_confidential"):
            return False
    if doc.employee_id is None:
        return has_perm(user, "documents.view") or doc.is_policy
    if getattr(user, "employee", None) and user.employee.id == doc.employee_id:
        return doc.visible_to_employee
    return can_access_employee(user, "documents.view", doc.employee)


def compute_retention(doc: Document):
    emp = doc.employee
    if emp is None or emp.exit_date is None:
        return None
    years = doc.category.retention_years
    try:
        return emp.exit_date.replace(year=emp.exit_date.year + years)
    except ValueError:
        return emp.exit_date + dt.timedelta(days=365 * years)


def letter_context(employee, extra=None):
    org = get_current_org() or employee.organization
    ctx = {
        "employee": employee,
        "organization": org,
        "today": dt.date.today(),
        "department": employee.department,
        "job_title": employee.job_title,
        "grade": employee.grade,
        "supervisor": employee.supervisor,
        "salary": employee.basic_salary,
    }
    ctx.update(extra or {})
    return ctx


@transaction.atomic
def generate_letter(template: LetterTemplate, employee, extra=None, reference="") -> Document:
    ctx = letter_context(employee, {**(extra or {}), "reference": reference})
    pdf = letter_pdf(template.body_html, ctx)
    category = template.output_category or DocumentCategory.objects.get_or_create(
        code="letters", defaults={"name": "HR letters", "default_confidentiality": "confidential"})[0]
    doc = Document.objects.create(employee=employee, category=category, title=f"{template.name}",
                                  reference_no=reference, confidentiality=category.default_confidentiality,
                                  issue_date=dt.date.today(), visible_to_employee=True)
    name = f"{template.code}-{employee.staff_number}-{dt.date.today():%Y%m%d}.pdf"
    f = ContentFile(pdf, name=name)
    f.content_type = "application/pdf"
    add_version(doc, f, note="Generated from template")
    audit.log("create", doc, {"generated_from": template.code})
    return doc
