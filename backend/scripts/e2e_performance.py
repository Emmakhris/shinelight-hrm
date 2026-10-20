"""Performance end-to-end flow against the seeded dev server, on its own Laboratory-only cycle:
HR launches -> reviewer sets and agrees objectives -> mid-year -> year-end: self-assessment -> manager review
(including after the self-assessment deadline) -> calibration -> release -> employee acknowledges ->
improvement plan approved by HR.

Usage: python scripts/e2e_performance.py [base_url]
"""

import datetime as dt
import sys
import time

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
        time.sleep(int(r.headers.get("Retry-After", "10")) + 1)
    assert r.status_code == 200, r.text
    s.headers["X-CSRFToken"] = s.cookies.get("csrftoken", "")
    return s


def ok(r):
    assert r.status_code in (200, 201), f"{r.status_code} {r.url}: {r.text[:600]}"
    return r.json()


def lst(data):
    return data["results"] if isinstance(data, dict) else data


hrd, med, admin = session("hrdirector"), session("medical"), session("admin")
today = dt.date.today()
lab = next(d for d in lst(ok(hrd.get(f"{BASE}/api/org/departments/"))) if d["code"] == "LAB")
cycle = ok(hrd.post(f"{BASE}/api/performance/cycles/", json={
    "name": f"Lab quarterly review {dt.datetime.now():%H%M%S}", "cycle_type": "quarterly",
    "period_start": str(today - dt.timedelta(days=80)), "period_end": str(today + dt.timedelta(days=10)),
    "self_review_deadline": str(today + dt.timedelta(days=5)), "min_service_days": 60, "departments": [lab["id"]],
    "use_calibration": True, "target_distribution": {"5": 10, "4": 30, "3": 50, "2": 10}}))
launched = ok(hrd.post(f"{BASE}/api/performance/cycles/{cycle['id']}/launch/"))
print("cycle launched:", cycle["name"], "appraisals:", launched["created"])
aps = lst(ok(hrd.get(f"{BASE}/api/performance/appraisals/", params={"cycle": cycle["id"]})))
aps = [a for a in aps if a["reviewer_name"]]
assert len(aps) >= 2, "need two lab staff with a reviewer"
a1, a2 = aps[0], aps[1]

# reviewer sets objectives (agreed immediately, no self-approval)
for ap in (a1, a2):
    for title, w in (("Turnaround time within 2 hours", 40), ("Zero sample labelling errors", 30), ("Complete QC daily", 30)):
        ok(med.post(f"{BASE}/api/performance/objectives/", json={"appraisal": ap["id"], "title": title, "measure": "Lab audit",
                                                                  "weight": w}))
    res = ok(med.post(f"{BASE}/api/performance/appraisals/{ap['id']}/submit-objectives/"))
    assert res["status"] == "objectives_agreed", res["status"]
print("objectives agreed by reviewer")
ok(hrd.post(f"{BASE}/api/performance/cycles/{cycle['id']}/advance/"))  # mid-year
d = ok(med.get(f"{BASE}/api/performance/appraisals/{a1['id']}/"))
ok(med.post(f"{BASE}/api/performance/appraisals/{a1['id']}/midyear/", json={
    "comments": "On track", "objectives": [{"id": o["id"], "midyear_status": "on_track"} for o in d["objectives"]]}))
adv = ok(hrd.post(f"{BASE}/api/performance/cycles/{cycle['id']}/advance/"))  # year-end review
print("year-end review opened:", adv)

# employee 1 self-assessment
users = lst(ok(admin.get(f"{BASE}/api/admin/users/", params={"search": a1["employee_name"].split()[-1]})))
u1 = next(u for u in users if u.get("employee_id") == a1["employee"])
emp1 = session(u1["username"])
d = ok(emp1.get(f"{BASE}/api/performance/appraisals/{a1['id']}/"))
assert d["role"] == "employee" and d["can"]["self_review"]


def rated(d, field, value):
    return {"objectives": [{"id": o["id"], field: value, "achievement": "Done"} for o in d["objectives"]],
            "competencies": [{"id": c["id"], field: value} for c in d["competency_ratings"]]}


ok(emp1.post(f"{BASE}/api/performance/appraisals/{a1['id']}/self-review/", json={**rated(d, "self_rating", 4),
                                                                                   "submit": True}))
d = ok(med.get(f"{BASE}/api/performance/appraisals/{a1['id']}/"))
res = ok(med.post(f"{BASE}/api/performance/appraisals/{a1['id']}/manager-review/", json={
    **rated(d, "manager_rating", 4), "manager_comments": "Reliable", "submit": True}))
print("appraisal 1:", res["status"], "score", res["overall_score"], "rating", res["final_rating"])
assert ok(emp1.get(f"{BASE}/api/performance/appraisals/{a1['id']}/"))["final_rating"] is None  # hidden until release

# appraisal 2: manager can only proceed once the self-assessment deadline has passed
d2 = ok(med.get(f"{BASE}/api/performance/appraisals/{a2['id']}/"))
r = med.post(f"{BASE}/api/performance/appraisals/{a2['id']}/manager-review/", json={**rated(d2, "manager_rating", 2),
                                                                                    "submit": True})
assert r.status_code in (400, 403), r.text
ok(hrd.patch(f"{BASE}/api/performance/cycles/{cycle['id']}/", json={"self_review_deadline": str(today - dt.timedelta(days=1))}))
r = med.post(f"{BASE}/api/performance/appraisals/{a2['id']}/manager-review/", json={**rated(d2, "manager_rating", 2),
                                                                                    "submit": True})
assert r.status_code == 400 and "development plan" in r.text  # low rating needs comments + plan
ok(med.post(f"{BASE}/api/performance/appraisals/{a2['id']}/manager-review/", json={
    **rated(d2, "manager_rating", 2), "manager_comments": "Several labelling errors", "development_needs": "SOP refresher",
    "submit": True}))
print("appraisal 2 reviewed after the self-assessment deadline")

# calibration and release
ok(hrd.post(f"{BASE}/api/performance/cycles/{cycle['id']}/advance/"))  # -> calibration
assert hrd.post(f"{BASE}/api/performance/appraisals/{a1['id']}/calibrate/", json={"rating": 5}).status_code == 400
ok(hrd.post(f"{BASE}/api/performance/appraisals/{a1['id']}/calibrate/", json={"rating": 5, "reason": "Led ISO prep"}))
summary = ok(hrd.get(f"{BASE}/api/performance/cycles/{cycle['id']}/summary/"))
print("calibration:", summary["calibrated_changes"], "change(s); distribution",
      {x["rating"]: x["count"] for x in summary["distribution"] if x["count"]})
closed = ok(hrd.post(f"{BASE}/api/performance/cycles/{cycle['id']}/advance/"))
assert closed["to"] == "closed"
d = ok(emp1.get(f"{BASE}/api/performance/appraisals/{a1['id']}/"))
assert d["final_rating"] == 5 and d["calibration_reason"] == ""
ok(emp1.post(f"{BASE}/api/performance/appraisals/{a1['id']}/acknowledge/", json={"agrees": True, "comments": "Thanks"}))
print("employee acknowledged final rating", d["final_rating_label"])

# improvement plan for the low rating: supervisor drafts, HR approves
plan = ok(med.post(f"{BASE}/api/performance/plans/", json={
    "employee": a2["employee"], "appraisal": a2["id"], "start_date": str(today),
    "end_date": str(today + dt.timedelta(days=45)), "reason": "Sample labelling errors",
    "support": "SOP refresher and weekly check-ins"}))
ok(med.post(f"{BASE}/api/performance/milestones/", json={"plan": plan["id"], "objective": "No labelling errors for 4 weeks",
                                                          "due_date": str(today + dt.timedelta(days=30))}))
ok(med.post(f"{BASE}/api/performance/plans/{plan['id']}/submit/"))
hro = session("hrofficer")
tasks = lst(ok(hro.get(f"{BASE}/api/workflow/inbox/", params={"status": "pending",
                                                                "instance__request_type": "improvement_plan"})))
for t in tasks:
    ok(hro.post(f"{BASE}/api/workflow/inbox/{t['id']}/act/", json={"action": "approve", "comment": "Fair plan"}))
print("improvement plan:", ok(med.get(f"{BASE}/api/performance/plans/{plan['id']}/"))["status"])
print("audit chain:", ok(session("auditor").get(f"{BASE}/api/audit/logs/verify/"))["intact"])
print("PERFORMANCE E2E OK")
