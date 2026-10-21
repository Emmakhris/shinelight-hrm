# Architecture

## Overview

```
Browser / PWA ──HTTPS──► nginx (static PWA, security headers) ──/api──► Django + DRF (gunicorn)
                                                                     │        │
                                                       PostgreSQL ◄──┘        └──► Redis ◄── Celery worker + beat
                                                       (all data)                    (email/SMS, SLA escalation,
                                                                                      accrual, device sync, reminders)
                       ZKTeco terminals ◄── pulled by Celery every 10 min
                       Hubtel / Arkesel, SMTP ◄── outbound notifications
                       Finance / BI / IdP ◄── REST API keys + signed webhooks
```

## Backend apps (`backend/apps/`)

| App | Responsibility |
|---|---|
| `tenancy` | `Organization` (tenant, status, plan, trial), `Plan`, per-tenant feature flags; `resolver.py` (host -> organization), `services.py` (access checks, provisioning, plan limits, trial expiry), `platform.py` (operator console, public tenant info, sign-up), `rls.py` (PostgreSQL row-level security) |
| `core` | `TenantModel` base (organization FK + auto-filtering manager), request context, holidays, numbering, custom fields, PDF/Excel helpers, Ghana localisation, setup and seed commands |
| `accounts` | User model, login, MFA (TOTP/SMS), cookie JWT, lockout, login monitoring, user admin |
| `rbac` | Permission catalogue, roles, scoped role assignments, `has_perm` / `scope_queryset` / field masking |
| `audit` | Append-only hash-chained `AuditLog`, automatic model change capture, chain verification |
| `organization` | Branches, locations, cost centres, departments, grades/steps, job titles, positions, org chart |
| `employees` | Employee master, effective-dated `EmploymentRecord`, contracts, contacts, bank accounts (encrypted), qualifications, change requests, consents, import, data quality |
| `workflow` | Generic approval engine (`engine.py`), definitions/steps, instances/tasks, delegation, SLA processing; domain apps register handlers |
| `notifications` | Templated in-app/email/SMS notifications, SMS gateways, announcements, expiry reminders |
| `documents` | Personnel files, versions, classification, retention/legal hold, letter templates and generation |
| `leave` | Types, policies, ledger-based balances, validation, approval hooks, accrual/carry-over, recall |
| `attendance` | Shifts, policies, patterns, roster, clock events, ZKTeco sync, daily processing, OT approval, period summaries |
| `payroll` | Statutory rule tables, pay elements, **pure calculation engine** (`engine.py`), runs, payslips, loans, adjustments, exports |
| `selfservice` | `/api/me/...` endpoints for ESS/MSS |
| `reports` | Dashboard, analytics with KPI definitions, report catalogue, export approvals, scheduled reports; `builder.py` (whitelisted datasets and fields, executed in the viewer's scope; saved as `ReportDefinition`, run as `custom:<id>`); `predictive.py` (turnover and retirement forecasts, rule-based attrition-risk indicators) |
| `integrations` | API keys, webhooks, deliveries with retry |
| `sso` | OpenID Connect identity providers per organization, external identities (provider + subject), discovery/start/callback views; `services.py` holds the flow and token verification |
| `assistant` | Governed AI assistant: conversations and messages (exact API content blocks replayed append-only), `tools.py` (read-only, permission-checked tools), `services.py` (Claude tool loop, redaction, limits, usage, retention purge) |
| `hospital` | Licences, competency requirements/records, credential checks used by rostering |
| `servicedesk` | Service catalogue, tickets with SLA pause/escalation, knowledge base, CSAT, KPIs |
| `expenses` | Per diem, travel requests and advances, expense claims, budgets, settlement via payroll |
| `compensation` | Salary review cycles, bonus schemes, benefit plans and enrolments, total rewards |
| `recruitment` | Requisitions, vacancies, candidates, applications and stage history, interviews and scorecards, reference checks, offers, public career site and offer response endpoints (`/api/public/...`, no login, throttled), analytics |
| `performance` | Rating scales, competencies, appraisal forms, review cycles and goals, appraisals with objectives and competency ratings, anonymous 360 feedback, calibration, improvement plans; `latest_rating()` feeds compensation merit guidelines |
| `learning` | Courses, modules and assessments, sessions, enrolments (with the `training_request` workflow), budgets, mandatory training and compliance, CPD, development goals, mentoring; completion renews `hospital.CompetencyRecord` |
| `relations` | Confidential ER cases (access by assignment, never to parties), notes/evidence, meetings, sanctions with the `disciplinary_decision` workflow, appeals, warnings, trend report |
| `assets` | Asset categories and register, assignments (tagged or by quantity), acknowledgment, loss/damage, return and payroll recovery (`ASSET_RECOVERY` element) |
| `offboarding` | Separations with the `separation` workflow, notice rules, clearance items with automatic checks, access extensions (consulted by `employees.services.revoke_access`), exit interviews, certificate of service, turnover analytics |
| `engagement` | Surveys (invites kept separate from anonymous responses), results with minimum group size, action plans, recognition, suggestions, events |
| `safety` | Incidents, corrective actions, risk assessments, inspections, statistics; `OHRecord` clinical zone (`ohs.medical` only) and `fitness_status()` used by `hospital.services.credential_issues` |
| `talent` | Talent profiles, nine-box assessments with evidenced potential criteria, succession plans and successors, career paths and promotion eligibility, workforce plans, plan lines and scenarios; `project()` is a pure projection function |
| `onboarding` | Checklist templates, onboarding records and tasks (auto-started by a `post_save` signal on new employees), probation reviews and outcome workflow |

## Key design decisions

- **Editions.** `DEPLOYMENT_MODE=self_hosted` serves one organization whatever the host name: the platform API, sign-up and the TLS check return 404, `setup_organization`/`provision` refuse a second organization and `create_platform_admin` is refused. `cloud` turns on host routing, the operator console, plans and trials. SSO redirects back to the address the user signed in on, so each organization's session cookie lands on its own host.
- **Multi-tenancy.** Every business table has `organization_id`. The authentication classes set the request's organization from the user and call `tenancy.services.check_access`, which rejects a session or API key used on another organization's host (`<code>.<SAAS_BASE_DOMAIN>`, `<code>.localhost`, or the organization's `domain`), refuses suspended organizations, and limits accounts with no organization (platform operators) to `/api/platform/` and `/api/auth/`. `TenantManager` and `TenantModelViewSet` filter by the organization; `TenantModel.save()` takes the organization from the context or from a tenant-scoped parent and refuses to guess when several organizations exist. On PostgreSQL, `org_context()` and every request also set `app.current_org`, and `manage.py enable_rls` adds a forced row-level security policy to every tenant table, so even `all_objects` cannot cross organizations while it is set. Missing or foreign ids raise `DoesNotExist`, which the API exception handler turns into 404.
- **Position ≠ person.** `Position` is the approved post (budget, headcount, status); `Employee.position` is who fills it. Vacancy control is enforced on hire and transfer.
- **Effective dating.** `EmploymentRecord` rows are inserted, never edited, and closed with `effective_to`. `Employee` holds a denormalised current snapshot for fast queries. `as_of(employee, date)` reconstructs history, and back-dated salary changes generate arrears.
- **One workflow engine.** Leave, corrections, profile changes, letters, loans and payroll approval all run through `workflow.engine`. A domain app only implements a `WorkflowHandler` (title, context for conditions, and `on_approved` / `on_rejected` / … hooks).
- **Payroll engine is a pure function.** `engine.calculate(PayInputs, Rules) → PayResult` has no DB access. The service layer builds inputs from HR data and effective-dated rule tables, so any payslip can be reproduced. Golden tests pin the GRA/SSNIT arithmetic.
- **Ledger-based leave.** The balance is the sum of immutable ledger entries (entitlement, accrual, carry-over, taken, reversal, adjustment, expiry). Pending requests are reported separately and never reach payroll.
- **Defence in depth for sensitive data.** Permission plus data scope plus field masking. Restricted documents need a separate permission, bank numbers are encrypted at rest, and sensitive views and exports are audited.
- **Tamper-evident audit.** Each entry stores the SHA-256 of the previous entry. The ORM refuses updates and deletes, and `verify_chain` detects out-of-band edits.

## Scheduled jobs (Celery beat)

| Job | Schedule |
|---|---|
| Workflow SLA reminders and escalation | every 15 min |
| ZKTeco sync | every 10 min |
| Nightly attendance processing, due personnel actions, due exits (access revocation) | 02:00 |
| Expiry reminders (contracts, probation, documents, licences), celebrations | 07:00 |
| Monthly leave accrual and carry-over expiry | 1st of month 01:00 |
| Webhook retries | every 5 min |
| Scheduled reports | 06:00 |
| Recruitment housekeeping: close expired vacancies, expire offers, anonymise candidates past retention | 00:30 |
| Onboarding: overdue task escalation, probation review reminders | 07:15 |
| Performance: deadline reminders, improvement plans ending in a week | 07:45 |
| Learning: assign due mandatory training, due-date and effectiveness reminders | 06:30 |
| Employee relations: escalate cases past their deadline | 07:05 |
| Offboarding: revoke access when extensions end, upcoming retirement reminders | 02:30 |
| Safety: overdue corrective actions, risk assessments due for review | 07:20 |
| Engagement: close surveys past their closing date | 00:15 |
| SaaS: trial reminders (3 days before) and suspension of ended trials | 06:05 |
| AI assistant: delete conversations past the retention period | 03:40 |
