"""HR analytics: operational dashboard, strategic KPIs and the standard report catalogue.

Every KPI has a documented definition (KPI_DEFINITIONS) so figures stay consistent. All figures
are computed within the requesting user's data scope."""

import datetime as dt
from collections import Counter
from decimal import Decimal

from django.db.models import Count, Q, Sum

from apps.employees.models import ACTIVE_STATUSES, Employee, EmploymentRecord
from apps.rbac.services import has_perm, scope_queryset

KPI_DEFINITIONS = {
    "headcount": {"name": "Headcount", "formula": "Employees with status active, probation, suspended or on_leave",
                  "source": "Employee master", "frequency": "Real-time"},
    "turnover_rate": {"name": "Turnover rate (12 months)",
                      "formula": "Exits in last 12 months / average headcount over the period x 100",
                      "source": "Employee exits", "frequency": "Monthly"},
    "retention_rate": {"name": "12-month retention", "formula": "Employees employed 12 months ago still employed / "
                       "headcount 12 months ago x 100", "source": "Employment records", "frequency": "Monthly"},
    "vacancy_rate": {"name": "Vacancy rate", "formula": "Vacant approved posts / approved establishment x 100",
                     "source": "Positions", "frequency": "Real-time"},
    "absence_rate": {"name": "Absence rate", "formula": "Approved sick + unpaid + unexcused absence days / "
                     "scheduled working days x 100 (last 90 days)", "source": "Attendance & leave",
                     "frequency": "Monthly"},
    "record_completeness": {"name": "Records complete", "formula": "Active employees with all mandatory fields / "
                            "active employees x 100", "source": "Employee master", "frequency": "Real-time"},
    "sla_compliance": {"name": "Approvals within SLA", "formula": "Workflow tasks completed before due time / tasks "
                       "completed x 100 (last 90 days)", "source": "Workflow engine", "frequency": "Weekly"},
    "avg_approval_hours": {"name": "Average approval turnaround", "formula": "Mean hours from task creation to action",
                           "source": "Workflow engine", "frequency": "Weekly"},
    "self_service_rate": {"name": "Self-service adoption", "formula": "Requests initiated by the subject employee / all "
                          "requests x 100 (last 90 days)", "source": "Workflow engine", "frequency": "Monthly"},
    "payroll_cost": {"name": "Monthly payroll cost", "formula": "Gross pay + employer contributions of the latest "
                     "released regular run", "source": "Payroll", "frequency": "Monthly"},
}


def _employees(user):
    return scope_queryset(user, Employee.objects.all(), "employees.view")


def _age(dob, today):
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def dashboard(user):
    from apps.attendance.models import AttendanceDay
    from apps.documents.models import Document
    from apps.leave.models import LeaveRequest
    from apps.leave.services import on_leave_on
    from apps.organization.models import Position
    from apps.workflow.models import WorkflowTask

    today = dt.date.today()
    month_start = today.replace(day=1)
    in_60 = today + dt.timedelta(days=60)
    emps = _employees(user)
    active = emps.filter(status__in=ACTIVE_STATUSES)
    headcount = active.count()

    def dist(field, label_field=None):
        rows = active.values(label_field or field).annotate(n=Count("id")).order_by("-n")
        return [{"label": r[label_field or field] or "Unassigned", "value": r["n"]} for r in rows]

    pending_leave = LeaveRequest.objects.filter(status="pending", employee__in=emps).count()
    on_leave_today = on_leave_on(today).filter(employee__in=active).count()
    yesterday = today - dt.timedelta(days=1)
    exceptions = AttendanceDay.objects.filter(date=yesterday, is_exception=True, employee__in=active)
    ot_pending = AttendanceDay.objects.filter(overtime_status="pending", employee__in=active,
                                              date__gte=today - dt.timedelta(days=45)).count()
    positions = Position.objects.filter(status="approved")
    approved_posts = sum(p.headcount for p in positions)
    vacant = sum(p.vacancies for p in positions)
    tasks = WorkflowTask.objects.filter(status="pending", instance__status="in_progress")
    data = {
        "as_of": today,
        "headcount": headcount,
        "on_probation": active.filter(status="probation").count(),
        "new_hires_month": emps.filter(hire_date__gte=month_start, hire_date__lte=today).count(),
        "new_hires_ytd": emps.filter(hire_date__year=today.year, hire_date__lte=today).count(),
        "exits_month": emps.filter(exit_date__gte=month_start, exit_date__lte=today).count(),
        "exits_ytd": emps.filter(exit_date__year=today.year, exit_date__lte=today).count(),
        "by_department": dist("department__name"),
        "by_employment_type": dist("employment_type"),
        "by_gender": dist("gender"),
        "by_grade": dist("grade__code"),
        "by_location": dist("location__name"),
        "establishment": {"approved": approved_posts, "vacant": vacant, "filled": approved_posts - vacant},
        "pending_leave_approvals": pending_leave,
        "on_leave_today": on_leave_today,
        "attendance_exceptions_yesterday": exceptions.count(),
        "absent_yesterday": exceptions.filter(status="absent").count(),
        "late_yesterday": exceptions.filter(status="late").count(),
        "overtime_pending_approval": ot_pending,
        "my_pending_tasks": tasks.filter(assignee=user).count(),
        "overdue_tasks": tasks.filter(due_at__lt=dt.datetime.now(dt.timezone.utc)).count()
        if has_perm(user, "workflow.admin") else tasks.filter(assignee=user, due_at__lt=dt.datetime.now(dt.timezone.utc)).count(),
        "expiring": {
            "contracts": list(active.filter(contract_end_date__range=(today, in_60)).order_by("contract_end_date")
                              .values("id", "first_name", "last_name", "staff_number", "contract_end_date")[:20]),
            "probation": list(active.filter(status="probation", probation_end_date__lte=in_60)
                              .order_by("probation_end_date")
                              .values("id", "first_name", "last_name", "staff_number", "probation_end_date")[:20]),
            "documents": Document.objects.filter(employee__in=active, expiry_date__range=(today, in_60),
                                                 is_archived=False).count(),
            "retirements_12m": active.filter(retirement_date__range=(today, today + dt.timedelta(days=365))).count(),
        },
    }
    if has_perm(user, "reports.view_payroll"):
        data["payroll"] = payroll_status()
    if has_perm(user, "organization.manage") or has_perm(user, "employees.view", "organization"):
        from apps.employees.services import data_quality_report

        dq = data_quality_report()
        data["record_completeness"] = dq["completeness_percent"]
    return data


def payroll_status():
    from apps.payroll.models import PayrollRun

    latest = PayrollRun.objects.filter(run_type="regular").select_related("period").order_by("-period__start_date").first()
    paid = PayrollRun.objects.filter(run_type="regular", status="paid").select_related("period").order_by(
        "-period__start_date").first()
    out = {"current": None, "last_paid": None}
    if latest:
        out["current"] = {"id": latest.id, "period": latest.period.name, "status": latest.get_status_display(),
                          "net": latest.totals.get("net"), "employees": latest.totals.get("employees")}
    if paid:
        out["last_paid"] = {"id": paid.id, "period": paid.period.name, "gross": paid.totals.get("gross"),
                            "net": paid.totals.get("net"), "employer_cost": paid.totals.get("employer_cost"),
                            "paye": paid.totals.get("paye"), "ssnit": str(Decimal(paid.totals.get("ssnit_employee", "0"))
                                                                         + Decimal(paid.totals.get("ssnit_employer", "0")))}
    return out


def strategic(user):
    from apps.attendance.models import AttendanceDay
    from apps.leave.models import LeaveRequest
    from apps.workflow.models import WorkflowInstance, WorkflowTask

    today = dt.date.today()
    year_ago = today - dt.timedelta(days=365)
    emps = _employees(user)
    active = emps.filter(status__in=ACTIVE_STATUSES)
    headcount = active.count()
    hc_year_ago = emps.filter(hire_date__lte=year_ago).filter(Q(exit_date__isnull=True) | Q(exit_date__gt=year_ago)).count()
    exits_12m = emps.filter(exit_date__range=(year_ago, today))
    avg_hc = (headcount + hc_year_ago) / 2 or 1
    still = emps.filter(hire_date__lte=year_ago).filter(Q(exit_date__isnull=True) | Q(exit_date__gt=today)).count()

    exit_reasons = list(exits_12m.values("exit_reason").annotate(n=Count("id")).order_by("-n"))
    voluntary = exits_12m.filter(exit_reason="resignation").count()

    # monthly hires/exits trend (12 months)
    trend = []
    months, ref = [], today.replace(day=1)
    for _ in range(12):
        months.append(ref)
        ref = (ref - dt.timedelta(days=1)).replace(day=1)
    for m_start in reversed(months):
        m_end = (m_start.replace(day=28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(days=1)
        trend.append({"month": m_start.strftime("%b %Y"),
                      "hires": emps.filter(hire_date__range=(m_start, m_end)).count(),
                      "exits": emps.filter(exit_date__range=(m_start, m_end)).count(),
                      "headcount": emps.filter(hire_date__lte=m_end).filter(
                          Q(exit_date__isnull=True) | Q(exit_date__gt=m_end)).count()})

    # absence (90 days)
    d90 = today - dt.timedelta(days=90)
    scheduled = AttendanceDay.objects.filter(employee__in=active, date__gte=d90).exclude(status__in=["off", "holiday"]).count()
    absent = AttendanceDay.objects.filter(employee__in=active, date__gte=d90, status="absent").count()
    sick = LeaveRequest.objects.filter(employee__in=active, leave_type__code="sick", status="approved",
                                       start_date__gte=d90).aggregate(d=Sum("days"))["d"] or 0
    absence_rate = round((absent + float(sick)) * 100 / scheduled, 2) if scheduled else None

    # workflow service KPIs (90 days)
    done = WorkflowTask.objects.filter(acted_at__gte=d90, status__in=["approved", "rejected", "returned"])
    within = done.filter(due_at__isnull=False).filter(acted_at__lte=models_F("due_at")).count()
    with_due = done.filter(due_at__isnull=False).count()
    hours = [(t.acted_at - t.created_at).total_seconds() / 3600 for t in done.only("acted_at", "created_at")[:5000]]
    instances = WorkflowInstance.objects.filter(created_at__date__gte=d90)
    self_service = instances.filter(subject_employee__user=models_F("initiator")).count()

    # demographics (aggregated)
    ages = [_age(d, today) for d in active.exclude(date_of_birth__isnull=True).values_list("date_of_birth", flat=True)]
    bands = Counter()
    for a in ages:
        bands["<25" if a < 25 else "25-34" if a < 35 else "35-44" if a < 45 else "45-54" if a < 55 else "55+"] += 1
    retire = []
    for y in range(today.year, today.year + 5):
        retire.append({"year": y, "count": active.filter(retirement_date__year=y).count()})

    # tenure
    tenure = Counter()
    for h in active.values_list("original_hire_date", "hire_date"):
        start = h[0] or h[1]
        yrs = (today - start).days / 365.25
        tenure["<1" if yrs < 1 else "1-3" if yrs < 3 else "3-5" if yrs < 5 else "5-10" if yrs < 10 else "10+"] += 1

    promotions = EmploymentRecord.objects.filter(employee__in=emps, event_type="promotion",
                                                 effective_from__gte=year_ago).count()
    out = {
        "turnover_rate": round(exits_12m.count() * 100 / avg_hc, 2),
        "voluntary_turnover_rate": round(voluntary * 100 / avg_hc, 2),
        "retention_rate": round(still * 100 / hc_year_ago, 2) if hc_year_ago else None,
        "exit_reasons": exit_reasons,
        "trend": trend,
        "absence_rate": absence_rate,
        "sla_compliance": round(within * 100 / with_due, 1) if with_due else None,
        "avg_approval_hours": round(sum(hours) / len(hours), 1) if hours else None,
        "self_service_rate": round(self_service * 100 / instances.count(), 1) if instances.count() else None,
        "age_bands": [{"label": k, "value": bands.get(k, 0)} for k in ["<25", "25-34", "35-44", "45-54", "55+"]],
        "tenure_bands": [{"label": k, "value": tenure.get(k, 0)} for k in ["<1", "1-3", "3-5", "5-10", "10+"]],
        "retirement_forecast": retire,
        "promotions_12m": promotions,
        "kpi_definitions": KPI_DEFINITIONS,
    }
    if has_perm(user, "reports.view_payroll"):
        out["cost_by_department"] = payroll_cost_by_department()
    return out


def models_F(name):
    from django.db.models import F

    return F(name)


def payroll_cost_by_department():
    from apps.payroll.models import PayrollRun

    run = PayrollRun.objects.filter(run_type="regular", status="paid").order_by("-period__start_date").first()
    if run is None:
        return []
    rows = (run.payslips.values("department").annotate(gross=Sum("gross_pay"), employer=Sum("employer_cost"),
                                                       headcount=Count("id")).order_by("-employer"))
    return [{"department": r["department"] or "Unassigned", "gross": r["gross"], "employer_cost": r["employer"],
             "headcount": r["headcount"], "period": run.period.name} for r in rows]


# ------------------------------------------------------------------ report catalogue
def report_headcount(user, params):
    qs = _employees(user).filter(status__in=ACTIVE_STATUSES).select_related("department", "job_title", "grade",
                                                                            "branch", "supervisor")
    if params.get("department"):
        qs = qs.filter(department_id=params["department"])
    headers = ["Staff No", "Name", "Gender", "Department", "Job title", "Grade", "Branch", "Employment type",
               "Status", "Hire date", "Supervisor"]
    rows = [[e.staff_number, e.full_name, e.gender, e.department.name if e.department_id else "",
             e.job_title.name if e.job_title_id else "", e.grade.code if e.grade_id else "",
             e.branch.name if e.branch_id else "", e.employment_type, e.get_status_display(),
             e.hire_date.strftime("%d/%m/%Y"), e.supervisor.full_name if e.supervisor_id else ""] for e in qs]
    return headers, rows


def _date_range(params):
    today = dt.date.today()
    start = dt.date.fromisoformat(params["start"]) if params.get("start") else today.replace(month=1, day=1)
    end = dt.date.fromisoformat(params["end"]) if params.get("end") else today
    return start, end


def report_hires(user, params):
    start, end = _date_range(params)
    qs = _employees(user).filter(hire_date__range=(start, end)).select_related("department", "job_title")
    headers = ["Staff No", "Name", "Department", "Job title", "Employment type", "Hire date"]
    return headers, [[e.staff_number, e.full_name, e.department.name if e.department_id else "",
                      e.job_title.name if e.job_title_id else "", e.employment_type,
                      e.hire_date.strftime("%d/%m/%Y")] for e in qs.order_by("hire_date")]


def report_exits(user, params):
    start, end = _date_range(params)
    qs = _employees(user).filter(exit_date__range=(start, end)).select_related("department", "job_title")
    headers = ["Staff No", "Name", "Department", "Job title", "Hire date", "Exit date", "Reason", "Rehire eligible"]
    return headers, [[e.staff_number, e.full_name, e.department.name if e.department_id else "",
                      e.job_title.name if e.job_title_id else "", e.hire_date.strftime("%d/%m/%Y"),
                      e.exit_date.strftime("%d/%m/%Y"), e.exit_reason, "Yes" if e.rehire_eligible else "No"]
                     for e in qs.order_by("exit_date")]


def report_expiries(user, params):
    days = int(params.get("days", 90))
    today = dt.date.today()
    end = today + dt.timedelta(days=days)
    qs = _employees(user).filter(status__in=ACTIVE_STATUSES)
    rows = []
    for e in qs.filter(contract_end_date__range=(today, end)):
        rows.append([e.staff_number, e.full_name, "Contract", e.contract_end_date.strftime("%d/%m/%Y")])
    for e in qs.filter(status="probation", probation_end_date__lte=end):
        rows.append([e.staff_number, e.full_name, "Probation", e.probation_end_date.strftime("%d/%m/%Y")])
    for e in qs.filter(retirement_date__range=(today, end)):
        rows.append([e.staff_number, e.full_name, "Retirement", e.retirement_date.strftime("%d/%m/%Y")])
    from apps.documents.models import Document

    for d in Document.objects.filter(employee__in=qs, expiry_date__range=(today, end), is_archived=False).select_related("employee"):
        rows.append([d.employee.staff_number, d.employee.full_name, f"Document: {d.title}",
                     d.expiry_date.strftime("%d/%m/%Y")])
    rows.sort(key=lambda r: dt.datetime.strptime(r[3], "%d/%m/%Y"))
    return ["Staff No", "Name", "Item", "Expiry date"], rows


def report_attendance(user, params):
    from apps.attendance.models import AttendanceDay

    start, end = _date_range(params)
    qs = AttendanceDay.objects.filter(employee__in=_employees(user), date__range=(start, end))
    agg = {}
    for d in qs.select_related("employee"):
        r = agg.setdefault(d.employee_id, {"emp": d.employee, "present": 0, "late": 0, "absent": 0, "incomplete": 0,
                                           "leave": 0, "ot": 0})
        if d.status in ("present", "late", "half_day"):
            r["present"] += 1
        if d.late_minutes:
            r["late"] += 1
        if d.status == "absent":
            r["absent"] += 1
        if d.status == "incomplete":
            r["incomplete"] += 1
        if d.status == "on_leave":
            r["leave"] += 1
        r["ot"] += d.approved_overtime_minutes
    headers = ["Staff No", "Name", "Days present", "Late arrivals", "Absences", "Missing punches", "On leave",
               "Approved OT (h)"]
    return headers, [[r["emp"].staff_number, r["emp"].full_name, r["present"], r["late"], r["absent"], r["incomplete"],
                      r["leave"], round(r["ot"] / 60, 2)] for r in agg.values()]


def report_payroll_cost(user, params):
    if not has_perm(user, "reports.view_payroll"):
        return ["Message"], [["Payroll reports require payroll reporting permission."]]
    return ["Department", "Headcount", "Gross", "Employer cost", "Period"], [
        [r["department"], r["headcount"], r["gross"], r["employer_cost"], r["period"]]
        for r in payroll_cost_by_department()]


REPORTS = {
    "headcount": ("Headcount register", report_headcount),
    "hires": ("New hires", report_hires),
    "exits": ("Exits & separations", report_exits),
    "expiries": ("Upcoming expiries (contracts, probation, retirement, documents)", report_expiries),
    "attendance": ("Attendance summary", report_attendance),
    "payroll_cost": ("Payroll cost by department", report_payroll_cost),
}


def custom_definitions(user):
    """Saved report-builder definitions the user may run: their own plus shared ones."""
    from .models import ReportDefinition

    return ReportDefinition.objects.filter(Q(created_by=user) | Q(visibility="shared"))


def get_report(code, user):
    """(name, fn(user, params) -> (headers, rows)) for a standard code or `custom:<id>`; None if unknown."""
    if code in REPORTS:
        return REPORTS[code]
    if code.startswith("custom:") and code[7:].isdigit():
        from . import builder

        definition = custom_definitions(user).filter(pk=int(code[7:])).first()
        if definition is None:
            return None
        spec = definition.spec()
        return definition.name, lambda u, params: builder.run(spec, u)[:2]
    return None
