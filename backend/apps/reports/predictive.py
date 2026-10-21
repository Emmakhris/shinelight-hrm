"""Attrition-risk indicators, turnover forecast and retirement forecast.

The indicators are deliberately rule-based and transparent, not an opaque model: every factor is shown
with its weight and the evidence behind it, so HR can see why someone is flagged and challenge it.
They exist to prompt retention conversations and are never a basis for decisions about the person.
Individual scores need `analytics.predictive`, are never shown to the employee (nor to anyone about
themselves), and each view is audit-logged. Weights can be tuned per organization through
`organization.settings["attrition_weights"]`.
"""

import datetime as dt
import math
from collections import Counter, defaultdict
from decimal import Decimal as D

from django.db.models import Q

from apps.employees.models import ACTIVE_STATUSES, Employee, EmploymentRecord
from apps.rbac.services import has_perm, scope_queryset

DEFAULT_WEIGHTS = {
    "manager_flag": 20,
    "early_tenure": 15,
    "stagnation": 15,
    "pay_below_range": 15,
    "contract_ending": 15,
    "low_rating": 10,
    "absence_rise": 10,
    "department_turnover": 10,
}
FACTOR_LABELS = {
    "manager_flag": "Manager assessed flight risk at the last talent review",
    "early_tenure": "In the first year of service",
    "stagnation": "Four or more years in the same role",
    "pay_below_range": "Pay still below 90% of the grade midpoint after 3+ years in role",
    "contract_ending": "Contract ends within 120 days",
    "low_rating": "Latest appraisal rating is 2 or below",
    "absence_rise": "Sick leave in the last 90 days is at least double the previous 90",
    "department_turnover": "Department turnover is 1.5x the organization rate or more",
}
HIGH, MEDIUM = 45, 25
SMOOTHING = 10          # pseudo-headcount pulling small departments towards the organization rate


def weights(org=None):
    w = dict(DEFAULT_WEIGHTS)
    if org is not None:
        for k, v in (org.settings or {}).get("attrition_weights", {}).items():
            if k in w:
                w[k] = int(v)
    return w


def band(score):
    return "high" if score >= HIGH else "medium" if score >= MEDIUM else "low"


def score_factors(facts, w):
    """Pure scoring: facts is {factor: detail or None}. Returns (score, [factor dicts])."""
    hits = [{"code": k, "label": FACTOR_LABELS[k], "weight": w[k], "detail": d}
            for k, d in facts.items() if d and w.get(k)]
    hits.sort(key=lambda h: -h["weight"])
    return min(100, sum(h["weight"] for h in hits)), hits


# ---------------------------------------------------------------- shared inputs
def _turnover_by_department(today):
    """Trailing 12-month exits and average headcount per department (whole organization)."""
    year_ago = today - dt.timedelta(days=365)
    exits = Counter(Employee.objects.filter(exit_date__range=(year_ago, today))
                    .values_list("department_id", flat=True))
    now = Counter(Employee.objects.filter(status__in=ACTIVE_STATUSES).values_list("department_id", flat=True))
    then = Counter(Employee.objects.filter(hire_date__lte=year_ago)
                   .filter(Q(exit_date__isnull=True) | Q(exit_date__gt=year_ago))
                   .values_list("department_id", flat=True))
    depts = set(exits) | set(now) | set(then)
    total_exits, total_avg = sum(exits.values()), (sum(now.values()) + sum(then.values())) / 2
    org_rate = total_exits / total_avg if total_avg else 0.0
    out = {}
    for d in depts:
        avg = (now[d] + then[d]) / 2
        out[d] = {"exits": exits[d], "avg_headcount": avg, "raw_rate": exits[d] / avg if avg else 0.0,
                  "rate": (exits[d] + SMOOTHING * org_rate) / (avg + SMOOTHING)}
    return out, org_rate


def _retirement_date(e, retirement_age):
    if e.retirement_date:
        return e.retirement_date, False
    if e.date_of_birth:
        dob = e.date_of_birth
        try:
            return dob.replace(year=dob.year + retirement_age), True
        except ValueError:          # 29 February
            return dob.replace(year=dob.year + retirement_age, day=28), True
    return None, False


def _retirement_age(org):
    from apps.employees.services import RETIREMENT_AGE

    return int((org.settings or {}).get("retirement_age", RETIREMENT_AGE)) if org else RETIREMENT_AGE


def _leaving_ids():
    from apps.offboarding.models import Separation

    return set(Separation.objects.filter(status__in=["pending", "returned", "clearance"])
               .values_list("employee_id", flat=True))


# ---------------------------------------------------------------- individual indicators
def risk_scores(user, today=None, department=None):
    """Attrition-risk indicators for active staff in the user's `analytics.predictive` scope."""
    from apps.leave.models import LeaveRequest
    from apps.performance.models import Appraisal
    from apps.talent.models import TalentAssessment

    today = today or dt.date.today()
    org = getattr(user, "organization", None)
    w = weights(org)
    qs = scope_queryset(user, Employee.objects.filter(status__in=ACTIVE_STATUSES), "analytics.predictive")
    me = getattr(user, "employee", None)
    if me is not None:
        qs = qs.exclude(pk=me.pk)
    if department:
        qs = qs.filter(department_id=department)
    people = list(qs.select_related("department", "job_title", "grade"))
    ids = [e.id for e in people]
    leaving = _leaving_ids()
    turnover, org_rate = _turnover_by_department(today)

    ratings = {}
    for emp_id, rating in (Appraisal.objects.filter(employee_id__in=ids, final_rating__isnull=False,
                                                    status__in=["acknowledgement", "completed"])
                           .order_by("employee_id", "cycle__period_end").values_list("employee_id", "final_rating")):
        ratings[emp_id] = rating                                # last one wins
    flags = {}
    for emp_id, risk, period in (TalentAssessment.objects.filter(employee_id__in=ids)
                                 .order_by("employee_id", "created_at")
                                 .values_list("employee_id", "flight_risk", "period")):
        flags[emp_id] = (risk, period)
    role_since = {}
    for emp_id, jt, frm in (EmploymentRecord.objects.filter(employee_id__in=ids, effective_from__lte=today)
                            .order_by("employee_id", "-effective_from", "-id")
                            .values_list("employee_id", "job_title_id", "effective_from")):
        role_since.setdefault(emp_id, []).append((jt, frm))
    sick = defaultdict(lambda: [D(0), D(0)])
    d90, d180 = today - dt.timedelta(days=90), today - dt.timedelta(days=180)
    for emp_id, start, days in (LeaveRequest.objects.filter(employee_id__in=ids, leave_type__code="sick",
                                                            status="approved", start_date__gte=d180,
                                                            start_date__lte=today)
                                .values_list("employee_id", "start_date", "days")):
        sick[emp_id][0 if start >= d90 else 1] += days or 0

    rows = []
    for e in people:
        if e.id in leaving:
            continue
        start = e.original_hire_date or e.hire_date
        tenure = (today - start).days / 365.25
        since = e.hire_date
        for jt, frm in role_since.get(e.id, []):
            if jt != e.job_title_id:
                break
            since = frm
        in_role = (today - since).days / 365.25
        facts = {
            "early_tenure": f"{tenure:.1f} years' service" if 0 <= tenure < 1 else None,
            "stagnation": f"{in_role:.1f} years as {e.job_title.name}" if e.job_title_id and in_role >= 4 else None,
            "low_rating": f"Rating {ratings[e.id]}" if ratings.get(e.id) is not None and ratings[e.id] <= 2 else None,
            "contract_ending": (f"Contract ends {e.contract_end_date:%d/%m/%Y}"
                                if e.contract_end_date and today <= e.contract_end_date <= today
                                + dt.timedelta(days=120) else None),
        }
        if e.grade_id and e.grade.max_salary and e.basic_salary and in_role >= 3:
            mid = (e.grade.min_salary + e.grade.max_salary) / 2
            compa = e.basic_salary / mid if mid else None
            facts["pay_below_range"] = f"{compa:.0%} of grade midpoint" if compa and compa < D("0.9") else None
        recent, prior = sick[e.id]
        facts["absence_rise"] = (f"{recent:g} sick days vs {prior:g} before"
                                 if recent >= 3 and recent >= 2 * prior else None)
        fr = flags.get(e.id)
        if fr and fr[0] in ("high", "medium"):
            facts["manager_flag"] = f"{fr[0].title()} ({fr[1]})"
        dept = turnover.get(e.department_id)
        if dept and org_rate and dept["raw_rate"] >= 1.5 * org_rate and dept["exits"] >= 2:
            facts["department_turnover"] = f"{dept['raw_rate']:.0%} vs {org_rate:.0%}"
        score, hits = score_factors(facts, w)
        if fr and fr[0] == "medium":
            for h in hits:
                if h["code"] == "manager_flag":
                    h["weight"] = w["manager_flag"] // 2
            score = min(100, sum(h["weight"] for h in hits))
        rows.append({"employee": e.id, "staff_number": e.staff_number, "name": e.full_name,
                     "department": e.department.name if e.department_id else "",
                     "job_title": e.job_title.name if e.job_title_id else "",
                     "score": score, "band": band(score), "factors": hits})
    rows.sort(key=lambda r: (-r["score"], r["name"]))
    return rows


# ---------------------------------------------------------------- aggregate forecasts
def turnover_forecast(user, today=None):
    """Expected leavers over the next 12 months, by department, plus a monthly headcount projection."""
    today = today or dt.date.today()
    org = getattr(user, "organization", None)
    age = _retirement_age(org)
    turnover, org_rate = _turnover_by_department(today)
    active = scope_queryset(user, Employee.objects.filter(status__in=ACTIVE_STATUSES), "employees.view")
    people = list(active.select_related("department").only("id", "department__name", "department_id",
                                                           "retirement_date", "date_of_birth"))
    horizon = today + dt.timedelta(days=365)
    bands = {}
    if has_perm(user, "analytics.predictive"):
        for r in risk_scores(user, today):
            bands.setdefault(r["department"], Counter())[r["band"]] += 1
    by_dept = defaultdict(lambda: {"headcount": 0, "retirements": 0, "id": None})
    retire_months = Counter()
    for e in people:
        name = e.department.name if e.department_id else "Unassigned"
        row = by_dept[name]
        row["headcount"] += 1
        row["id"] = e.department_id
        rd, _ = _retirement_date(e, age)
        if rd and today <= rd < horizon:
            row["retirements"] += 1
            retire_months[(rd.year, rd.month)] += 1
    depts, total_expected = [], 0.0
    for name, row in sorted(by_dept.items()):
        t = turnover.get(row["id"], {"rate": org_rate, "raw_rate": 0.0, "exits": 0})
        expected = max(0, row["headcount"] - row["retirements"]) * t["rate"]
        total_expected += expected
        out = {"department": name, "headcount": row["headcount"], "exits_12m": t["exits"],
               "turnover_percent": round(100 * t["raw_rate"], 1),
               "forecast_rate_percent": round(100 * t["rate"], 1),
               "expected_leavers": round(expected, 1), "retirements_12m": row["retirements"]}
        b = bands.get(name)
        if b is not None:                                   # only for viewers allowed individual indicators
            out.update({"risk_high": b["high"], "risk_medium": b["medium"]})
        depts.append(out)
    half = 1.28 * math.sqrt(total_expected) if total_expected else 0
    future_hires = Counter((h.year, h.month) for h in scope_queryset(
        user, Employee.objects.filter(hire_date__gt=today, hire_date__lte=horizon), "employees.view")
        .values_list("hire_date", flat=True))
    headcount = len(people)
    monthly, hc, ref = [], float(headcount), today.replace(day=1)
    for _ in range(12):
        ref = (ref.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
        key = (ref.year, ref.month)
        hc = hc - total_expected / 12 - retire_months[key] + future_hires[key]
        monthly.append({"month": ref.strftime("%b %Y"), "headcount": round(hc, 1),
                        "retirements": retire_months[key], "starters": future_hires[key]})
    return {
        "as_of": today, "headcount": headcount,
        "org_turnover_percent": round(100 * org_rate, 1),
        "expected_leavers": round(total_expected, 1),
        "range": [max(0, round(total_expected - half)), round(total_expected + half)],
        "retirements_12m": sum(d["retirements_12m"] for d in depts),
        "departments": sorted(depts, key=lambda d: -d["expected_leavers"]),
        "monthly": monthly,
        "method": ("Each department's trailing 12-month turnover, smoothed towards the organization rate for small "
                   f"departments ({SMOOTHING} pseudo-staff), applied to staff not due to retire. The range is an "
                   "80% interval. Known retirements and future start dates are added month by month."),
    }


def retirement_forecast(user, years=5, today=None):
    """Retirements per year by department and job title, and critical posts losing their incumbent."""
    from apps.organization.models import Position
    from apps.talent.models import SuccessionPlan

    today = today or dt.date.today()
    org = getattr(user, "organization", None)
    age = _retirement_age(org)
    active = scope_queryset(user, Employee.objects.filter(status__in=ACTIVE_STATUSES), "employees.view")
    end = dt.date(today.year + years, 1, 1)
    by_year, by_dept, by_title = Counter(), defaultdict(Counter), Counter()
    estimated, retiring = 0, {}
    for e in active.select_related("department", "job_title", "position"):
        rd, est = _retirement_date(e, age)
        if not rd or not today <= rd < end:
            continue
        estimated += est
        by_year[rd.year] += 1
        by_dept[e.department.name if e.department_id else "Unassigned"][rd.year] += 1
        by_title[e.job_title.name if e.job_title_id else "Unassigned"] += 1
        if e.position_id:
            retiring[e.position_id] = (e, rd)
    yrs = list(range(today.year, today.year + years))
    critical = []
    for plan in SuccessionPlan.objects.filter(position_id__in=retiring).select_related(
            "position__job_title", "position__department").prefetch_related("successors"):
        e, rd = retiring[plan.position_id]
        ready = [s for s in plan.successors.all() if s.readiness == "ready_now"]
        critical.append({"position": str(plan.position), "incumbent": e.full_name if has_perm(
            user, "talent.view") else None, "retirement_date": rd, "successors": plan.successors.count(),
            "ready_now": len(ready), "covered": bool(ready)})
    uncovered_critical = []
    for pos in Position.objects.filter(pk__in=retiring, is_critical=True).exclude(
            pk__in=SuccessionPlan.objects.values_list("position_id", flat=True)):
        e, rd = retiring[pos.id]
        uncovered_critical.append({"position": str(pos), "incumbent": e.full_name if has_perm(
            user, "talent.view") else None, "retirement_date": rd, "successors": 0, "ready_now": 0,
            "covered": False})
    return {
        "years": yrs,
        "by_year": [{"label": str(y), "value": by_year[y]} for y in yrs],
        "by_department": [{"department": d, **{str(y): c[y] for y in yrs}, "total": sum(c.values())}
                          for d, c in sorted(by_dept.items(), key=lambda kv: -sum(kv[1].values()))],
        "by_job_title": [{"label": t, "value": n} for t, n in by_title.most_common(10)],
        "critical_positions": sorted(critical + uncovered_critical, key=lambda r: r["retirement_date"]),
        "estimated_dates": estimated,
        "retirement_age": age,
    }
