"""Phase 2 end-to-end flow against the seeded dev server:
help desk ticket (raise → agent replies → letter → resolve → rate), travel with advance → expense claim
retiring it → finance settlement, benefit enrolment, and e-signature of the generated letter.

Usage: python scripts/e2e_phase2.py [base_url]
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
    for _ in range(10):  # the login endpoint is rate limited (10/min); wait it out
        r = s.post(f"{BASE}/api/auth/login/", json={"username": user, "password": PASSWORD})
        if r.status_code != 429:
            break
        import time

        time.sleep(int(r.headers.get("Retry-After", "10")) + 1)
    assert r.status_code == 200, r.text
    s.headers["X-CSRFToken"] = s.cookies.get("csrftoken", "")
    return s


def ok(r):
    assert r.status_code in (200, 201), f"{r.status_code} {r.url}: {r.text[:600]}"
    return r.json() if r.headers.get("content-type", "").startswith("application/json") else r


def approve_all(s, rtype):
    n = 0
    for t in ok(s.get(f"{BASE}/api/workflow/inbox/", params={"status": "pending", "instance__request_type": rtype}))["results"]:
        ok(s.post(f"{BASE}/api/workflow/inbox/{t['id']}/act/", json={"action": "approve", "comment": "OK"}))
        n += 1
    return n


emp, hr, mgr = session("employee"), session("hrofficer"), session("manager")
fin, pay = session("approver"), session("payroll")
me = ok(emp.get(f"{BASE}/api/auth/me/"))

# ---- help desk
svc = next(s for s in ok(emp.get(f"{BASE}/api/helpdesk/services/")) if s["name"] == "Employment confirmation letter")
t = ok(emp.post(f"{BASE}/api/helpdesk/tickets/", json={"service_type": svc["id"], "subject": "Letter for GCB",
                                                       "description": "Need it for a loan", "form_data": {
                                                           "addressed_to": "The Manager, GCB Ridge", "purpose": "a loan"}}))
print("ticket:", t["reference"], t["status"], "->", t["assignee_name"])
agent_user = t["assignee_name"]
agents = {"Kofi Mensah": hr}
agent = agents.get(agent_user) or session("hrdirector")
ok(agent.post(f"{BASE}/api/helpdesk/tickets/{t['id']}/comment/", json={"body": "Internal: check salary", "internal": True}))
detail = ok(emp.get(f"{BASE}/api/helpdesk/tickets/{t['id']}/"))
assert all(not c["is_internal"] for c in detail["comments"]), "internal note leaked"
ok(agent.post(f"{BASE}/api/helpdesk/tickets/{t['id']}/generate-letter/"))
ok(agent.post(f"{BASE}/api/helpdesk/tickets/{t['id']}/resolve/", json={"resolution": "Letter issued"}))
ok(emp.post(f"{BASE}/api/helpdesk/tickets/{t['id']}/rate/", json={"rating": 5, "feedback": "Fast"}))
m = ok(hr.get(f"{BASE}/api/helpdesk/tickets/metrics/"))
print("helpdesk KPIs: resolved", m["resolved"], "CSAT", m["csat_average"], "SLA%", m["sla_compliance_percent"])

# ---- e-signature of the generated letter
doc = ok(emp.get(f"{BASE}/api/me/documents/"))[0]
users = ok(hr.get(f"{BASE}/api/users/lookup/", params={"search": "Boateng"}))["results"]
sig = ok(hr.post(f"{BASE}/api/documents/signatures/", json={"document": doc["id"], "signers": [
    {"employee_self": True, "role_label": "Employee"}, {"user": users[0]["id"], "role_label": "Head, HR"}]}))
task = next(x for x in ok(emp.get(f"{BASE}/api/documents/signatures/my-tasks/")) if x["request"] == sig["id"])
ok(emp.post(f"{BASE}/api/documents/signatures/sign/{task['signer_id']}/", json={"typed_name": me["full_name"], "consent": True}))
hrd = session("hrdirector")
task2 = next(x for x in ok(hrd.get(f"{BASE}/api/documents/signatures/my-tasks/")) if x["request"] == sig["id"])
hrd_me = ok(hrd.get(f"{BASE}/api/auth/me/"))
done = ok(hrd.post(f"{BASE}/api/documents/signatures/sign/{task2['signer_id']}/",
                   json={"typed_name": hrd_me["full_name"], "consent": True}))
print("e-signature:", done["status"], "signed version", done["signed_version"])
assert done["status"] == "completed"

# ---- travel + claim retirement
dep = dt.date.today() - dt.timedelta(days=4)
tr = ok(emp.post(f"{BASE}/api/expenses/travel/", json={
    "purpose": "Outreach clinic", "destination": "Kumasi", "destination_class": "national",
    "departure_date": str(dep), "return_date": str(dep + dt.timedelta(days=1)), "transport_estimate": "200",
    "accommodation_estimate": "400", "advance_requested": "600"}))
print("travel:", tr["reference"], "estimate", tr["total_estimate"])
print("travel approvals:", approve_all(mgr, "travel_request") + approve_all(mgr, "travel_request"))
ok(pay.post(f"{BASE}/api/expenses/travel/{tr['id']}/pay-advance/", json={"amount": "600", "reference": "TRF-E2E"}))
claim = ok(emp.post(f"{BASE}/api/expenses/claims/", json={
    "title": "Kumasi outreach", "travel_request": tr["id"], "payment_method": "payroll", "items": [
        {"date": str(dep), "category": "transport", "description": "STC bus", "amount": "180", "receipt_missing_reason": "Paper ticket lost"},
        {"date": str(dep), "category": "meals", "description": "Lunch", "amount": "45"}]}))
print("claim:", claim["reference"], "total", claim["total"], "net", claim["net_payable"])
approve_all(mgr, "expense_claim")
approve_all(fin, "expense_claim")
nxt = (dt.date.today().replace(day=28) + dt.timedelta(days=4))
group = ok(pay.get(f"{BASE}/api/payroll/pay-groups/"))[0]
ok(pay.post(f"{BASE}/api/payroll/periods/generate/", json={"pay_group": group["id"], "year": nxt.year, "month": nxt.month}))
settled = ok(pay.post(f"{BASE}/api/expenses/claims/{claim['id']}/settle/", json={"method": "payroll"}))
print("claim settled:", settled["status"], "via payroll adjustment", settled["payroll_adjustment"])

# ---- benefits
plan = next(p for p in ok(emp.get(f"{BASE}/api/benefits/plans/")) if p["code"] == "medical")
if not plan["my_enrollment"]:
    e = ok(emp.post(f"{BASE}/api/benefits/enrollments/", json={"plan": plan["id"], "start_date": str(dt.date.today()),
                                                               "dependants": [{"name": "Kojo", "relationship": "child"}]}))
    approve_all(hr, "benefit_enrollment")
    e = ok(emp.get(f"{BASE}/api/benefits/enrollments/{e['id']}/"))
    print("benefit enrolment:", e["status"], "employee cost", e["employee_cost"])
rewards = ok(emp.get(f"{BASE}/api/compensation/total-rewards/"))
pdf = emp.get(f"{BASE}/api/compensation/total-rewards/", params={"format": "pdf"})
assert pdf.content[:4] == b"%PDF"
print("total rewards:", rewards["total"], "(PDF ok)")
print("audit chain:", ok(session("auditor").get(f"{BASE}/api/audit/logs/verify/"))["intact"])
print("PHASE 2 E2E OK")
