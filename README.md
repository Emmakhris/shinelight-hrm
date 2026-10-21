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

### Phase 3: Talent & lifecycle

| Area | Highlights |
|---|---|
| **Recruitment / ATS** | Manpower requisitions checked against the approved establishment and routed to the head of department, HR Director and finance; vacancies published to a public **career site** (`/careers/<org-code>`) and an internal job board; applications with CV upload, consent (Act 843) and screening questions; advisory screening score and knock-out flags (never auto-rejects); pipeline stages with reasons for rejection; interview scheduling with panel notifications and candidate invitations; weighted scorecards, with colleagues' scores hidden until a panelist submits; reference and background checks that require candidate consent; talent pool with automatic anonymisation when the retention period ends; analytics (time to hire, time to fill, vacancy ageing, funnel, sources, offer acceptance, cost per hire) |
| **Offers** | Offer letters generated from a template; approval by the HR Director (plus finance when above the requisition budget); revisions for negotiation; a secure public link where the candidate reads the letter and accepts by typing their name (date, time and IP recorded), declines or asks to discuss terms; **Hire** creates the employee through the effective-dated hire record and files the CV and offer letter in the personnel file |
| **Onboarding** | Checklists start automatically when a new employee is registered; the most specific template is used (department and employment type); tasks route to HR, the supervisor, IT, finance, administration and the new hire, with pre-boarding tasks before day one; completion rules (document on file, policy acknowledgment, forms such as the new-hire survey); overdue escalation to HR; dashboard |
| **Probation** | Mid-point and end-of-probation reviews scheduled from the hire and probation end dates, with reminders to the supervisor; rated review with a recommendation; confirmation (effective from the end of probation, with a confirmation letter), extension (re-schedules the final review) or termination through the approval workflow; employee sees and acknowledges the review once submitted |

| **Performance** | Review cycles (annual, half-year, quarterly) with eligibility rules and deadlines; organization and department goals that individual objectives cascade from; role-specific forms (clinical, management, standard) with weighted objectives and competencies on a configurable rating scale; objectives agreed by the supervisor through the approval workflow; mid-year check-in; self-assessment, manager review (allowed once the self-assessment deadline passes) and weighted scoring; anonymous 360 feedback shown only once 3+ people respond; calibration against a target distribution with audited reasons; release and employee acknowledgment (disputes alert HR); improvement plans with milestones, HR approval and outcomes; ratings feed salary-review merit guidelines |

| **Learning & development** | Course catalogue (classroom, e-learning, external, on-the-job) with CPD credits and costs; training requests routed to the supervisor and training office (HR Director above GHS 2,000 or beyond the department budget); sessions with capacity, waitlist and attendance; e-learning modules and scored assessments (answers never sent to the browser, 3 attempts); mandatory training by role with refresher periods, assigned automatically and tracked in a compliance matrix; completing a course renews the linked clinical competency used by roster credential checks; CPD records and annual requirements per role; training needs from appraisal competency gaps; individual development plans and mentoring; participant and manager (applied-on-the-job) evaluations; spend vs budget and effectiveness reports |

| **Employee relations** | Confidential grievance, harassment, whistleblowing (optionally anonymous), misconduct and disciplinary cases; access by assignment only (case officer, investigators, HR Director), never by line management, and never to a party; least-loaded case officer assignment; investigation plans, notes and evidence; meetings with neutral invitations and minutes; a minuted hearing is required before any formal sanction; suspension, demotion and dismissal need HR Director approval; outcome letters filed as restricted documents the addressee can still read; responses and appeals decided by someone independent; warnings lapse automatically; deadlines and escalation; name-free trend reports |
| **Assets** | Register of tagged assets (laptops, phones, access cards) and issue of untagged uniforms/PPE; employee acknowledgment; transfers; loss/damage reporting; return with condition and recovery through payroll; outstanding-items dashboard including leavers |
| **Offboarding** | Resignation through self-service, other exits recorded by HR; notice period per the Labour Act with shortfall shown; approval (involuntary exits need the HR Director); clearance across supervisor, IT, admin, finance, HR and payroll with automatic checks (assets returned, loans and advances, exit interview, final payroll run); access revoked on the last day unless an approved extension applies; dismissals from ER cases start offboarding automatically; certificate of service; exit interviews; turnover analytics and upcoming retirements |
| **Engagement** | Engagement, pulse, stay and wellbeing surveys; anonymous responses stored with no link to the person; results only for groups of 5+ (smaller groups combined), shuffled unattributed comments; engagement index, eNPS, themes and workload/burnout risk by department; managers see their own area only; action plans; recognition wall; suggestion box (anonymous option, votes, HR responses); wellness, welfare and EAP events with registration |
| **Health & safety** | Incident and near-miss reporting by anyone (urgent alerts for needlestick/splash exposures and serious incidents); investigation, root cause, lost time, reportable-incident tracking; corrective actions with overdue reminders; 5x5 risk assessments with review dates; inspections with checklists; LTIFR, days since last lost-time injury and trends. **Occupational health records are a separate restricted zone** (OH professionals only, not even the HR Director): HR and rostering see only the fitness outcome and work restrictions, and staff marked unfit cannot be rostered for clinical duties |

### Phase 4 (in progress): Enterprise intelligence

| Area | Highlights |
|---|---|
| **Talent & succession** | Employee career profiles (aspirations, skills, mobility); nine-box talent reviews where performance is suggested from the latest appraisal and potential must be justified against published criteria with evidence (no opaque labelling); succession plans for critical positions with readiness levels; automatic flags for vacant critical roles, missing or not-ready successors, single-person dependencies and incumbents retiring within two years; bench strength; published career paths with transparent promotion eligibility (time in role, rating, required courses, qualification to verify) |
| **Workforce planning** | Establishment by department (approved, occupied, vacant, frozen, proposed) with budget vs actual cost; workforce plans by department and role with workload drivers (e.g. nurses per bed); what-if scenarios (attrition, pay rise, growth, department cuts, hiring freeze, budget cap); multi-year projection of retirements, attrition, hires needed and staff cost with employer on-cost read from the statutory rate table; skills shortages; plan approval by the HR Director and finance |

See [docs/ROADMAP.md](docs/ROADMAP.md).

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

Development uses SQLite, console email/SMS and synchronous Celery tasks by default. Demo usernames (admin, hrdirector, hrofficer, payroll, approver, manager, employee, auditor, recruiter, itsupport, newhire, safety, ohdoctor) and the shared demo password are listed at the top of `backend/apps/core/management/commands/seed_demo.py`. MFA is disabled for the demo organization only. The demo career site is at http://localhost:5173/careers/shinelight.

## Production (Docker on a VPS)

```bash
cp .env.example .env            # set SECRET_KEY, FIELD_ENCRYPTION_KEY, DB password, hosts, SMTP, SMS
docker compose up -d --build
docker compose exec backend python manage.py setup_organization --name "Your Organization" --code yourorg --admin admin --email you@org.com --features payroll,sms
```

Full runbook (TLS, backups, restore tests, monitoring, upgrades): [docs/OPERATIONS.md](docs/OPERATIONS.md). **Before paying anyone, work through [docs/GO_LIVE_CHECKLIST.md](docs/GO_LIVE_CHECKLIST.md)**: the statutory rates are seeded unverified.

## Tests

```bash
cd backend && .venv/Scripts/python -m pytest          # 106 tests: payroll golden figures, workflow, leave, RBAC, audit, attendance, service desk, expenses, compensation, e-signature, recruitment, onboarding, probation, performance, learning, employee relations, assets, offboarding, engagement, health & safety, talent and workforce planning
.venv/Scripts/python scripts/smoke_api.py              # every endpoint x every demo role (needs running server + seed_demo)
.venv/Scripts/python scripts/e2e_flow.py               # leave approval → payroll maker-checker → payslip PDF → GL balance
.venv/Scripts/python scripts/e2e_phase2.py             # ticket → letter → e-signature; travel advance → claim → payroll recovery; benefits
.venv/Scripts/python scripts/e2e_phase3.py             # vacancy → career-site application → offer approval → candidate accepts → hire → onboarding → requisition
.venv/Scripts/python scripts/e2e_performance.py        # cycle → objectives → self/manager review → calibration → release → acknowledgment → improvement plan
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
