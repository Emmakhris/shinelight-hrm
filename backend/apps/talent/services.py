"""Talent, succession and workforce planning (features.txt §13-14).

Principles: succession decisions stay with people. The system suggests a performance level from the latest
appraisal and shows the documented potential criteria, but never labels anyone a future leader on its own.
Projections are pure arithmetic over current data and stated assumptions (`project`)."""

import datetime as dt
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from apps.core.exceptions import BusinessRuleError
from apps.employees.models import ACTIVE_STATUSES, Employee, EmploymentRecord
from apps.rbac.services import can_access_employee, has_perm

from .models import POTENTIAL_CRITERIA, CareerPath, SuccessionPlan, Successor, TalentAssessment

D = Decimal
HIGH_POTENTIAL_MIN_CRITERIA = 3
RETIREMENT_RISK_YEARS = 2


def q2(x):
    return D(x).quantize(D("0.01"), rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------- talent assessments (nine-box)
def suggested_performance(employee):
    from apps.performance.services import latest_rating

    r = latest_rating(employee)
    if r is None:
        return None
    return 1 if r <= 2 else 2 if r == 3 else 3


def can_assess(user, employee):
    if employee.user_id == user.pk:
        return False
    sup = employee.supervisor
    return bool(sup and sup.user_id == user.pk) or can_access_employee(user, "talent.manage", employee)


def assess(user, employee, period, performance, potential, criteria, rationale, flight_risk="low"):
    if not can_assess(user, employee):
        raise PermissionDenied("Only the employee's supervisor or the talent team can assess.")
    performance, potential = int(performance), int(potential)
    if performance not in (1, 2, 3) or potential not in (1, 2, 3):
        raise BusinessRuleError("Performance and potential are 1 (low) to 3 (high).")
    if not rationale:
        raise BusinessRuleError("Explain the placement; assessments must be transparent.")
    keys = dict(POTENTIAL_CRITERIA)
    clean = {}
    for k, v in (criteria or {}).items():
        if k not in keys:
            continue
        met = bool(v.get("met"))
        if met and not (v.get("evidence") or "").strip():
            raise BusinessRuleError(f"Give evidence for '{keys[k]}'.")
        clean[k] = {"met": met, "evidence": (v.get("evidence") or "").strip()}
    met = sum(1 for v in clean.values() if v["met"])
    if potential == 3 and met < HIGH_POTENTIAL_MIN_CRITERIA:
        raise BusinessRuleError(f"High potential needs at least {HIGH_POTENTIAL_MIN_CRITERIA} criteria met with "
                                "evidence.")
    if potential == 2 and met < 1:
        raise BusinessRuleError("Moderate potential needs at least one criterion met with evidence.")
    obj, _ = TalentAssessment.objects.update_or_create(
        employee=employee, period=period,
        defaults={"performance": performance, "potential": potential, "criteria": clean, "rationale": rationale,
                  "flight_risk": flight_risk, "assessed_by": user, "calibrated": False})
    return obj


BOX_LABELS = {1: "Low performance / low potential", 2: "Low performance / moderate potential",
              3: "Low performance / high potential (enigma)", 4: "Solid performance / low potential",
              5: "Core player", 6: "Solid performance / high potential", 7: "High performance / low potential "
              "(trusted professional)", 8: "High performance / moderate potential", 9: "Top talent"}


def nine_box(period, assessments):
    grid = {b: [] for b in range(1, 10)}
    for a in assessments.filter(period=period).select_related("employee__department", "employee__job_title"):
        grid[a.box].append({"assessment": a.id, "employee": a.employee_id, "name": a.employee.full_name,
                            "job_title": a.employee.job_title.name if a.employee.job_title_id else None,
                            "department": a.employee.department.name if a.employee.department_id else None,
                            "flight_risk": a.flight_risk})
    return [{"box": b, "label": BOX_LABELS[b], "people": grid[b], "count": len(grid[b])} for b in range(1, 10)]


# ---------------------------------------------------------------- succession
def add_successor(user, plan: SuccessionPlan, employee, readiness, actions="", rank=1):
    if not has_perm(user, "talent.manage"):
        raise PermissionDenied()
    if employee.status not in ACTIVE_STATUSES:
        raise BusinessRuleError("Successors must be current employees.")
    if employee.position_id == plan.position_id:
        raise BusinessRuleError("The incumbent cannot be their own successor.")
    if readiness not in dict(Successor.READINESS):
        raise BusinessRuleError("Choose a readiness level.")
    s, _ = Successor.objects.update_or_create(plan=plan, employee=employee, defaults={
        "readiness": readiness, "development_actions": actions, "rank": rank})
    plan.last_reviewed = dt.date.today()
    plan.save(update_fields=["last_reviewed", "updated_at"])
    return s


def succession_risk(today=None):
    """Critical positions with their cover and the risks the system can see (no judgement on people)."""
    from apps.organization.models import Position

    today = today or dt.date.today()
    horizon = today + dt.timedelta(days=int(365.25 * RETIREMENT_RISK_YEARS))
    rows = []
    for p in Position.objects.filter(is_critical=True, status="approved").select_related("job_title", "department"):
        incumbents = list(p.employees.filter(status__in=ACTIVE_STATUSES))
        plan = getattr(p, "succession_plan", None)
        successors = list(plan.successors.select_related("employee")) if plan else []
        ready_now = [s for s in successors if s.readiness == "ready_now"]
        flags = []
        if not incumbents:
            flags.append("Vacant critical position")
        if not successors:
            flags.append("No successor identified")
        elif not ready_now:
            flags.append("No ready-now successor")
        if p.headcount == 1 and incumbents and not ready_now:
            flags.append("Single-person dependency")
        retiring = [e for e in incumbents if e.retirement_date and e.retirement_date <= horizon]
        if retiring:
            flags.append(f"Incumbent retires {retiring[0].retirement_date:%d/%m/%Y}")
        if plan and plan.risk_of_loss == "high":
            flags.append("High risk of loss")
        rows.append({
            "position": p.id, "code": p.code, "title": p.job_title.name, "department": p.department.name,
            "incumbents": [{"id": e.id, "name": e.full_name, "retirement_date": e.retirement_date} for e in incumbents],
            "plan": plan.id if plan else None,
            "successors": [{"id": s.id, "employee": s.employee_id, "name": s.employee.full_name,
                            "readiness": s.readiness, "readiness_label": s.get_readiness_display()} for s in successors],
            "flags": flags, "risk": "high" if len(flags) >= 2 else "medium" if flags else "low"})
    total = len(rows)
    covered = sum(1 for r in rows if any(s["readiness"] == "ready_now" for s in r["successors"]))
    return {"positions": rows, "critical_positions": total,
            "bench_strength_percent": round(100 * covered / total) if total else None,
            "single_person_dependencies": sum(1 for r in rows if "Single-person dependency" in r["flags"]),
            "retirement_risks": sum(1 for r in rows if any(f.startswith("Incumbent retires") for f in r["flags"]))}


# ---------------------------------------------------------------- career paths & promotion eligibility
def years_in_role(employee, today=None):
    today = today or dt.date.today()
    recs = list(EmploymentRecord.objects.filter(employee=employee, effective_from__lte=today)
                .order_by("-effective_from", "-id").values_list("job_title_id", "effective_from"))
    since = employee.hire_date
    for jt, frm in recs:
        if jt != employee.job_title_id:
            break
        since = frm
    return round((today - since).days / 365.25, 1)


def promotion_eligibility(employee, today=None):
    from apps.learning.services import course_status
    from apps.performance.services import latest_rating

    if not employee.job_title_id:
        return []
    yrs = years_in_role(employee, today)
    rating = latest_rating(employee)
    out = []
    for path in CareerPath.objects.filter(from_title=employee.job_title).select_related("to_title") \
            .prefetch_related("required_courses"):
        gaps = []
        if yrs < path.min_years_in_role:
            gaps.append(f"{path.min_years_in_role:g} years in role needed ({yrs:g} so far)")
        if rating is None or rating < path.min_rating:
            gaps.append(f"Latest rating {path.min_rating}+ needed ({rating if rating is not None else 'none'})")
        for c in path.required_courses.all():
            if course_status(employee, c)[0] not in ("current", "expiring"):
                gaps.append(f"Course: {c.title}")
        out.append({"path": path.id, "to": path.to_title.name, "eligible": not gaps, "gaps": gaps,
                    "years_in_role": yrs, "rating": rating,
                    "qualification_to_verify": path.required_qualification})
    return out


# ---------------------------------------------------------------- workforce planning
def employer_on_cost_rate(on_date=None):
    """Employer statutory on-cost (SSNIT employer %) from the effective-dated rate table - never hard-coded."""
    from apps.payroll.services import rate_set_for

    try:
        return D(rate_set_for(on_date or dt.date.today()).ssnit_employer_rate) / 100
    except Exception:
        return D("0")


def project(lines, years, attrition, salary_increase, growth, on_cost, dept_adjust=None, freeze=False,
            budget_cap=None):
    """Pure projection. lines: [{"key", "department_id", "label", "current", "planned", "avg_monthly",
    "retirements": {year_index: n}}]. Rates are fractions (0.1 = 10%). Returns per-year totals and lines."""
    dept_adjust = dept_adjust or {}
    budget_cap = budget_cap or D("0")
    out_years, out_lines = [], []
    state = {ln["key"]: D(ln["current"]) for ln in lines}
    for y in range(1, years + 1):
        tot = defaultdict(D)
        for ln in lines:
            start = state[ln["key"]]
            retire = D(ln.get("retirements", {}).get(y, 0))
            leavers = (start - retire) * attrition if start > retire else D(0)
            adj = D(1) + D(str(dept_adjust.get(str(ln["department_id"]), 0))) / 100
            target = (D(ln["planned"]) * (D(1) + growth) ** y * adj).quantize(D("1"), rounding=ROUND_HALF_UP)
            supply = start - retire - leavers
            hires = D(0) if freeze else max(D(0), target - supply)
            end = supply + hires
            cost = end * D(ln["avg_monthly"]) * 12 * (D(1) + salary_increase) ** y * (D(1) + on_cost)
            state[ln["key"]] = end
            row = {"year": y, "key": ln["key"], "label": ln["label"], "start": float(round(start, 1)),
                   "retirements": float(retire), "attrition": float(round(leavers, 1)), "target": float(target),
                   "hires": float(round(hires, 1)), "end": float(round(end, 1)), "gap": float(round(target - end, 1)),
                   "cost": q2(cost)}
            out_lines.append(row)
            for k in ("start", "retirements", "attrition", "target", "hires", "end"):
                tot[k] += D(str(row[k]))
            tot["cost"] += row["cost"]
        out_years.append({"year": y, **{k: float(round(v, 1)) for k, v in tot.items() if k != "cost"},
                          "cost": q2(tot["cost"]), "over_budget": bool(budget_cap and tot["cost"] > budget_cap)})
    return {"years": out_years, "lines": out_lines}


def actual_turnover_rate():
    try:
        from apps.offboarding.services import analytics

        return D(str(analytics(12)["turnover_percent"])) / 100
    except Exception:
        return D("0.08")


def _line_population(line):
    qs = Employee.objects.filter(status__in=ACTIVE_STATUSES)
    from apps.rbac.services import department_descendants

    qs = qs.filter(department_id__in=department_descendants(line.department_id))
    if line.job_title_id:
        qs = qs.filter(job_title_id=line.job_title_id)
    if line.employment_type:
        qs = qs.filter(employment_type=line.employment_type)
    return qs


def plan_inputs(plan, horizon=None):
    years = horizon or plan.horizon_years
    base = dt.date(plan.year, 1, 1)
    out = []
    for ln in plan.lines.select_related("department", "job_title"):
        people = list(_line_population(ln).only("basic_salary", "retirement_date"))
        n = len(people)
        avg = (sum((p.basic_salary for p in people), D(0)) / n) if n else D(0)
        retire = defaultdict(int)
        for p in people:
            if p.retirement_date:
                yi = p.retirement_date.year - base.year + 1
                if 1 <= yi <= years:
                    retire[yi] += 1
        if avg == 0 and ln.job_title_id and ln.job_title.default_grade_id:
            g = ln.job_title.default_grade
            avg = (g.min_salary + g.max_salary) / 2 if g.max_salary else D(0)
        out.append({"key": ln.id, "department_id": ln.department_id,
                    "label": f"{ln.department.name}{' - ' + ln.job_title.name if ln.job_title_id else ''}",
                    "current": n, "planned": ln.planned_headcount, "avg_monthly": q2(avg), "retirements": dict(retire),
                    "workload_units": ln.workload_units, "workload_label": ln.workload_label,
                    "target_ratio": ln.target_ratio})
    return out


def run_scenario(plan, scenario=None):
    inputs = plan_inputs(plan)
    s = scenario
    attrition = (D(s.attrition_percent) / 100) if s and s.attrition_percent is not None else actual_turnover_rate()
    res = project(inputs, plan.horizon_years, attrition, D(s.salary_increase_percent) / 100 if s else D(0),
                  D(s.growth_percent) / 100 if s else D(0), employer_on_cost_rate(), s.department_adjustments if s else {},
                  bool(s and s.hiring_freeze), D(s.budget_cap) if s else D(0))
    workload = []
    for ln in inputs:
        if ln["workload_units"] and ln["target_ratio"]:
            needed = (D(ln["workload_units"]) * D(ln["target_ratio"])).quantize(D("1"), rounding=ROUND_HALF_UP)
            workload.append({"label": ln["label"], "units": float(ln["workload_units"]),
                             "unit_label": ln["workload_label"], "needed": float(needed), "current": ln["current"],
                             "ratio": round(ln["current"] / float(ln["workload_units"]), 2),
                             "shortfall": float(needed - ln["current"])})
    return {"plan": plan.name, "scenario": s.name if s else "Baseline", "attrition_percent": float(attrition * 100),
            "on_cost_percent": float(employer_on_cost_rate() * 100), "inputs": [
                {k: (float(v) if isinstance(v, Decimal) else v) for k, v in ln.items() if k != "retirements"}
                for ln in inputs], **res, "workload": workload}


def establishment_summary():
    """Approved vs occupied positions and budget vs actual cost by department."""
    from apps.organization.models import Position

    rows = {}
    for p in Position.objects.filter(status__in=["approved", "frozen", "proposed"]).select_related("department"):
        r = rows.setdefault(p.department_id, {"department": p.department.name, "approved": 0, "occupied": 0,
                                              "vacant": 0, "frozen": 0, "proposed": 0, "budget": D(0), "actual": D(0)})
        if p.status != "approved":
            r[p.status] += p.headcount
            continue
        occ = list(p.employees.filter(status__in=ACTIVE_STATUSES).only("basic_salary"))
        r["approved"] += p.headcount
        r["occupied"] += min(len(occ), p.headcount)
        r["vacant"] += max(p.headcount - len(occ), 0)
        r["budget"] += p.budgeted_annual_cost
        r["actual"] += sum((e.basic_salary for e in occ), D(0)) * 12
    out = []
    for r in sorted(rows.values(), key=lambda x: x["department"]):
        r["variance"] = r["budget"] - r["actual"]
        out.append({k: (float(v) if isinstance(v, Decimal) else v) for k, v in r.items()})
    by_type = defaultdict(int)
    for t in Employee.objects.filter(status__in=ACTIVE_STATUSES).values_list("employment_type", flat=True):
        by_type[t] += 1
    return {"departments": out, "by_employment_type": dict(by_type)}


def skills_shortages():
    from apps.learning.services import training_needs

    risk = succession_risk()
    needs = training_needs()
    return {"critical_roles_without_cover": [r for r in risk["positions"] if "No successor identified" in r["flags"]
                                             or "No ready-now successor" in r["flags"]],
            "competency_gaps": needs["competency_gaps"][:10]}


def touch_profile(profile):
    profile.updated_by_employee_at = timezone.now()
    profile.save(update_fields=["updated_by_employee_at", "updated_at"])

