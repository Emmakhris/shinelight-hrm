# ShineLight HRM

An enterprise Human Resource Management System for Ghanaian organizations, with an optional hospital/clinical workforce module.
Built for a single organization today; every record is tenant-scoped, so the same codebase can become multi-tenant SaaS later.

**Stack:** Django 5 + Django REST Framework + PostgreSQL + Celery/Redis · React 18 + TypeScript + MUI (installable PWA) · Docker Compose.

## What's in this release

### Phase 1 + Payroll

| Area | Highlights |
|---|---|
| **Core HR** | Single employee master; effective-dated employment history (promotions, transfers, secondments, salary changes, confirmations, suspensions, exits) that never overwrites; future-dated actions auto-apply; contracts with expiry; emergency contacts, beneficiaries, qualifications; concurrent/acting roles; rehire that keeps one identity; duplicate detection (Ghana Card, SSNIT, name + DOB); Excel bulk import with full validation and dry run; data-quality dashboard; custom fields |
| **Organization** | Branches, locations (GPS / geofence), cost centres, hierarchical departments/units/wards, job families and titles, grades with salary steps, **positions separate from people** (approved / frozen / vacant / budgeted), establishment report, live org chart |
| **Workflow engine** | Configurable multi-step approvals for every request type; conditional routing (e.g. leave > 10 days, loans > GHS 5,000); parallel and sequential steps; supervisor, second-level, department head, role or named user approvers; SLA timers, reminders, escalation; delegation of authority; approve, reject or return for correction, with mandatory comments; segregation of duties (no one approves their own request); full history |
| **Leave** | Labour Act-based defaults (annual, sick, maternity, paternity, compassionate, study, casual, unpaid); policies by category, grade and employment type; upfront or monthly accrual; carry-over with expiry; service-based bonus days; working-day calculation excluding Ghana public holidays; half days; staffing-conflict and relief-officer warnings; recall with day credit; return-to-work; balance ledger; team calendar; only **approved** leave reaches payroll |
| **Time & attendance** | Web/mobile clock-in with optional geofence; **ZKTeco** biometric sync; shifts (incl. night and on-call); rotating patterns; two-week roster with publish step; late, early, absent and missing-punch detection; overtime classified as weekday, rest day, public holiday or night, with an approval step; correction requests; monthly summaries locked for payroll |
| **Payroll (Ghana)** | Pure, tested gross-to-net engine: GRA PAYE graduated bands, SSNIT 5.5% / 13% (Tier 1 13.5%, Tier 2 5%) with insurable cap, Tier 3, bonus tax (5% up to 15% of annual basic), junior-staff overtime tax, reliefs, non-resident rate. All rates are **versioned by effective date**. Allowances and deductions can be fixed, % of basic or gross, hourly, daily or a formula; pro-ration; unpaid leave and absence; loans and advances; arrears/retro; final settlement with leave encashment. Pipeline Draft → Calculated → Submitted → Approved → Released with **maker-checker**; variance report; reversal; bank and MoMo payment files; GL journal; GRA PAYE schedule; SSNIT report; password-protectable payslip PDFs |
| **Self-service** | Employee portal (profile, corrections, leave, attendance, payslips, letters, loans, requests with "who acts next", policies to acknowledge, directory) and manager views (team, approvals inbox, team attendance) |
| **Documents** | Classified personnel files (internal, confidential or restricted), versioning, expiry alerts, retention schedules, legal hold, secure disposal, logged downloads, letter templates → PDF, ESS letter requests |
| **Notifications** | In-app, email (SMTP) and SMS (**Hubtel / Arkesel**) with editable templates; contract, probation, document and licence expiry reminders; announcements with acknowledgment |
| **Reports** | HR dashboard, workforce analytics with documented KPI definitions, report catalogue, Excel/CSV export (approval required for users without export rights), scheduled email reports |
| **Security** | RBAC with data scopes (own, team, department, branch, organization); field masking for salary, bank, national IDs and medical data; MFA (TOTP or SMS) enforced for sensitive roles; lockout and login monitoring; HttpOnly JWT cookies plus CSRF; encrypted bank account numbers; **hash-chained, append-only audit trail** with integrity verification; access-review report; Data Protection Act 843 support (consent records, subject-access export, retention) |
| **Hospital add-on** | Professional licence registry and verification; **rostering blocked when a licence or mandatory competency has lapsed**; competency matrix; ward staffing view |
| **Integrations** | REST API (OpenAPI docs at `/api/docs/`), API keys, signed webhooks with retries |

### Phase 2: Service delivery & rewards

| Area | Highlights |
|---|---|
| **HR service desk** | Service catalogue with per-service request forms; tickets with a reference number, routed to the least-loaded agent in a team; response and resolution SLAs that pause while waiting on the employee; warnings and escalation; internal notes; confidential grievances; one-click letters from a ticket; knowledge base with suggestions while typing; reopen; satisfaction ratings; KPIs (SLA %, response/resolution times, backlog, CSAT, per agent) |
| **Travel & expenses** | Per diem rates by destination and grade; travel requests with routing by destination (international adds HR Director approval); advances with a retirement deadline and reminders; expense claims with receipts (or a reason when one is missing) that retire advances; departmental budgets with warnings; settlement through payroll (reimbursement or recovery of an unspent advance) or by transfer. The claim's approver cannot pay it. |
| **Compensation** | Salary review cycles with a budget and per-grade guidelines; justification required for out-of-guideline proposals; approval; applied as effective-dated salary changes (back-dated reviews produce arrears automatically). Bonus schemes (fixed, % of basic, months of basic) post to a payroll period with bonus-tax treatment. |
| **Benefits** | Plans with eligibility (category, grade, service, employment type), dependants, approval, auto-enrolment; the employee share is deducted through payroll; cost and 12-month forecast; total rewards statement PDF |
| **E-signature** | Sequential signing with consent, typed name, IP and timestamp. A SHA-256 check refuses signing if the document changed after it was sent. A signature certificate page is appended to the signed PDF, and every event is in the audit trail. A pluggable provider interface allows an external e-signature service later. |

The workflow engine also skips a step when its only approver already approved an earlier step of the same request (e.g. a supervisor who is also head of department).

See [docs/ROADMAP.md](docs/ROADMAP.md) for Phases 3–4: service desk, recruitment, performance, LMS, succession and more.

## Quick start (development)

Requirements: Python 3.12+, Node 20+.

```bash
cd backend
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt      # macOS/Linux: .venv/bin/pip
.venv/Scripts/python manage.py migrate
.venv/Scripts/python manage.py seed_demo           # demo org, 28 employees, payroll, rosters, licences
.venv/Scripts/python manage.py runserver 8000
```

```bash
cd frontend
npm install
npm run dev                                        # http://localhost:5173 (proxies /api to :8000)
```

Development uses SQLite, console email/SMS and synchronous Celery tasks by default. Demo usernames (admin, hrdirector, hrofficer, payroll, approver, manager, employee, auditor) and the shared demo password are listed at the top of `backend/apps/core/management/commands/seed_demo.py`. MFA is disabled for the demo organization only.

## Production (Docker on a VPS)

```bash
cp .env.example .env            # set SECRET_KEY, FIELD_ENCRYPTION_KEY, DB password, hosts, SMTP, SMS
docker compose up -d --build
docker compose exec backend python manage.py setup_organization --name "Your Organization" --code yourorg --admin admin --email you@org.com --features payroll,sms
```

Full runbook (TLS, backups, restore tests, monitoring, upgrades): [docs/OPERATIONS.md](docs/OPERATIONS.md). **Before paying anyone, work through [docs/GO_LIVE_CHECKLIST.md](docs/GO_LIVE_CHECKLIST.md)**: the statutory rates are seeded unverified.

## Tests

```bash
cd backend && .venv/Scripts/python -m pytest          # 57 tests: payroll golden figures, workflow, leave, RBAC, audit, attendance, service desk, expenses, compensation, e-signature
.venv/Scripts/python scripts/smoke_api.py              # every endpoint x every demo role (needs running server + seed_demo)
.venv/Scripts/python scripts/e2e_flow.py               # leave approval → payroll maker-checker → payslip PDF → GL balance
.venv/Scripts/python scripts/e2e_phase2.py             # ticket → letter → e-signature; travel advance → claim → payroll recovery; benefits
cd frontend && npm test && npx tsc --noEmit && npm run build
```

## Repository layout

```
backend/   Django project (config/, apps/<module>/, templates/pdf/, scripts/)
frontend/  React PWA (src/pages/<module>/, src/components/, src/api/)
docker/    Dockerfiles and nginx config
scripts/   backup.sh / restore.sh
docs/      architecture, operations, go-live checklist, user guide, roadmap
```
