# CLAUDE.md

ShineLight HRM is an enterprise HRMS for Ghanaian organizations.
- **Backend:** Django 5 + DRF + PostgreSQL + Celery/Redis in `backend/`.
- **Frontend:** React 18 + TypeScript + MUI PWA in `frontend/`.
- **Deployment:** Docker Compose.
- It runs single-organization today but must stay **SaaS-ready**: never add single-tenant assumptions.

Original requirements: `features.txt`. Phases: `docs/ROADMAP.md`. Architecture: `docs/ARCHITECTURE.md`.

## Status

- **Done:** Phase 1 + Ghana payroll, and Phase 2 (service desk, travel & expenses, compensation & benefits, e-signature), both on `main`. Phase 3 is complete on the `phase-3` branch: recruitment/ATS, onboarding, probation, performance, learning (LMS), employee relations, assets, offboarding, engagement and health & safety.
- **Next:** the rest of Phase 3, in this order:
  1. ~~recruitment/ATS, then onboarding and probation~~ (done);
  2. ~~performance~~ (done);
  3. ~~LMS~~ (done);
  4. ~~employee relations, assets and offboarding~~ (done);
  5. ~~engagement and OHS~~ (done). Next: Phase 4 (see docs/ROADMAP.md).

## Commands

The backend venv is `backend/.venv` (Python 3.13, Windows: `.venv/Scripts/python`).

```bash
cd backend
.venv/Scripts/python manage.py migrate
.venv/Scripts/python manage.py seed_demo                       # demo org + 28 employees (idempotent; refreshes config)
.venv/Scripts/python manage.py runserver 8000
.venv/Scripts/python -m pytest -p no:cacheprovider -q          # 101 tests; add --create-db after model changes
.venv/Scripts/ruff check apps config --select F,E9
.venv/Scripts/python manage.py makemigrations --check --dry-run
.venv/Scripts/python scripts/smoke_api.py                      # every endpoint x every demo role (needs running server)
.venv/Scripts/python scripts/e2e_flow.py                       # Phase 1 flow: leave -> payroll maker-checker -> payslip
.venv/Scripts/python scripts/e2e_phase2.py                     # Phase 2 flow: ticket, e-sign, travel/claim, benefits
.venv/Scripts/python scripts/e2e_phase3.py                     # Phase 3 flow: vacancy, career-site apply, offer, hire, onboarding
.venv/Scripts/python scripts/e2e_performance.py                # appraisal cycle on its own Lab-only cycle (re-runnable)
```

```bash
cd frontend
npm run dev                  # :5173, proxies /api and /media to :8000
npx tsc -p tsconfig.json --noEmit
npm test && npm run build
```

- Run against PostgreSQL by setting `DATABASE_URL=postgres://...`. The default is SQLite. The tests pass on both.
- Demo usernames and the shared demo password are at the top of `backend/apps/core/management/commands/seed_demo.py`. MFA is disabled for the demo org only.
- Public pages (no login): career site `/careers/<org-code>` and offer response `/offer/<token>`. Their API lives under `/api/public/` (`AllowAny`, no auth classes, `apply` throttle scope); wrap work in `org_context(org)` since there is no user to set the tenant.
- `.claude/launch.json` defines the `backend` and `frontend` preview servers. The backend runs with `--noreload`, so **restart it after backend edits**.

## Backend conventions (follow these)

- **Tenancy:** every business model subclasses `apps.core.models.TenantModel` (organization FK, auto-filtering `objects`, unfiltered `all_objects`).
  - Use `all_objects` plus an explicit `organization_id` in Celery tasks and cross-tenant code, or wrap the code in `org_context(org)`.
  - Viewsets subclass `apps.core.views.TenantModelViewSet`, which re-applies the tenant filter.
  - In explicit `PrimaryKeyRelatedField`s, pass the manager (`queryset=Model.objects`), never `.objects.all()` at import time.
- **Permissions:** codes are `module.action`, listed in `apps/rbac/catalog.py` (`PERMISSIONS` and `DEFAULT_ROLES`).
  - Views declare `perm_module`, `perm_read`, `perm_write`, `perm_map`; set an action to `None` in `perm_map` to allow any authenticated user.
  - Data scope (own, team, department, branch, organization): set `scope_prefix` on the viewset, or call `rbac.services.scope_queryset` / `can_access_employee`.
  - Mask sensitive fields with `SensitiveFieldsMixin`.
  - Raise `rest_framework.exceptions.PermissionDenied` for authorization failures (403).
  - Raise `apps.core.exceptions.BusinessRuleError` for rule violations (400 with `{detail, code}`).
- **Approvals:** never write ad-hoc approval logic. Register a `WorkflowHandler` in `<app>/workflow_handlers.py` and import it in `apps/workflow/signals.py`.
  - Start requests with `workflow.engine.start(obj, "<request_type>", user, ...)`.
  - Seed a default definition in `apps/core/setup.py:seed_workflows`.
  - The engine already enforces: the requester can never approve their own request, mandatory comments, delegation, SLA escalation, and skipping a step whose only approver already approved.
- **Employment changes:** always go through `employees.services.apply_change` (effective-dated `EmploymentRecord`). Never edit snapshot fields on `Employee` directly.
- **Audit:** register new models in `apps/audit/registrations.py`, marking `sensitive` fields. Call `audit.services.log(...)` for exports, downloads and sensitive actions. `AuditLog` is append-only and hash-chained.
- **Payroll:** `payroll/engine.py` is a **pure function**; keep DB access out of it.
  - Statutory figures live in effective-dated tables (`StatutoryRateSet`, `TaxTable`) and are seeded **unverified**. Never hard-code rates.
  - One-off money (reimbursements, bonuses, recoveries) goes in as a `PayrollAdjustment` on an open period.
- **Notifications:** `notifications.services.notify(event_code, users, context)`. Default texts are in `notifications/defaults.py`. Keep SMS free of confidential details.
- **Display names in serializers:** use `DisplayField("rel")` from `apps/core/serializers.py`. Do not use `CharField(source="rel.__str__")`, which shows "method-wrapper" when the relation is empty.
- **Money and dates:** use `Decimal` (`q()` helpers quantize to 2 dp, ROUND_HALF_UP), the GHS currency and the Africa/Accra time zone.
- **Exports:** `?format=xlsx|csv` via `core.exports.tabular_response`. DRF's `URL_FORMAT_OVERRIDE` is disabled on purpose.
- **New app checklist:**
  1. Add it to `INSTALLED_APPS`.
  2. Add routes in `config/api_urls.py`.
  3. Add permissions and role grants in `rbac/catalog.py`.
  4. Add audit registrations.
  5. Add workflow handlers.
  6. Add Celery beat entries in `config/celery.py`.
  7. Add seed defaults in `core/setup.py`.
  8. Write tests in `<app>/tests.py`, using the fixtures in `backend/conftest.py`.

## Frontend conventions

- API access: `useApi`, `useList`, `post` and `useInvalidate` from `src/api/hooks.ts`, plus `download`/`openBlob` from `src/api/client.ts` (cookie JWT + CSRF; the axios baseURL is `/api`).
- For CRUD screens, use `components/ResourcePage.tsx` (with `FormDialog` field configs) and `DataTable` rather than writing tables and forms by hand.
- Permission checks: `useAuth().can("perm", minScope?)` and `feature("hospital"|"payroll"|...)`.
- Each new page needs:
  - a lazy route in `src/App.tsx` (wrapped with `g(<Page/>, perm)`);
  - a nav entry in `components/Layout.tsx` (`NAV`).
- Use the formatters in `src/utils.ts` (`fmtDate` DD/MM/YYYY, `fmtMoney` GHS) and `StatusChip`/`useToast` from `components/Feedback.tsx`.
- Charts: `components/Charts.tsx`, which uses the validated categorical palette in fixed order. Never dual axes.

## Gotchas

- Login is throttled at 10/min, so the smoke test followed by the e2e scripts can hit 429s (`e2e_phase2.py` retries).
- Released payroll periods can't take adjustments. Expense settlement via payroll needs an **open** period.
- Onboarding auto-starts from a `post_save` signal on `Employee` (`apps/onboarding/signals.py`) only for hire dates within the last 30 days and when an active checklist exists. Tests using `make_employee` default to a 2020 hire date, so pass `hire_date=today` to exercise onboarding.
- Performance visibility: the employee never sees manager ratings/comments before release (`acknowledgement`/`completed`) or the calibration reason; 360 responses are only exposed aggregated via `feedback_summary` (3+ responses), and `FeedbackRequest` is deliberately not audit-registered so respondents can't be identified.
- Employee relations: case access is by assignment (`relations.services.can_access`) and parties are always excluded, even if they hold HR permissions. Never add line-manager scope to ER cases. Workflow titles and notifications for ER stay generic (no names or allegations).
- `employees.services.revoke_access` consults `offboarding.services.access_extended`; pass `force=True` only when an extension has ended.
- Survey responses must never be linkable to a person when `anonymous`: store no employee, date only, and never report a group below `min_group_size`. Occupational-health clinical data (`safety.OHRecord.clinical_notes`) is `ohs.medical` only; `hr_director` is deliberately excluded from that permission.
- Candidates are not users: email/SMS them with `recruitment.services.message_candidate`, not `notify()`.
- The `hospital` features are behind the per-org feature flag (`OrganizationFeature`). The demo org has payroll, hospital, sms and geofence enabled.
- On Windows the Bash tool can choke on long inline heredocs containing quotes. Write a script file and run it instead.
- Don't commit `.env`, `backend/db.sqlite3`, `backend/media/`, `frontend/dist/` or `node_modules/` (already in `.gitignore`).
- Commit or push only when the user asks.
