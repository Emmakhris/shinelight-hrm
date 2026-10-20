import datetime as dt

from apps.core.exceptions import BusinessRuleError

from .models import CompetencyRecord, CompetencyRequirement, ProfessionalLicense


def credential_issues(employee, on_date=None) -> list[str]:
    """Return reasons an employee may not perform regulated clinical duties on a date."""
    on_date = on_date or dt.date.today()
    issues = []
    jt = employee.job_title
    if jt is None or not jt.is_clinical:
        return issues
    licenses = ProfessionalLicense.objects.filter(employee=employee)
    if jt.required_license_type:
        licenses = licenses.filter(license_type__iexact=jt.required_license_type)
    if not any(lic.is_valid_on(on_date) for lic in licenses):
        issues.append(f"No active, verified {jt.required_license_type or 'professional'} licence on "
                      f"{on_date:%d/%m/%Y}.")
    for req in CompetencyRequirement.objects.filter(job_titles=jt, blocks_rostering=True):
        rec = CompetencyRecord.objects.filter(employee=employee, requirement=req).order_by("-completed_on").first()
        if rec is None or (rec.expires_on and rec.expires_on < on_date):
            issues.append(f"Mandatory competency '{req.name}' is missing or expired.")
    return issues


def assert_credentials_valid(employee, on_date):
    issues = credential_issues(employee, on_date)
    if issues:
        raise BusinessRuleError(f"{employee.full_name} cannot be rostered: " + " ".join(issues),
                                code="credential_invalid")


def expire_licenses(today=None):
    today = today or dt.date.today()
    return ProfessionalLicense.objects.filter(status="active", expiry_date__lt=today).update(status="expired")


def send_license_reminders(target_dates, hr_users):
    from apps.notifications.services import notify

    expire_licenses()
    for lic in ProfessionalLicense.objects.filter(expiry_date__in=target_dates, status="active").select_related(
            "employee__user"):
        recipients = list(hr_users)
        if lic.employee.user_id:
            recipients.append(lic.employee.user)
        notify("expiry.license", recipients, {"license": lic.license_type, "employee": lic.employee.full_name,
                                              "date": lic.expiry_date}, related=lic)


def competency_matrix(department=None):
    from apps.employees.models import ACTIVE_STATUSES, Employee

    employees = Employee.objects.filter(status__in=ACTIVE_STATUSES, job_title__is_clinical=True)
    if department is not None:
        employees = employees.filter(department=department)
    today = dt.date.today()
    rows = []
    for emp in employees.select_related("job_title", "department"):
        reqs = CompetencyRequirement.objects.filter(job_titles=emp.job_title)
        items = {}
        for req in reqs:
            rec = CompetencyRecord.objects.filter(employee=emp, requirement=req).order_by("-completed_on").first()
            if rec is None:
                items[req.name] = "missing"
            elif rec.expires_on and rec.expires_on < today:
                items[req.name] = "expired"
            elif rec.expires_on and (rec.expires_on - today).days <= 60:
                items[req.name] = "expiring"
            else:
                items[req.name] = "current"
        rows.append({"employee": emp.id, "name": emp.full_name, "job_title": emp.job_title.name,
                     "department": emp.department.name if emp.department_id else "",
                     "credential_issues": credential_issues(emp, today), "competencies": items})
    return rows
