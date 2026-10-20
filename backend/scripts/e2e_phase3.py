"""Phase 3 end-to-end flow against the seeded dev server:
public career-site application with CV -> internal application -> offer approval (HR Director) -> send ->
candidate accepts through the public link -> hire -> onboarding tasks (IT, new hire survey) ->
probation review -> manager requisition.

Usage: python scripts/e2e_phase3.py [base_url]
"""

import datetime as dt
import sys
import time

import requests

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
PASSWORD = "Demo@ShineLight2026"  # demo-only (seed_demo)
ORG = "shinelight"


def session(user):
    s = requests.Session()
    s.get(f"{BASE}/api/auth/csrf/")
    s.headers["X-CSRFToken"] = s.cookies.get("csrftoken", "")
    for _ in range(10):  # the login endpoint is rate limited (10/min); wait it out
        r = s.post(f"{BASE}/api/auth/login/", json={"username": user, "password": PASSWORD})
        if r.status_code != 429:
            break
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


anon = requests.Session()
stamp = dt.datetime.now().strftime("%H%M%S")
rec, hrd = session("recruiter"), session("hrdirector")

# ---- recruiter publishes a vacancy
depts = ok(rec.get(f"{BASE}/api/org/departments/"))
lab = next(d for d in (depts["results"] if isinstance(depts, dict) else depts) if d["code"] == "LAB")
vac = ok(rec.post(f"{BASE}/api/recruitment/vacancies/", json={
    "title": f"Laboratory Assistant {stamp}", "department": lab["id"], "summary": "Support the laboratory team.",
    "min_qualification": "diploma", "min_experience_years": 1, "visibility": "both",
    "closing_date": str(dt.date.today() + dt.timedelta(days=14)),
    "screening_questions": [{"key": "ahpc", "question": "Are you registered with the AHPC?", "type": "yes_no",
                             "knockout": "no"}]}))
vac = ok(rec.post(f"{BASE}/api/recruitment/vacancies/{vac['id']}/publish/"))
print("vacancy published:", vac["reference"])

# ---- public career site application with CV
listed = [v["id"] for v in ok(anon.get(f"{BASE}/api/public/careers/{ORG}/"))["vacancies"]]
assert vac["id"] in listed
r = anon.post(f"{BASE}/api/public/careers/{ORG}/{vac['id']}/apply/", data={
    "first_name": "Esi", "last_name": f"Mensah{stamp}", "email": f"esi.{stamp}@example.com", "phone": "0201112233",
    "highest_qualification": "diploma", "years_experience": "3", "consent": "true", "talent_pool": "true",
    "answers": '{"ahpc": "yes"}'}, files={"cv": ("cv.pdf", b"%PDF-1.4 e2e cv", "application/pdf")})
ref = ok(r)["reference"]
print("public application:", ref)

# ---- internal application by an employee
emp = session("employee")
r = emp.post(f"{BASE}/api/me/vacancies/", json={"vacancy": vac["id"], "consent": True, "highest_qualification": "diploma",
                                                 "years_experience": 4, "answers": {"ahpc": "yes"}})
print("internal application:", ok(r)["reference"])

# ---- shortlist, interview, offer -> HR Director approval -> send
app = ok(rec.get(f"{BASE}/api/recruitment/applications/", params={"search": ref}))["results"][0]
ok(rec.post(f"{BASE}/api/recruitment/applications/{app['id']}/move/", json={"stage": "shortlisted", "notify": True}))
users = ok(rec.get(f"{BASE}/api/users/lookup/", params={"search": "Agyeman"}))["results"]
when = (dt.datetime.now(dt.UTC) + dt.timedelta(days=1)).isoformat()
ok(rec.post(f"{BASE}/api/recruitment/interviews/", json={"application": app["id"], "scheduled_at": when,
                                                          "panel": [users[0]["id"]], "venue": "Lab office"}))
detail = ok(rec.get(f"{BASE}/api/recruitment/applications/{app['id']}/"))
assert detail["stage"] == "interview" and detail["has_cv"]
titles = ok(rec.get(f"{BASE}/api/org/job-titles/"))
jt = next(t for t in (titles["results"] if isinstance(titles, dict) else titles) if "Laboratory" in t["name"])
offer = ok(rec.post(f"{BASE}/api/recruitment/offers/", json={
    "application": app["id"], "job_title": jt["id"], "department": lab["id"], "basic_salary": "3500",
    "start_date": str(dt.date.today() + dt.timedelta(days=21)), "expiry_date": str(dt.date.today() + dt.timedelta(days=7)),
    "probation_months": 6, "allowances": [{"name": "Transport", "amount": 250}], "submit": True}))
print("offer:", offer["reference"], offer["status"])
print("offer approvals (HR Director):", approve_all(hrd, "job_offer"))
offer = ok(rec.post(f"{BASE}/api/recruitment/offers/{offer['id']}/send/"))
assert offer["status"] == "sent"

# ---- candidate accepts through the public link (token is only in their email; read it from the dev DB)
import os  # noqa: E402

import django  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()
from apps.recruitment.models import Offer  # noqa: E402

token = Offer.all_objects.get(pk=offer["id"]).token
view = ok(anon.get(f"{BASE}/api/public/offers/{token}/"))
pdf = anon.get(f"{BASE}/api/public/offers/{token}/", params={"letter": 1})
assert pdf.content[:4] == b"%PDF"
assert anon.post(f"{BASE}/api/public/offers/{token}/", json={"decision": "accept", "typed_name": "Wrong"}).status_code == 400
ok(anon.post(f"{BASE}/api/public/offers/{token}/", json={"decision": "accept", "typed_name": view["candidate_name"]}))
print("candidate accepted offer (letter PDF ok)")
hired = ok(rec.post(f"{BASE}/api/recruitment/offers/{offer['id']}/hire/"))
print("hired:", hired["staff_number"])
ob = ok(hrd.get(f"{BASE}/api/onboarding/records/", params={"employee": hired["employee"]}))["results"][0]
print("onboarding started automatically:", ob["progress"])

# ---- onboarding tasks routed to IT and to the new hire
it = session("itsupport")
tasks = ok(it.get(f"{BASE}/api/onboarding/tasks/", params={"mine": 1, "open": 1}))["results"]
for t in tasks[:2]:
    ok(it.post(f"{BASE}/api/onboarding/tasks/{t['id']}/complete/", json={"notes": "Provisioned"}))
print("IT tasks completed:", min(2, len(tasks)), "of", len(tasks))
nh = session("newhire")
mine = ok(nh.get(f"{BASE}/api/me/onboarding/"))
survey = next((t for t in mine["my_tasks"] if t["category"] == "survey" and t["status"] == "pending"), None)
if survey:
    ok(nh.post(f"{BASE}/api/onboarding/tasks/{survey['id']}/complete/",
               json={"response": {"welcome": 5, "clarity": 4, "tools": 4, "comments": "Great start"}}))
print("new hire onboarding progress:", ok(nh.get(f"{BASE}/api/me/onboarding/"))["onboarding"]["progress"])

# ---- probation review by the supervisor (midpoint -> continue)
med = session("medical")
reviews = ok(med.get(f"{BASE}/api/onboarding/probation/", params={"mine": 1, "status": "scheduled"}))["results"]
mid = next((r for r in reviews if r["review_type"] == "midpoint" and r["can_review"]), None)
if mid:
    res = ok(med.post(f"{BASE}/api/onboarding/probation/{mid['id']}/submit/", json={
        "ratings": {c: 4 for c in mid["criteria"]}, "recommendation": "continue", "strengths": "Quick learner"}))
    print("midpoint probation review:", res["status"], res["overall_rating"])

# ---- manager raises a requisition. The requester heads Ward A, so the HOD step escalates to the parent
# directorate head (Medical Director), then HR Director and finance approve.
mgr = session("manager")
jt = ok(mgr.get(f"{BASE}/api/org/job-titles/"))
jt = (jt["results"] if isinstance(jt, dict) else jt)[0]
dept = ok(mgr.get(f"{BASE}/api/org/departments/"))
dept = next(d for d in (dept["results"] if isinstance(dept, dict) else dept) if d["code"] == "WARD_A")
req = ok(mgr.post(f"{BASE}/api/recruitment/requisitions/", json={
    "job_title": jt["id"], "department": dept["id"], "headcount": 1, "reason": "temporary",
    "justification": "Maternity cover", "salary_max": "3000", "submit": True}))
print("requisition:", req["reference"], req["status"])
print("requisition approvals (Medical Director as HOD):", approve_all(med, "job_requisition"))
print("requisition approvals (HR Director):", approve_all(hrd, "job_requisition"))
fin = session("approver")
print("requisition approvals (finance):", approve_all(fin, "job_requisition"))
status = ok(mgr.get(f"{BASE}/api/recruitment/requisitions/{req['id']}/"))["status"]
print("requisition status:", status)
assert status == "approved"
an = ok(rec.get(f"{BASE}/api/recruitment/analytics/"))
print("analytics: hires", an["hires"], "offer acceptance", an["offer_acceptance_percent"], "time to hire", an["avg_time_to_hire_days"])
print("audit chain:", ok(session("auditor").get(f"{BASE}/api/audit/logs/verify/"))["intact"])
print("PHASE 3 E2E OK")
