"""Tools the assistant may call. Each runs as the signed-in user and applies the same permission and data-scope
checks as the rest of the system: the model never touches the database directly and only ever sees what the
user could already see on screen. Tools only read; nothing here changes a record.

Two governance modes (organization setting):
- "policies": only approved knowledge-base articles. No personal data leaves the server.
- "hr_data": also the user's own records and aggregate reports within their access.
"""

import datetime as dt
import json
import re
from collections import Counter

from apps.rbac.services import has_perm, scope_queryset

POLICY_ONLY = {"search_policies"}


def _obj(properties, required=()):
    return {"type": "object", "properties": properties, "required": list(required), "additionalProperties": False}


DEFINITIONS = [
    {"name": "search_policies",
     "description": "Search the organization's approved HR policies and knowledge-base articles. Use this for any "
                    "question about rules, entitlements or procedures, and answer only from what it returns.",
     "input_schema": _obj({"query": {"type": "string", "description": "Keywords, e.g. 'maternity leave days'."}},
                          ["query"])},
    {"name": "my_profile",
     "description": "The user's own job details: job title, department, grade, supervisor, hire date, "
                    "employment type, probation and contract end dates.",
     "input_schema": _obj({})},
    {"name": "my_leave_balances",
     "description": "The user's own leave balances for the current year by leave type.",
     "input_schema": _obj({})},
    {"name": "my_latest_payslip",
     "description": "Summary of the user's own most recent published payslip (gross, deductions, net).",
     "input_schema": _obj({})},
    {"name": "my_pending_requests",
     "description": "The user's own requests still awaiting approval, and who they are waiting on.",
     "input_schema": _obj({})},
    {"name": "headcount",
     "description": "Aggregate active headcount within the user's reporting access, grouped by a dimension. "
                    "Only for users with HR reporting access.",
     "input_schema": _obj({"group_by": {"type": "string", "enum": ["department", "gender", "employment_type",
                                                                   "grade", "branch"]}}, ["group_by"])},
    {"name": "team_on_leave",
     "description": "Who in the user's team or department is on approved leave on a date (default today). "
                    "Only for managers and HR.",
     "input_schema": _obj({"date": {"type": "string", "description": "YYYY-MM-DD; omit for today."}})},
]


def available(user, mode):
    """Tool definitions this user may use under the organization's mode."""
    names = POLICY_ONLY if mode == "policies" else {d["name"] for d in DEFINITIONS}
    out = []
    for d in DEFINITIONS:
        if d["name"] not in names:
            continue
        if d["name"].startswith("my_") and getattr(user, "employee", None) is None:
            continue
        if d["name"] == "headcount" and not has_perm(user, "reports.view"):
            continue
        if d["name"] == "team_on_leave" and not (has_perm(user, "leave.view", "team")):
            continue
        out.append({**d, "strict": True})
    return out


def run(name, args, user, mode):
    """Execute a tool. Returns (result_dict, sources). Raises PermissionError when not allowed."""
    if name not in {d["name"] for d in available(user, mode)}:
        raise PermissionError(f"Tool {name} is not available to you.")
    return globals()[f"_{name}"](user, args or {})


# ---------------------------------------------------------------- implementations
WORD = re.compile(r"[a-z0-9]{3,}")


def _search_policies(user, args):
    from apps.servicedesk.models import KnowledgeArticle

    terms = set(WORD.findall(str(args.get("query", "")).lower()))
    scored = []
    for a in KnowledgeArticle.objects.filter(is_published=True).only("id", "title", "body", "tags"):
        title, body, tags = a.title.lower(), a.body.lower(), (a.tags or "").lower()
        score = sum(3 * (t in title) + 2 * (t in tags) + (t in body) for t in terms)
        if score:
            scored.append((score, a))
    scored.sort(key=lambda s: -s[0])
    hits = [{"article_id": a.id, "title": a.title, "text": a.body[:3000]} for _, a in scored[:4]]
    sources = [{"title": h["title"], "link": f"/helpdesk/kb?article={h['article_id']}"} for h in hits]
    return {"results": hits, "note": "No matching approved article." if not hits else ""}, sources


def _my_profile(user, args):
    e = user.employee
    return {"name": e.full_name, "job_title": e.job_title.name if e.job_title_id else None,
            "department": e.department.name if e.department_id else None,
            "grade": e.grade.code if e.grade_id else None,
            "supervisor": e.supervisor.full_name if e.supervisor_id else None,
            "employment_type": e.employment_type, "status": e.get_status_display(),
            "hire_date": str(e.hire_date), "probation_end_date": str(e.probation_end_date or "") or None,
            "contract_end_date": str(e.contract_end_date or "") or None}, [{"title": "My profile", "link": "/me/profile"}]


def _my_leave_balances(user, args):
    from apps.leave.services import all_balances

    rows = [{"leave_type": b["leave_type_name"], "available_days": float(b["available"]),
             "taken_days": float(b["taken"]), "pending_days": float(b["pending"]),
             "tracks_balance": b["tracks_balance"]} for b in all_balances(user.employee)]
    return {"year": dt.date.today().year, "balances": rows}, [{"title": "My leave", "link": "/leave/my"}]


def _my_latest_payslip(user, args):
    from apps.payroll.models import Payslip

    p = (Payslip.objects.filter(employee=user.employee, published_at__isnull=False)
         .exclude(run__run_type="reversal").select_related("run__period").order_by("-run__period__start_date").first())
    if p is None:
        return {"payslip": None, "note": "No published payslip yet."}, []
    return {"period": p.run.period.name, "gross_pay": str(p.gross_pay), "paye": str(p.paye),
            "ssnit_employee": str(p.ssnit_employee), "total_deductions": str(p.total_deductions),
            "net_pay": str(p.net_pay), "currency": "GHS"}, [{"title": f"Payslip {p.run.period.name}",
                                                             "link": "/me/payslips"}]


def _my_pending_requests(user, args):
    from apps.workflow.models import WorkflowInstance, WorkflowTask

    out = []
    for inst in WorkflowInstance.objects.filter(initiator=user, status="in_progress").order_by("-created_at")[:10]:
        waiting = [t.assignee.get_full_name() or t.assignee.username for t in
                   WorkflowTask.objects.filter(instance=inst, status="pending").select_related("assignee")]
        out.append({"request": inst.title, "submitted": str(inst.created_at.date()), "waiting_on": waiting})
    return {"pending": out}, [{"title": "My requests", "link": "/me/requests"}]


def _headcount(user, args):
    from apps.employees.models import ACTIVE_STATUSES, Employee

    field = {"department": "department__name", "gender": "gender", "employment_type": "employment_type",
             "grade": "grade__code", "branch": "branch__name"}[args["group_by"]]
    qs = scope_queryset(user, Employee.objects.filter(status__in=ACTIVE_STATUSES), "employees.view")
    counts = Counter(v or "Unassigned" for v in qs.values_list(field, flat=True))
    return {"group_by": args["group_by"], "total": sum(counts.values()),
            "rows": [{"group": k, "headcount": n} for k, n in counts.most_common()]}, \
        [{"title": "HR dashboard", "link": "/dashboard"}]


def _team_on_leave(user, args):
    from apps.leave.services import on_leave_on

    try:
        day = dt.date.fromisoformat(args["date"]) if args.get("date") else dt.date.today()
    except ValueError:
        day = dt.date.today()
    reqs = scope_queryset(user, on_leave_on(day), "leave.view", "employee__").select_related("employee", "leave_type")
    return {"date": str(day), "on_leave": [{"name": r.employee.full_name, "leave_type": r.leave_type.name,
                                            "until": str(r.end_date)} for r in reqs[:50]]}, \
        [{"title": "Team calendar", "link": "/leave/calendar"}]


def as_json(result):
    return json.dumps(result, default=str)
