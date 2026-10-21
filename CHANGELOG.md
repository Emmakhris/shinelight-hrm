# Changelog

All notable changes to ShineLight HRM. Versions follow [semantic versioning](https://semver.org/):
MAJOR for changes that need customer action beyond a normal upgrade, MINOR for new features, PATCH for fixes.
Self-hosted customers upgrade by checking out the new tag (see `deploy/self-hosted/INSTALL.md`).

## [1.0.0] - 2026-10-21

First release.

### Core HR and payroll
- Organization structure, positions and establishment, employee records with effective-dated history, contracts,
  documents with retention and legal hold, letters, e-signature, bulk import.
- Leave (accrual, carry-over, Ghana public holidays), attendance with ZKTeco devices and geofenced clock-in.
- Ghana payroll: PAYE, SSNIT tiers, reliefs, loans, maker-checker approval, bank files, journals, payslips.
  Statutory tables are seeded **unverified**: confirm them before the first live payroll (`docs/GO_LIVE_CHECKLIST.md`).
- Configurable approval workflows, notifications (email, SMS, in-app), hash-chained audit trail.

### Employee lifecycle
- HR service desk, travel and expenses, compensation and benefits.
- Recruitment with a public career site and offer acceptance, onboarding and probation, performance and 360
  feedback, learning and CPD, employee relations, assets, offboarding and clearance, engagement surveys,
  health and safety with a restricted occupational-health zone.
- Optional hospital module: professional licences, competency matrix, ward staffing.

### Planning, analytics and AI
- Talent reviews, succession, career paths, workforce planning with scenarios.
- Report builder, turnover and retirement forecasts, transparent attrition-risk indicators.
- Single sign-on with OpenID Connect (Microsoft 365, Google Workspace, Okta).
- Governed AI assistant (off by default).

### Editions
- **Self-hosted**: one organization on the customer's server, signed licence files (`docs/LICENSING.md`).
- **Cloud**: multi-organization SaaS with host-based routing, platform operator console, plans and trials,
  PostgreSQL row-level security.
- Install kits in `deploy/`.

### Security
- Security review before release: production refuses to start with development secrets; client IP taken only
  from trusted proxies (`TRUSTED_PROXY_COUNT`); uploaded files served with a type derived from their extension
  and only PDFs and images shown inline; administrator-configured URLs (webhooks, SSO) can't reach internal
  addresses in the cloud edition; SSO return paths can't leave the site; Content-Security-Policy header;
  vulnerable frontend dependencies upgraded. Details in `docs/SECURITY.md`.
- Fixed: organization-wide HR users could not see employees' documents in the documents list.
