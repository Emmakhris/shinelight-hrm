"""End-to-end API flow against the seeded dev server:
employee applies for leave -> line manager approves -> HR approves -> balance updated;
payroll officer creates period + run, calculates and submits -> approver approves and releases ->
employee sees the payslip and downloads the PDF.

Usage: python scripts/e2e_flow.py [base_url]
"""

import datetime as dt
import sys

import requests

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
PASSWORD = "Demo@ShineLight2026"  # demo-only (seed_demo)


def session(user):
    s = requests.Session()
    s.get(f"{BASE}/api/auth/csrf/")
    s.headers["X-CSRFToken"] = s.cookies.get("csrftoken", "")
    r = s.post(f"{BASE}/api/auth/login/", json={"username": user, "password": PASSWORD})
    assert r.status_code == 200, r.text
    s.headers["X-CSRFToken"] = s.cookies.get("csrftoken", "")
    return s


def ok(r, code=(200, 201)):
    assert r.status_code in (code if isinstance(code, tuple) else (code,)), f"{r.status_code} {r.url}: {r.text[:500]}"
    return r.json() if r.headers.get("content-type", "").startswith("application/json") else r


def approve_all(s, rtype):
    tasks = ok(s.get(f"{BASE}/api/workflow/inbox/", params={"status": "pending", "instance__request_type": rtype}))["results"]
    for t in tasks:
        ok(s.post(f"{BASE}/api/workflow/inbox/{t['id']}/act/", json={"action": "approve", "comment": "OK"}))
    return len(tasks)


emp = session("employee")
me = ok(emp.get(f"{BASE}/api/auth/me/"))
annual = next(t for t in ok(emp.get(f"{BASE}/api/leave/types/")) if t["code"] == "annual")
booked = ok(emp.get(f"{BASE}/api/leave/requests/", params={"employee": me["employee"]["id"]}))["results"]
start = dt.date.today() + dt.timedelta(days=30)
while start.weekday() != 0 or any(b["status"] in ("pending", "approved") and b["start_date"] <= str(start + dt.timedelta(days=2))
                                  and b["end_date"] >= str(start) for b in booked) or start.year != dt.date.today().year:
    start += dt.timedelta(days=1)
    if start.year != dt.date.today().year:
        start = dt.date.today() + dt.timedelta(days=1)
before = next(b for b in ok(emp.get(f"{BASE}/api/leave/requests/balances/")) if b["code"] == "annual")
req = ok(emp.post(f"{BASE}/api/leave/requests/", json={"leave_type": annual["id"], "start_date": str(start),
                                                       "end_date": str(start + dt.timedelta(days=2)), "reason": "Family"}))
print("leave submitted:", req["status"], req["days"], "days")
mgr = session("manager")
print("manager approved:", approve_all(mgr, "leave_request"))
hr = session("hrofficer")
print("hr approved:", approve_all(hr, "leave_request"))
after = next(b for b in ok(emp.get(f"{BASE}/api/leave/requests/balances/")) if b["code"] == "annual")
print(f"annual leave available: {before['available']} -> {after['available']}")
assert float(after["available"]) == float(before["available"]) - 3

pay = session("payroll")
group = ok(pay.get(f"{BASE}/api/payroll/pay-groups/"))[0]
today = dt.date.today()
period = ok(pay.post(f"{BASE}/api/payroll/periods/generate/", json={"pay_group": group["id"], "year": today.year,
                                                                    "month": today.month}))
runs = [r for r in ok(pay.get(f"{BASE}/api/payroll/runs/", params={"period": period["id"]}))["results"]
        if r["run_type"] == "regular" and r["status"] != "reversed"]
run = runs[0] if runs else ok(pay.post(f"{BASE}/api/payroll/runs/", json={"period": period["id"], "run_type": "regular"}))
if run["status"] in ("draft", "calculated", "rejected"):
    run = ok(pay.post(f"{BASE}/api/payroll/runs/{run['id']}/calculate/"))
    print("calculated:", run["totals"])
    errors = ok(pay.get(f"{BASE}/api/payroll/runs/{run['id']}/payslips/", params={"status": "error"}))
    assert errors["count"] == 0, errors
    run = ok(pay.post(f"{BASE}/api/payroll/runs/{run['id']}/submit/"))
    r = pay.post(f"{BASE}/api/payroll/runs/{run['id']}/release/")
    assert r.status_code == 403, f"preparer must not release: {r.status_code}"
appr = session("approver")
print("payroll approved:", approve_all(appr, "payroll_run"))
for kind in ("register", "paye", "ssnit", "journal", "variance"):
    ok(appr.get(f"{BASE}/api/payroll/runs/{run['id']}/report/{kind}/"))
bank = appr.get(f"{BASE}/api/payroll/runs/{run['id']}/bank-file/", params={"format": "csv"})
assert bank.status_code == 200 and b"Amount" in bank.content
run = ok(appr.post(f"{BASE}/api/payroll/runs/{run['id']}/release/", json={"publish": True}))
print("released:", run["status"])
slips = ok(emp.get(f"{BASE}/api/payroll/payslips/", params={"mine": 1}))["results"]
assert slips, "employee should see a published payslip"
pdf = emp.get(f"{BASE}/api/payroll/payslips/{slips[0]['id']}/pdf/")
assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
print(f"employee payslip {slips[0]['period_name']}: net {slips[0]['net_pay']} (PDF {len(pdf.content)} bytes)")
journal = ok(appr.get(f"{BASE}/api/payroll/runs/{run['id']}/report/journal/"))
dr = sum(float(r[3]) for r in journal["rows"])
cr = sum(float(r[4]) for r in journal["rows"])
print(f"GL journal balanced: debit {dr:,.2f} credit {cr:,.2f}")
assert abs(dr - cr) < 0.05
ver = ok(session("auditor").get(f"{BASE}/api/audit/logs/verify/"))
print("audit chain:", ver)
assert ver["intact"]
hrd = session("hrdirector")
for url in ("employees/export/", "reports/run/headcount/", "leave/requests/report/balances/",
            f"payroll/runs/{run['id']}/report/paye/", "attendance/days/export/"):
    x = (appr if "payroll" in url else hrd).get(f"{BASE}/api/{url}", params={"format": "xlsx"})
    assert x.status_code == 200 and x.content[:2] == b"PK", f"{url}: {x.status_code} {x.content[:200]}"
print("Excel exports OK")
print("E2E OK")
