"""API smoke test against a running dev server seeded with `manage.py seed_demo`.

Usage: python scripts/smoke_api.py [base_url]
Signs in as each demo role and GETs every list/report endpoint, reporting any 5xx or unexpected errors.
"""

import sys

import requests

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
PASSWORD = "Demo@ShineLight2026"  # demo-only, see apps/core/management/commands/seed_demo.py
USERS = ["admin", "hrdirector", "hrofficer", "payroll", "approver", "manager", "employee", "auditor"]
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
]

failures = 0
for user in USERS:
    s = requests.Session()
    s.get(f"{BASE}/api/auth/csrf/")
    r = s.post(f"{BASE}/api/auth/login/", json={"username": user, "password": PASSWORD},
               headers={"X-CSRFToken": s.cookies.get("csrftoken", "")})
    if r.status_code != 200 or r.json().get("mfa_required"):
        print(f"[{user}] login failed: {r.status_code} {r.text[:200]}")
        failures += 1
        continue
    codes = {}
    for ep in ENDPOINTS:
        resp = s.get(f"{BASE}/api/{ep}")
        codes.setdefault(resp.status_code, []).append(ep)
        if resp.status_code >= 500 or resp.status_code in (400, 405):
            failures += 1
            print(f"[{user}] {resp.status_code} {ep}: {resp.text[:300]}")
    summary = ", ".join(f"{c}:{len(v)}" for c, v in sorted(codes.items()))
    print(f"[{user}] {summary}")
print("FAILURES:", failures)
sys.exit(1 if failures else 0)
