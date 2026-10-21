"""Self-service report builder.

Reports are built from whitelisted datasets and fields only, never from free-form ORM lookups. Each
dataset is scoped to the viewer's data scope at run time, so sharing a definition never widens what a
colleague can see. Sensitive fields need their own permission, and the whole dataset can need one.
"""

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal

from apps.core.exceptions import BusinessRuleError
from apps.rbac.services import has_perm, scope_queryset

MAX_ROWS = 50000
OPS = {"eq", "ne", "in", "gt", "gte", "lt", "lte", "contains", "isnull", "last_days"}
AGGREGATES = {"count", "sum", "avg", "min", "max"}
TENURE_BANDS = ("<1", "1-3", "3-5", "5-10", "10+")
AGE_BANDS = ("<25", "25-34", "35-44", "45-54", "55+")


@dataclass
class F:
    label: str
    lookup: str = ""                  # ORM path; blank for computed fields
    type: str = "text"                # text | number | money | date | choice | bool
    perm: str | None = None           # extra permission needed to see or filter on this field
    choices: dict | None = None
    compute: object = None            # fn(row: dict, today) -> value, for derived fields
    needs: tuple = ()                 # lookups the compute fn reads
    order: tuple = ()                 # natural order of band values, used when grouping


@dataclass
class Dataset:
    label: str
    model: object                     # callable returning the model class (lazy import)
    scope_code: str
    prefix: str = ""
    perm: str | None = None
    description: str = ""
    fields: dict = field(default_factory=dict)


def _age(d, today):
    return today.year - d.year - ((today.month, today.day) < (d.month, d.day)) if d else None


def _band(v, edges, labels):
    if v is None:
        return ""
    for edge, label in zip(edges, labels):
        if v < edge:
            return label
    return labels[-1]


def _name(prefix=""):
    return F("Name", type="text", needs=(f"{prefix}first_name", f"{prefix}last_name"),
             compute=lambda r, t: f"{r[f'{prefix}first_name']} {r[f'{prefix}last_name']}")


def _employees():
    from apps.employees.models import Employee

    return Employee


def _employee_fields():
    from apps.employees.models import Employee
    from apps.organization.models import Position

    return {
        "staff_number": F("Staff No", "staff_number"),
        "name": _name(),
        "gender": F("Gender", "gender", "choice", choices=dict(Employee.GENDERS)),
        "department": F("Department", "department__name"),
        "branch": F("Branch", "branch__name"),
        "location": F("Location", "location__name"),
        "job_title": F("Job title", "job_title__name"),
        "grade": F("Grade", "grade__code"),
        "cost_center": F("Cost centre", "cost_center__code"),
        "category": F("Category", "category__name"),
        "employment_type": F("Employment type", "employment_type", "choice", choices=dict(Position.EMPLOYMENT_TYPES)),
        "status": F("Status", "status", "choice", choices=dict(Employee.STATUS)),
        "supervisor": F("Supervisor", type="text", needs=("supervisor__first_name", "supervisor__last_name"),
                        compute=lambda r, t: " ".join(filter(None, [r["supervisor__first_name"],
                                                                     r["supervisor__last_name"]]))),
        "hire_date": F("Hire date", "hire_date", "date"),
        "confirmation_date": F("Confirmation date", "confirmation_date", "date"),
        "contract_end_date": F("Contract end", "contract_end_date", "date"),
        "retirement_date": F("Retirement date", "retirement_date", "date"),
        "exit_date": F("Exit date", "exit_date", "date"),
        "exit_reason": F("Exit reason", "exit_reason"),
        "tenure_years": F("Tenure (years)", type="number", needs=("hire_date", "original_hire_date", "exit_date"),
                          compute=lambda r, t: round(((r["exit_date"] or t) - (r["original_hire_date"]
                                                                               or r["hire_date"])).days / 365.25, 1)),
        "tenure_band": F("Tenure band", type="text", needs=("hire_date", "original_hire_date", "exit_date"),
                         compute=lambda r, t: _band(((r["exit_date"] or t) - (r["original_hire_date"]
                                                                              or r["hire_date"])).days / 365.25,
                                                    [1, 3, 5, 10], TENURE_BANDS), order=TENURE_BANDS),
        "age_band": F("Age band", type="text", needs=("date_of_birth",),
                      compute=lambda r, t: _band(_age(r["date_of_birth"], t), [25, 35, 45, 55], AGE_BANDS),
                      order=AGE_BANDS),
        "date_of_birth": F("Date of birth", "date_of_birth", "date", perm="employees.view_personal"),
        "basic_salary": F("Basic salary", "basic_salary", "money", perm="employees.view_salary"),
    }


def _emp_ref(prefix="employee__"):
    return {
        "staff_number": F("Staff No", f"{prefix}staff_number"),
        "name": _name(prefix),
        "department": F("Department", f"{prefix}department__name"),
        "job_title": F("Job title", f"{prefix}job_title__name"),
        "branch": F("Branch", f"{prefix}branch__name"),
    }


def datasets():
    """The dataset registry. Built lazily so model imports stay out of module import time."""
    from apps.attendance.models import AttendanceDay
    from apps.leave.models import LeaveRequest
    from apps.learning.models import Course, Enrollment
    from apps.payroll.models import Payslip

    return {
        "employees": Dataset("Employees", _employees, "employees.view",
                             description="One row per employee record (current and former) in your scope.",
                             fields=_employee_fields()),
        "leave": Dataset("Leave requests", lambda: LeaveRequest, "leave.view", "employee__",
                         description="One row per leave request.", fields={
                             **_emp_ref(),
                             "leave_type": F("Leave type", "leave_type__name"),
                             "start_date": F("Start", "start_date", "date"),
                             "end_date": F("End", "end_date", "date"),
                             "days": F("Days", "days", "number"),
                             "status": F("Status", "status", "choice", choices=dict(LeaveRequest.STATUS)),
                         }),
        "attendance": Dataset("Attendance days", lambda: AttendanceDay, "attendance.view", "employee__",
                              description="One row per employee per day. Filter by date to keep it fast.", fields={
                                  **_emp_ref(),
                                  "date": F("Date", "date", "date"),
                                  "status": F("Status", "status", "choice", choices=dict(AttendanceDay.STATUS)),
                                  "late_minutes": F("Late (min)", "late_minutes", "number"),
                                  "worked_hours": F("Worked (h)", type="number", needs=("worked_minutes",),
                                                    compute=lambda r, t: round(r["worked_minutes"] / 60, 2)),
                                  "overtime_hours": F("Approved OT (h)", type="number",
                                                      needs=("approved_overtime_minutes",),
                                                      compute=lambda r, t: round(r["approved_overtime_minutes"] / 60, 2)),
                                  "is_exception": F("Exception", "is_exception", "bool"),
                              }),
        "training": Dataset("Training enrolments", lambda: Enrollment, "learning.view", "employee__",
                            description="One row per course enrolment.", fields={
                                **_emp_ref(),
                                "course": F("Course", "course__title"),
                                "category": F("Category", "course__category", "choice",
                                              choices=dict(Course.CATEGORIES)),
                                "status": F("Status", "status", "choice", choices=dict(Enrollment.STATUS)),
                                "source": F("Source", "source", "choice", choices=dict(Enrollment.SOURCES)),
                                "due_date": F("Due", "due_date", "date"),
                                "completed_at": F("Completed", "completed_at", "date"),
                                "expires_on": F("Expires", "expires_on", "date"),
                                "cost": F("Cost", "cost", "money"),
                            }),
        "payslips": Dataset("Payslips", lambda: Payslip, "payroll.view", "employee__", perm="reports.view_payroll",
                            description="One row per payslip; department and grade as at the pay run.", fields={
                                "period": F("Period", "run__period__name"),
                                "period_start": F("Period start", "run__period__start_date", "date"),
                                "run_type": F("Run type", "run__run_type"),
                                "staff_number": F("Staff No", "staff_number"),
                                "name": F("Name", "employee_name"),
                                "department": F("Department", "department"),
                                "grade": F("Grade", "grade"),
                                "cost_center": F("Cost centre", "cost_center"),
                                "gross_pay": F("Gross", "gross_pay", "money"),
                                "paye": F("PAYE", "paye", "money"),
                                "ssnit_employee": F("SSNIT (employee)", "ssnit_employee", "money"),
                                "ssnit_employer": F("SSNIT (employer)", "ssnit_employer", "money"),
                                "net_pay": F("Net pay", "net_pay", "money"),
                                "employer_cost": F("Employer cost", "employer_cost", "money"),
                            }),
    }


def catalog(user):
    """Datasets and fields this user may build with."""
    out = []
    for code, ds in datasets().items():
        if not has_perm(user, ds.scope_code) or (ds.perm and not has_perm(user, ds.perm)):
            continue
        out.append({"code": code, "label": ds.label, "description": ds.description,
                    "fields": [{"code": k, "label": f.label, "type": f.type,
                                "choices": [{"value": v, "label": lb} for v, lb in (f.choices or {}).items()]}
                               for k, f in ds.fields.items() if not f.perm or has_perm(user, f.perm)]})
    return out


# ---------------------------------------------------------------- validation
def validate(spec, user=None):
    """Check a definition against the registry. Returns the normalised spec or raises BusinessRuleError."""
    reg = datasets()
    ds = reg.get(spec.get("dataset"))
    if ds is None:
        raise BusinessRuleError("Choose a dataset.", code="report_dataset")
    if user is not None and (not has_perm(user, ds.scope_code) or (ds.perm and not has_perm(user, ds.perm))):
        raise BusinessRuleError(f"You do not have access to the {ds.label} dataset.", code="report_dataset")

    def check_field(code, what):
        f = ds.fields.get(code)
        if f is None:
            raise BusinessRuleError(f"Unknown {what} field '{code}'.", code="report_field")
        if user is not None and f.perm and not has_perm(user, f.perm):
            raise BusinessRuleError(f"You are not permitted to use '{f.label}'.", code="report_field")
        return f

    columns = list(spec.get("columns") or [])
    group_by = list(spec.get("group_by") or [])[:2]
    aggregates = list(spec.get("aggregates") or [])
    if not columns and not group_by:
        raise BusinessRuleError("Pick at least one column.", code="report_columns")
    for c in columns + group_by:
        check_field(c, "column")
    for a in aggregates:
        if a.get("fn") not in AGGREGATES:
            raise BusinessRuleError(f"Unknown summary '{a.get('fn')}'.", code="report_aggregate")
        if a["fn"] != "count":
            f = check_field(a.get("field"), "summary")
            if f.type not in ("number", "money"):
                raise BusinessRuleError(f"'{f.label}' is not numeric.", code="report_aggregate")
    if group_by and not aggregates:
        aggregates = [{"fn": "count"}]
    filters = []
    for flt in spec.get("filters") or []:
        f = check_field(flt.get("field"), "filter")
        op = flt.get("op", "eq")
        if op not in OPS:
            raise BusinessRuleError(f"Unknown operator '{op}'.", code="report_filter")
        if op == "last_days" and f.type != "date":
            raise BusinessRuleError(f"'{f.label}' is not a date.", code="report_filter")
        filters.append({"field": flt["field"], "op": op, "value": flt.get("value")})
    sort = spec.get("sort") or ""
    if sort and sort.lstrip("-") not in ds.fields and sort.lstrip("-") not in {_agg_key(a) for a in aggregates}:
        raise BusinessRuleError("Sort must be one of the report's columns.", code="report_sort")
    limit = int(spec.get("limit") or 0)
    return {"dataset": spec["dataset"], "columns": columns, "group_by": group_by, "aggregates": aggregates,
            "filters": filters, "sort": sort, "limit": max(0, min(limit, MAX_ROWS))}


def _agg_key(a):
    return a["fn"] if a["fn"] == "count" else f"{a['fn']}_{a['field']}"


# ---------------------------------------------------------------- execution
def _coerce(f: F, value):
    if value in (None, ""):
        return value
    if f.type == "date":
        return value if isinstance(value, dt.date) else dt.date.fromisoformat(str(value)[:10])
    if f.type in ("number", "money"):
        return Decimal(str(value))
    if f.type == "bool":
        return value if isinstance(value, bool) else str(value).lower() in ("1", "true", "yes")
    return value


def _orm_filter(qs, f: F, op, value, today):
    lk = f.lookup
    if op == "isnull":
        truthy = value in (True, "true", "1", 1, None, "")
        return qs.filter(**{f"{lk}__isnull": truthy})
    if op == "last_days":
        return qs.filter(**{f"{lk}__gte": today - dt.timedelta(days=int(value or 30)), f"{lk}__lte": today})
    if op == "in":
        vals = value if isinstance(value, list) else [v.strip() for v in str(value).split(",") if v.strip()]
        return qs.filter(**{f"{lk}__in": [_coerce(f, v) for v in vals]})
    if op == "contains":
        return qs.filter(**{f"{lk}__icontains": value})
    v = _coerce(f, value)
    if op == "ne":
        return qs.exclude(**{lk: v})
    suffix = "" if op == "eq" else f"__{op}"
    return qs.filter(**{f"{lk}{suffix}": v})


def _py_match(v, op, value):
    if op == "isnull":
        return (v in (None, "")) == (value in (True, "true", "1", 1, None, ""))
    if op == "in":
        vals = value if isinstance(value, list) else [x.strip() for x in str(value).split(",")]
        return str(v) in [str(x) for x in vals]
    if op == "contains":
        return str(value).lower() in str(v).lower()
    try:
        a, b = (float(v), float(value)) if isinstance(v, (int, float, Decimal)) else (str(v), str(value))
    except (TypeError, ValueError):
        return False
    return {"eq": a == b, "ne": a != b, "gt": a > b, "gte": a >= b, "lt": a < b, "lte": a <= b}.get(op, False)


def _display(f: F, v):
    if f.type == "choice" and f.choices:
        return f.choices.get(v, v or "")
    if isinstance(v, dt.date):
        return v.strftime("%d/%m/%Y")
    if isinstance(v, bool):
        return "Yes" if v else "No"
    if v is None:
        return ""
    if isinstance(v, Decimal):
        return float(v)
    return v


def run(spec, user, today=None):
    """Execute a definition within the user's data scope. Returns (headers, rows, meta)."""
    spec = validate(spec, user)
    today = today or dt.date.today()
    ds = datasets()[spec["dataset"]]
    model = ds.model()
    qs = scope_queryset(user, model.objects.all(), ds.scope_code, ds.prefix)
    py_filters = []
    for flt in spec["filters"]:
        f = ds.fields[flt["field"]]
        if f.compute is None:
            qs = _orm_filter(qs, f, flt["op"], flt["value"], today)
        else:
            py_filters.append((flt["field"], flt["op"], flt["value"]))

    used = set(spec["columns"]) | set(spec["group_by"]) | {flt["field"] for flt in spec["filters"]}
    used |= {a["field"] for a in spec["aggregates"] if a.get("field")}
    lookups = set()
    for code in used:
        f = ds.fields[code]
        lookups |= set(f.needs) if f.compute else {f.lookup}
    raw = list(qs.values(*sorted(lookups))[:MAX_ROWS + 1])
    truncated = len(raw) > MAX_ROWS
    raw = raw[:MAX_ROWS]

    def value(r, code):
        f = ds.fields[code]
        return f.compute(r, today) if f.compute else r[f.lookup]

    records = []
    for r in raw:
        rec = {c: value(r, c) for c in used}
        if all(_py_match(rec[code], op, val) for code, op, val in py_filters):
            records.append(rec)

    if spec["group_by"]:
        groups = defaultdict(list)
        for rec in records:
            groups[tuple(rec[g] for g in spec["group_by"])].append(rec)
        headers = [ds.fields[g].label for g in spec["group_by"]]
        keys = list(spec["group_by"])
        for a in spec["aggregates"]:
            headers.append("Count" if a["fn"] == "count" else f"{a['fn'].title()} of {ds.fields[a['field']].label}")
            keys.append(_agg_key(a))
        out = []
        for gkey, recs in groups.items():
            row = dict(zip(spec["group_by"], gkey))
            for a in spec["aggregates"]:
                if a["fn"] == "count":
                    row["count"] = len(recs)
                    continue
                vals = [Decimal(str(x[a["field"]])) for x in recs if x[a["field"]] not in (None, "")]
                agg = (sum(vals, Decimal(0)) if a["fn"] == "sum" else
                       (sum(vals, Decimal(0)) / len(vals) if vals else None) if a["fn"] == "avg" else
                       (min(vals) if vals else None) if a["fn"] == "min" else (max(vals) if vals else None))
                row[_agg_key(a)] = round(agg, 2) if agg is not None else None
            out.append(row)
        records = out
    else:
        keys = list(spec["columns"])
        headers = [ds.fields[c].label for c in keys]

    sort = spec["sort"]
    if sort:
        k = sort.lstrip("-")
        records.sort(key=lambda r: (r.get(k) is None, r.get(k) if r.get(k) is not None else 0),
                     reverse=sort.startswith("-"))
    elif spec["group_by"]:
        def natural(g, v):
            order = ds.fields[g].order
            return (order.index(v), "") if v in order else (len(order), str(v or ""))
        records.sort(key=lambda r: tuple(natural(g, r[g]) for g in spec["group_by"]))
    if spec["limit"]:
        records = records[:spec["limit"]]

    def cell(k, v):
        f = ds.fields.get(k)
        return _display(f, v) if f else (float(v) if isinstance(v, Decimal) else v)

    rows = [[cell(k, r.get(k)) for k in keys] for r in records]
    return headers, rows, {"truncated": truncated, "dataset": ds.label, "count": len(rows)}
