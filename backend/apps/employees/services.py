"""Employee lifecycle services. All employment changes go through `apply_change` so history is
effective-dated and never overwritten."""

import datetime as dt
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from apps.audit import services as audit
from apps.core.exceptions import BusinessRuleError
from apps.core.services import next_number

from .models import ACTIVE_STATUSES, ChangeRequest, Employee, EmploymentRecord

SNAPSHOT = EmploymentRecord.SNAPSHOT_FIELDS
RETIREMENT_AGE = 60  # Ghana compulsory retirement age; configurable via org.settings["retirement_age"]


def _fk_or_value(record, name):
    field = EmploymentRecord._meta.get_field(name)
    return getattr(record, field.attname)


def _snapshot_from(record: EmploymentRecord) -> dict:
    return {EmploymentRecord._meta.get_field(f).attname: _fk_or_value(record, f) for f in SNAPSHOT}


def retirement_date_for(employee: Employee):
    if not employee.date_of_birth:
        return None
    age = employee.organization.settings.get("retirement_age", RETIREMENT_AGE) if employee.organization_id else RETIREMENT_AGE
    dob = employee.date_of_birth
    try:
        return dob.replace(year=dob.year + age)
    except ValueError:
        return dob.replace(year=dob.year + age, day=28)


def find_duplicates(first_name, last_name, date_of_birth=None, ghana_card_no="", ssnit_number="", exclude_id=None):
    q = Q()
    if ghana_card_no:
        q |= Q(ghana_card_no__iexact=ghana_card_no)
    if ssnit_number:
        q |= Q(ssnit_number__iexact=ssnit_number)
    if date_of_birth:
        q |= Q(first_name__iexact=first_name, last_name__iexact=last_name, date_of_birth=date_of_birth)
    if not q:
        return Employee.objects.none()
    qs = Employee.objects.filter(q)
    if exclude_id:
        qs = qs.exclude(pk=exclude_id)
    return qs


@transaction.atomic
def hire(data: dict, user=None, allow_duplicate=False) -> Employee:
    """Create an employee and the initial 'hire' employment record."""
    data = dict(data)
    if not allow_duplicate:
        dups = find_duplicates(data.get("first_name", ""), data.get("last_name", ""), data.get("date_of_birth"),
                               data.get("ghana_card_no", ""), data.get("ssnit_number", ""))
        exited = [d for d in dups if d.status == "exited"]
        if exited:
            raise BusinessRuleError(
                f"This person was previously employed ({exited[0].staff_number}). Use Rehire to keep a single identity.",
                code="rehire_required")
        if dups.exists():
            raise BusinessRuleError(f"Possible duplicate of {dups.first()}. Check Ghana Card/SSNIT/name and DOB.",
                                    code="duplicate")
    if not data.get("staff_number"):
        data["staff_number"] = next_number("staff_number", default_prefix="SL", default_pattern="{prefix}{seq:05d}")
    position = data.get("position")
    if position is not None:
        if position.status != "approved":
            raise BusinessRuleError("Employees can only be appointed to approved positions.")
        if position.vacancies <= 0:
            raise BusinessRuleError(f"Position {position.code} has no vacancy.", code="no_vacancy")
        data.setdefault("job_title", position.job_title)
        data.setdefault("department", position.department)
        data.setdefault("grade", position.grade)
        data.setdefault("branch", position.branch)
        data.setdefault("location", position.location)
        data.setdefault("employment_type", position.employment_type)
        if data.get("department") and data["department"].cost_center_id:
            data.setdefault("cost_center", data["department"].cost_center)
    if data.get("grade_step") and not data.get("basic_salary"):
        data["basic_salary"] = data["grade_step"].basic_salary
    data.setdefault("original_hire_date", data["hire_date"])
    if data.get("status") is None:
        data["status"] = "probation" if data.get("probation_end_date") else "active"
    employee = Employee(**{k: v for k, v in data.items() if hasattr(Employee, k) or k.endswith("_id")})
    employee.full_clean(exclude=["organization", "user"])
    employee.save()
    if not employee.retirement_date:
        employee.retirement_date = retirement_date_for(employee)
        employee.save(update_fields=["retirement_date"])
    record = EmploymentRecord(employee=employee, event_type=data.get("event_type", "hire"),
                              effective_from=employee.hire_date, reason=data.get("reason", "Appointment"),
                              approved_by=user)
    for f in SNAPSHOT:
        setattr(record, f, getattr(employee, f))
    record.is_current = employee.hire_date <= dt.date.today()
    record.is_applied = True
    record.save()
    return employee


@transaction.atomic
def apply_change(employee: Employee, event_type: str, effective_from: dt.date, changes: dict, reason="",
                 reference="", user=None) -> EmploymentRecord:
    """Insert a new effective-dated employment record. Future-dated changes are applied to the
    snapshot by `apply_due_records` when their date arrives."""
    employee = Employee.objects.select_for_update().get(pk=employee.pk)
    unknown = set(changes) - set(SNAPSHOT)
    if unknown:
        raise BusinessRuleError(f"Unsupported fields for a personnel action: {', '.join(sorted(unknown))}")
    if effective_from < employee.hire_date:
        raise BusinessRuleError("Effective date cannot be before the hire date.")
    if employee.status == "exited" and event_type not in ("correction",):
        raise BusinessRuleError("Employee has exited. Use Rehire instead.")
    if EmploymentRecord.objects.filter(employee=employee, effective_from=effective_from,
                                       event_type=event_type).exists():
        raise BusinessRuleError("An identical action already exists for that date.")

    # base the new record on the record in force on effective_from
    base = (EmploymentRecord.objects.filter(employee=employee, effective_from__lte=effective_from)
            .order_by("-effective_from", "-id").first())
    new = EmploymentRecord(employee=employee, event_type=event_type, effective_from=effective_from, reason=reason,
                           reference=reference, approved_by=user)
    for f in SNAPSHOT:
        setattr(new, f, getattr(base, f) if base else getattr(employee, f))
    if "position" in changes and changes["position"] is not None:
        pos = changes["position"]
        if pos.status != "approved":
            raise BusinessRuleError("Target position is not approved.")
        if pos.pk != employee.position_id and pos.vacancies <= 0:
            raise BusinessRuleError(f"Position {pos.code} has no vacancy.", code="no_vacancy")
        for f in ("job_title", "department", "grade", "branch", "location"):
            if f not in changes and getattr(pos, f, None) is not None:
                setattr(new, f, getattr(pos, f))
    if "grade_step" in changes and changes["grade_step"] is not None and "basic_salary" not in changes:
        new.basic_salary = changes["grade_step"].basic_salary
    for k, v in changes.items():
        setattr(new, k, v)

    # close the base record and any later records are left untouched (they remain in the future)
    if base and (base.effective_to is None or base.effective_to >= effective_from):
        later = (EmploymentRecord.objects.filter(employee=employee, effective_from__gt=effective_from)
                 .order_by("effective_from").first())
        new.effective_to = later.effective_from - dt.timedelta(days=1) if later else None
        base.effective_to = effective_from - dt.timedelta(days=1)
        base.save(update_fields=["effective_to", "updated_at"])
    new.save()
    if effective_from <= dt.date.today():
        _apply_snapshot(employee, new)
    audit.log("update", employee, {"personnel_action": event_type, "effective_from": effective_from,
                                   "fields": sorted(changes)})
    return new


def _apply_snapshot(employee: Employee, record: EmploymentRecord):
    EmploymentRecord.objects.filter(employee=employee, is_current=True).exclude(pk=record.pk).update(is_current=False)
    for attname, value in _snapshot_from(record).items():
        setattr(employee, attname, value)
    if record.event_type == "confirmation":
        employee.confirmation_date = record.effective_from
        if employee.status == "probation":
            employee.status = "active"
    employee.save()
    record.is_current = True
    record.is_applied = True
    record.save(update_fields=["is_current", "is_applied", "updated_at"])


def apply_due_records(today=None):
    """Daily job: apply future-dated records that are now effective."""
    today = today or dt.date.today()
    count = 0
    for record in EmploymentRecord.all_objects.filter(is_applied=False, effective_from__lte=today).order_by(
            "effective_from", "id").select_related("employee"):
        latest = (EmploymentRecord.all_objects.filter(employee=record.employee, effective_from__lte=today)
                  .order_by("-effective_from", "-id").first())
        if latest and latest.pk == record.pk:
            _apply_snapshot(record.employee, record)
        else:
            record.is_applied = True
            record.save(update_fields=["is_applied"])
        count += 1
    return count


def as_of(employee: Employee, on_date: dt.date):
    return (EmploymentRecord.objects.filter(employee=employee, effective_from__lte=on_date)
            .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=on_date))
            .order_by("-effective_from", "-id").first())


@transaction.atomic
def confirm_appointment(employee, effective_from, user=None, reason="Confirmed after satisfactory probation"):
    if employee.status != "probation":
        raise BusinessRuleError("Only employees on probation can be confirmed.")
    return apply_change(employee, "confirmation", effective_from, {"status": "active"}, reason=reason, user=user)


@transaction.atomic
def extend_probation(employee, new_end_date, user=None, reason=""):
    if employee.status != "probation":
        raise BusinessRuleError("Employee is not on probation.")
    employee.probation_end_date = new_end_date
    employee.save(update_fields=["probation_end_date", "updated_at"])
    return apply_change(employee, "probation_extension", dt.date.today(), {}, reason=reason or
                        f"Probation extended to {new_end_date:%d/%m/%Y}", user=user)


@transaction.atomic
def separate(employee: Employee, exit_date: dt.date, reason: str, notes="", rehire_eligible=True, user=None):
    """Record an exit. Linked offboarding (clearance, final pay, access revocation) keys off exit_date."""
    record = apply_change(employee, "exit", exit_date, {"status": "exited"}, reason=notes or reason, user=user)
    employee.refresh_from_db()
    employee.exit_date = exit_date
    employee.exit_reason = reason
    employee.rehire_eligible = rehire_eligible
    if exit_date > dt.date.today():
        employee.save(update_fields=["exit_date", "exit_reason", "rehire_eligible", "updated_at"])
    else:
        employee.status = "exited"
        employee.save()
        revoke_access(employee)
    # set retention dates on personnel documents
    from apps.documents.services import compute_retention

    for doc in employee.documents.all():
        doc.retention_until = compute_retention(doc)
        doc.save(update_fields=["retention_until"])
    return record


def revoke_access(employee: Employee):
    if employee.user_id and employee.user.is_active:
        user = employee.user
        user.is_active = False
        user.save(update_fields=["is_active"])
        audit.log("update", user, {"is_active": False, "reason": "employee exit"})


def process_due_exits(today=None):
    today = today or dt.date.today()
    n = 0
    for emp in Employee.all_objects.filter(exit_date__lte=today).exclude(status="exited"):
        emp.status = "exited"
        emp.save(update_fields=["status"])
        revoke_access(emp)
        n += 1
    return n


@transaction.atomic
def rehire(previous: Employee, hire_date: dt.date, data: dict, user=None) -> Employee:
    """Rehire keeps the person's historical identity: a new employment record linked to the old one."""
    if previous.status != "exited":
        raise BusinessRuleError("Only former employees can be rehired.")
    if not previous.rehire_eligible:
        raise BusinessRuleError("This former employee is marked as not eligible for rehire.")
    personal = {f: getattr(previous, f) for f in (
        "title", "first_name", "middle_name", "last_name", "preferred_name", "gender", "date_of_birth",
        "marital_status", "nationality", "ghana_card_no", "ssnit_number", "tin", "passport_no", "hometown",
        "region_of_origin", "personal_email", "phone", "alt_phone", "residential_address", "digital_address")}
    personal.update(data)
    personal.update({"hire_date": hire_date, "original_hire_date": previous.original_hire_date or previous.hire_date,
                     "previous_record": previous, "event_type": "rehire", "reason": "Rehire"})
    personal.setdefault("staff_number", previous.staff_number + "-R" if data.get("keep_staff_number") else None)
    personal.pop("keep_staff_number", None)
    if personal.get("staff_number") is None:
        personal.pop("staff_number")
    new = hire(personal, user=user, allow_duplicate=True)
    if previous.user_id and not new.user_id:
        previous_user = previous.user
        previous.user = None
        previous.save(update_fields=["user"])
        previous_user.is_active = True
        previous_user.save(update_fields=["is_active"])
        new.user = previous_user
        new.save(update_fields=["user"])
    return new


# ------------------------------------------------------------------ change requests
def submit_change_request(employee, changes: dict, reason, user) -> ChangeRequest:
    from apps.workflow import engine

    illegal = set(changes) - set(ChangeRequest.ALLOWED_FIELDS)
    if illegal:
        raise BusinessRuleError(f"These fields cannot be changed via self-service: {', '.join(sorted(illegal))}")
    if not changes:
        raise BusinessRuleError("No changes submitted.")
    previous = {k: str(getattr(employee, k) or "") for k in changes}
    cr = ChangeRequest.objects.create(employee=employee, changes=changes, previous=previous, reason=reason)
    engine.start(cr, "employee_change", user, subject_employee=employee)
    return cr


@transaction.atomic
def apply_change_request(cr: ChangeRequest):
    emp = cr.employee
    for k, v in cr.changes.items():
        field = Employee._meta.get_field(k)
        value = field.to_python(v) if v not in ("", None) else ("" if not field.null else None)
        setattr(emp, k, value)
    emp.full_clean(exclude=["organization", "user"])
    emp.save()
    cr.status = "approved"
    cr.applied_at = timezone.now()
    cr.save(update_fields=["status", "applied_at", "updated_at"])


# ------------------------------------------------------------------ data quality
REQUIRED_FIELDS = ["date_of_birth", "gender", "ghana_card_no", "ssnit_number", "phone", "department", "job_title",
                   "grade", "supervisor"]


def data_quality_report():
    """Missing fields, duplicates and inconsistent records for active employees."""
    active = Employee.objects.filter(status__in=ACTIVE_STATUSES)
    total = active.count()
    missing = {}
    for f in REQUIRED_FIELDS:
        lookup = {f"{f}__isnull": True} if Employee._meta.get_field(f).is_relation or f == "date_of_birth" else {f: ""}
        missing[f] = active.filter(**lookup).count()
    issues = []
    for emp in active.select_related("supervisor"):
        if emp.contract_end_date and emp.contract_end_date < dt.date.today():
            issues.append({"employee": emp.id, "name": emp.full_name, "issue": "Contract end date has passed"})
        if emp.date_of_birth and emp.hire_date and (emp.hire_date - emp.date_of_birth).days < 15 * 365:
            issues.append({"employee": emp.id, "name": emp.full_name, "issue": "Hire age under 15 - check dates"})
        if emp.supervisor_id == emp.id:
            issues.append({"employee": emp.id, "name": emp.full_name, "issue": "Employee is own supervisor"})
        if emp.basic_salary <= Decimal("0"):
            issues.append({"employee": emp.id, "name": emp.full_name, "issue": "No basic salary"})
        if emp.status == "probation" and emp.probation_end_date and emp.probation_end_date < dt.date.today():
            issues.append({"employee": emp.id, "name": emp.full_name, "issue": "Probation overdue for review"})
    dup_cards = (active.exclude(ghana_card_no="").values("ghana_card_no").order_by()
                 .annotate(n=Count("id")).filter(n__gt=1))
    complete = active
    for f in REQUIRED_FIELDS:
        lookup = {f"{f}__isnull": True} if Employee._meta.get_field(f).is_relation or f == "date_of_birth" else {f: ""}
        complete = complete.exclude(**lookup)
    return {
        "active_employees": total,
        "complete_records": complete.count(),
        "completeness_percent": round(complete.count() * 100 / total, 1) if total else 100.0,
        "missing_fields": missing,
        "duplicate_ghana_cards": list(dup_cards),
        "issues": issues[:500],
    }
