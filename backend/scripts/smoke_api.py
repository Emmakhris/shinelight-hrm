"""API smoke test against a running dev server seeded with `manage.py seed_demo`.

Usage: python scripts/smoke_api.py [base_url]
Signs in as each demo role and GETs every list/report endpoint, reporting any 5xx or unexpected errors.
"""

import sys
import time

import requests

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
PASSWORD = "Demo@ShineLight2026"  # demo-only, see apps/core/management/commands/seed_demo.py
USERS = ["admin", "hrdirector", "hrofficer", "payroll", "approver", "manager", "employee", "auditor",
         "recruiter", "itsupport", "newhire", "safety", "ohdoctor"]
ENDPOINTS = [
    "auth/me/", "me/summary/", "me/profile/", "me/documents/", "me/letters/", "me/team/", "me/change-requests/",
    "employees/", "employees/data-quality/", "employees/change-requests/", "employees/categories/", "directory/",
    "employees/bank-accounts/", "org/departments/", "org/departments/tree/", "org/positions/", "org/positions/establishment/",
    "org/chart/", "org/grades/", "org/grade-steps/", "org/job-titles/", "org/branches/", "org/locations/",
    "org/cost-centers/", "documents/", "documents/categories/", "documents/templates/", "documents/policies/",
    "documents/expiring/", "workflow/inbox/", "workflow/inbox/counts/", "workflow/requests/", "workflow/definitions/",
    "workflow/definitions/request-types/", "workflow/delegations/", "notifications/", "notifications/unread-count/",
    "announcements/", "leave/types/", "leave/policies/", "leave/requests/", "leave/requests/balances/",
    "leave/requests/calendar/", "leave/requests/report/balances/", "leave/requests/report/utilization/",
    "attendance/clock/", "attendance/team-today/", "attendance/shifts/", "attendance/policies/", "attendance/roster/",
    "attendance/roster/staffing/", "attendance/days/", "attendance/corrections/", "attendance/summaries/",
    "attendance/devices/", "payroll/runs/", "payroll/periods/", "payroll/elements/", "payroll/tax-tables/",
    "payroll/rate-sets/", "payroll/reliefs/", "payroll/pay-groups/", "payroll/profiles/", "payroll/employee-elements/",
    "payroll/loans/", "payroll/payslips/", "reports/dashboard/", "reports/analytics/", "reports/catalog/",
    "reports/run/headcount/", "reports/run/expiries/", "reports/run/attendance/", "reports/export-requests/",
    "admin/users/", "admin/roles/", "admin/permissions/", "admin/role-assignments/", "admin/holidays/",
    "admin/login-attempts/", "organization/", "audit/logs/", "audit/logs/verify/", "audit/logs/access-review/",
    "integrations/webhooks/", "integrations/api-keys/", "hospital/licenses/", "hospital/credentials/",
    "hospital/competency-requirements/", "users/lookup/",
    # phase 2
    "helpdesk/categories/", "helpdesk/services/", "helpdesk/articles/", "helpdesk/articles/suggest/?q=payslip+password",
    "helpdesk/tickets/", "helpdesk/tickets/?view=open", "helpdesk/tickets/metrics/", "helpdesk/tickets/agents/",
    "expenses/per-diem/", "expenses/budgets/", "expenses/travel/", "expenses/travel/outstanding-advances/",
    "expenses/claims/", "compensation/reviews/", "compensation/bonus-schemes/", "benefits/plans/", "benefits/plans/cost/",
    "benefits/enrollments/", "compensation/total-rewards/", "documents/signatures/", "documents/signatures/my-tasks/",
    # phase 3
    "recruitment/requisitions/", "recruitment/vacancies/", "recruitment/candidates/", "recruitment/applications/",
    "recruitment/applications/?active=1", "recruitment/interviews/", "recruitment/interviews/?mine=1",
    "recruitment/checks/", "recruitment/offers/", "recruitment/analytics/", "me/vacancies/", "me/onboarding/",
    "onboarding/templates/", "onboarding/template-tasks/", "onboarding/records/", "onboarding/records/dashboard/",
    "onboarding/tasks/", "onboarding/tasks/?mine=1&open=1", "onboarding/probation/", "onboarding/probation/?mine=1",
    "performance/scales/", "performance/competencies/", "performance/templates/", "performance/cycles/",
    "performance/cycles/2/summary/", "performance/goals/", "performance/appraisals/", "performance/appraisals/?mine=1",
    "performance/appraisals/?team=1", "performance/objectives/", "performance/feedback/", "performance/plans/",
    "performance/plans/?mine=1", "performance/milestones/", "compensation/reviews/",
    "learning/courses/", "learning/modules/", "learning/questions/", "learning/sessions/", "learning/sessions/?upcoming=1",
    "learning/enrollments/", "learning/enrollments/?mine=1", "learning/enrollments/?team=1", "learning/budgets/",
    "learning/cpd/", "learning/cpd/summary/", "learning/cpd-requirements/", "learning/development-goals/",
    "learning/mentorships/", "learning/compliance/", "learning/needs/", "learning/report/",
    "relations/cases/", "relations/my/", "relations/report/", "assets/categories/", "assets/items/",
    "assets/assignments/", "assets/assignments/?mine=1", "assets/dashboard/", "offboarding/separations/",
    "offboarding/separations/?mine=1", "offboarding/separations/?clearance_for_me=1", "offboarding/analytics/",
    "engagement/surveys/", "engagement/surveys/mine/", "engagement/surveys/trends/", "engagement/surveys/1/results/",
    "engagement/action-plans/", "engagement/recognition/", "engagement/suggestions/", "engagement/events/",
    "engagement/overview/", "safety/incidents/", "safety/incidents/?mine=1", "safety/actions/", "safety/risks/",
    "safety/inspections/", "safety/oh-records/", "safety/fitness/", "safety/stats/",
]

failures = 0
for user in USERS:
    s = requests.Session()
    s.get(f"{BASE}/api/auth/csrf/")
    for _ in range(10):  # the login endpoint is rate limited (10/min); wait it out
        r = s.post(f"{BASE}/api/auth/login/", json={"username": user, "password": PASSWORD},
                   headers={"X-CSRFToken": s.cookies.get("csrftoken", "")})
        if r.status_code != 429:
            break
        time.sleep(int(r.headers.get("Retry-After", "10")) + 1)
    if r.status_code != 200 or r.json().get("mfa_required"):
        print(f"[{user}] login failed: {r.status_code} {r.text[:200]}")
        failures += 1
        continue
    codes = {}
    for ep in ENDPOINTS:
        resp = s.get(f"{BASE}/api/{ep}")
        codes.setdefault(resp.status_code, []).append(ep)
        no_employee = resp.status_code == 400 and "employee record" in resp.text  # accounts without a staff record
        if resp.status_code >= 500 or (resp.status_code in (400, 405) and not no_employee):
            failures += 1
            print(f"[{user}] {resp.status_code} {ep}: {resp.text[:300]}")
    summary = ", ".join(f"{c}:{len(v)}" for c, v in sorted(codes.items()))
    print(f"[{user}] {summary}")
print("FAILURES:", failures)
sys.exit(1 if failures else 0)
