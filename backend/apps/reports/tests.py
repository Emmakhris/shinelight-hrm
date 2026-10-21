import datetime as dt
from decimal import Decimal as D

import pytest
from rest_framework.test import APIClient

from apps.core.exceptions import BusinessRuleError


@pytest.fixture
def people(org, make_employee, make_user, structure):
    today = dt.date.today()
    boss = make_employee(first="Kojo", hire_date=dt.date(2010, 1, 1))
    a = make_employee(first="Ama", supervisor=boss, hire_date=today - dt.timedelta(days=100),
                      contract_end_date=today + dt.timedelta(days=60), date_of_birth=dt.date(1998, 5, 1))
    b = make_employee(first="Esi", supervisor=boss, date_of_birth=dt.date(1967, 3, 1),
                      retirement_date=today + dt.timedelta(days=200))
    fin = make_employee(first="Yaw", position=structure["pos_fin"], basic_salary=D("7000"))
    return {"boss": boss, "a": a, "b": b, "fin": fin,
            "u_boss": make_user("boss", ("line_manager", "dept_head"), employee=boss),
            "u_a": make_user("ama", ("employee",), employee=a),
            "hro": make_user("hro", ("hr_officer",)), "hrd": make_user("hrd", ("hr_director",)),
            "fo": make_user("fo", ("finance_officer",))}


def test_builder_validates_against_whitelist_and_field_permissions(people):
    from apps.reports import builder

    with pytest.raises(BusinessRuleError):
        builder.validate({"dataset": "employees", "columns": ["user__password"]}, people["hrd"])
    with pytest.raises(BusinessRuleError):  # HR officers cannot see salaries
        builder.validate({"dataset": "employees", "columns": ["name", "basic_salary"]}, people["hro"])
    with pytest.raises(BusinessRuleError):  # nor filter on them to infer them
        builder.validate({"dataset": "employees", "columns": ["name"],
                          "filters": [{"field": "basic_salary", "op": "gt", "value": 6000}]}, people["hro"])
    with pytest.raises(BusinessRuleError):  # payslips need payroll reporting permission
        builder.validate({"dataset": "payslips", "columns": ["name"]}, people["hro"])
    with pytest.raises(BusinessRuleError):
        builder.validate({"dataset": "employees", "group_by": ["department"],
                          "aggregates": [{"fn": "sum", "field": "name"}]}, people["hrd"])
    assert "payslips" not in {d["code"] for d in builder.catalog(people["hro"])}
    fields = {f["code"] for d in builder.catalog(people["hro"]) if d["code"] == "employees" for f in d["fields"]}
    assert "basic_salary" not in fields and "tenure_band" in fields
    spec = builder.validate({"dataset": "employees", "group_by": ["department"]}, people["hrd"])
    assert spec["aggregates"] == [{"fn": "count"}]


def test_builder_runs_grouped_filtered_and_scoped(people):
    from apps.reports import builder

    headers, rows, meta = builder.run({"dataset": "employees", "group_by": ["department"],
                                       "aggregates": [{"fn": "count"}, {"fn": "sum", "field": "basic_salary"}],
                                       "sort": "-count"}, people["hrd"])
    assert headers == ["Department", "Count", "Sum of Basic salary"]
    assert rows[0][0] == "Operations" and rows[0][1] == 3
    assert dict((r[0], r[1]) for r in rows)["Finance"] == 1
    # computed field filter (tenure band) and choice display
    _, rows, _ = builder.run({"dataset": "employees", "columns": ["name", "tenure_band", "status"],
                              "filters": [{"field": "tenure_band", "op": "eq", "value": "<1"}]}, people["hrd"])
    assert [r[0] for r in rows] == [people["a"].full_name] and rows[0][2] == "Active"
    _, rows, _ = builder.run({"dataset": "employees", "columns": ["name"],
                              "filters": [{"field": "contract_end_date", "op": "isnull", "value": False}]},
                             people["hrd"])
    assert [r[0] for r in rows] == [people["a"].full_name]
    # a department head sees only their department (and themselves) even with the same definition
    _, rows, _ = builder.run({"dataset": "employees", "columns": ["name"]}, people["u_boss"])
    assert people["fin"].full_name not in {r[0] for r in rows} and len(rows) == 3


def test_saved_reports_share_safely_and_exports_need_approval(people):
    c = APIClient()
    c.force_authenticate(people["hrd"])
    body = {"name": "Headcount by department", "dataset": "employees", "group_by": ["department"],
            "visibility": "shared", "chart": "bar"}
    r = c.post("/api/reports/definitions/", body, format="json")
    assert r.status_code == 201, r.content
    rid = r.json()["id"]
    assert r.json()["aggregates"] == [{"fn": "count"}] and r.json()["code"] == f"custom:{rid}"
    bad = c.post("/api/reports/definitions/", {**body, "columns": ["nope"]}, format="json")
    assert bad.status_code == 400
    # the department head can run the shared report but only sees their own scope; cannot change it
    c.force_authenticate(people["u_boss"])
    data = c.get(f"/api/reports/definitions/{rid}/run/").json()
    assert data["rows"] == [["Operations", 3]] and data["chart"] == "bar"
    assert c.patch(f"/api/reports/definitions/{rid}/", {"name": "x"}, format="json").status_code == 403
    # HR officer (reports.build) cannot edit someone else's either, and exports need approval
    c.force_authenticate(people["hro"])
    assert c.patch(f"/api/reports/definitions/{rid}/", {"name": "x"}, format="json").status_code == 403
    assert c.get(f"/api/reports/run/custom:{rid}/").status_code == 200
    r = c.get(f"/api/reports/run/custom:{rid}/", {"format": "xlsx"})
    assert r.status_code == 400 and r.json()["code"] == "export_approval"
    # private reports are invisible to others
    c.force_authenticate(people["hrd"])
    priv = c.post("/api/reports/definitions/", {**body, "visibility": "private"}, format="json").json()["id"]
    c.force_authenticate(people["hro"])
    assert c.get(f"/api/reports/run/custom:{priv}/").status_code == 400
    assert c.get(f"/api/reports/definitions/{priv}/run/").status_code == 404
    # finance can build on payslips; HR officer cannot even preview them
    assert c.post("/api/reports/definitions/preview/", {"dataset": "payslips", "columns": ["name"]},
                  format="json").status_code == 400
    c.force_authenticate(people["fo"])
    assert c.post("/api/reports/definitions/preview/", {"dataset": "payslips", "columns": ["name"]},
                  format="json").status_code == 200


def test_attrition_indicators_are_transparent_restricted_and_logged(people):
    from apps.audit.models import AuditLog
    from apps.reports import predictive
    from apps.talent.models import TalentAssessment

    score, hits = predictive.score_factors({"early_tenure": "0.3 years", "contract_ending": "x", "stagnation": None},
                                           predictive.DEFAULT_WEIGHTS)
    assert score == 30 and {h["code"] for h in hits} == {"early_tenure", "contract_ending"}
    assert predictive.band(score) == "medium" and predictive.band(45) == "high"
    TalentAssessment.objects.create(employee=people["a"], period="2026", performance=2, potential=2, criteria={},
                                    rationale="r", flight_risk="high")
    rows = {r["employee"]: r for r in predictive.risk_scores(people["hrd"])}
    a = rows[people["a"].id]
    assert a["score"] == 50 and a["band"] == "high"
    assert {f["code"] for f in a["factors"]} == {"manager_flag", "early_tenure", "contract_ending"}
    assert all(f["detail"] for f in a["factors"])
    # org-level weight override
    people["hrd"].organization.settings = {"attrition_weights": {"manager_flag": 0}}
    people["hrd"].organization.save()
    assert predictive.risk_scores(people["hrd"])[0]["score"] == 30
    c = APIClient()
    c.force_authenticate(people["u_boss"])  # managers and heads do not get individual scores
    assert c.get("/api/reports/attrition-risk/").status_code == 403
    c.force_authenticate(people["hrd"])
    before = AuditLog.objects.filter(action="view").count()
    r = c.get("/api/reports/attrition-risk/", {"band": "medium"})
    assert r.status_code == 200 and [x["employee"] for x in r.json()["rows"]] == [people["a"].id]
    assert AuditLog.objects.filter(action="view").count() == before + 1
    # nobody sees their own score
    hro_emp = people["fin"]
    people["hrd"].employee = hro_emp
    assert hro_emp.id not in {x["employee"] for x in predictive.risk_scores(people["hrd"])}


def test_turnover_and_retirement_forecasts(people, make_employee):
    from apps.reports import predictive
    from apps.talent.models import SuccessionPlan

    today = dt.date.today()
    gone = make_employee(first="Kofi", hire_date=dt.date(2019, 1, 1))
    gone.status, gone.exit_date = "exited", today - dt.timedelta(days=30)
    gone.save()
    f = predictive.turnover_forecast(people["hrd"])
    assert f["headcount"] == 4 and f["retirements_12m"] == 1
    ops = next(d for d in f["departments"] if d["department"] == "Operations")
    assert ops["exits_12m"] == 1 and ops["expected_leavers"] > 0 and "risk_high" in ops
    assert len(f["monthly"]) == 12 and f["range"][0] <= f["expected_leavers"] <= f["range"][1]
    # aggregate forecasts carry no risk bands for viewers without individual access
    ops_mgr = next(d for d in predictive.turnover_forecast(people["u_boss"])["departments"])
    assert "risk_high" not in ops_mgr

    pos = people["b"].position
    pos.is_critical = True
    pos.save()
    r = predictive.retirement_forecast(people["hrd"], 3)
    assert sum(y["value"] for y in r["by_year"]) == 1
    crit = r["critical_positions"]
    assert len(crit) == 1 and crit[0]["covered"] is False and crit[0]["incumbent"] == people["b"].full_name
    SuccessionPlan.objects.create(position=pos)
    assert predictive.retirement_forecast(people["hrd"], 3)["critical_positions"][0]["successors"] == 0
