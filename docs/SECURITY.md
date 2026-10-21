# Security notes

## Reporting a vulnerability

Email the maintainers privately (do not open a public issue) with steps to reproduce. Expect an acknowledgement
within three working days.

## Security review for v1.0.0 (October 2026)

Scope: authentication and sessions, permissions and data scope, multi-organization isolation, public endpoints
(career site, offer links, sign-up, SSO, TLS check), file upload and download, outbound HTTP, settings, and
third-party dependencies.

### Fixed before release

| # | Finding | Severity | Fix |
|---|---|---|---|
| 1 | Production started silently with the development `SECRET_KEY` (forgeable login tokens) and with field encryption derived from it | High | Startup is refused with `DEBUG=False` unless both keys are set |
| 2 | Client IP read from the first `X-Forwarded-For` entry, which the browser controls: login rate limits and API-key IP allowlists could be bypassed, audit IPs spoofed | High | Only entries added by our own proxies are trusted (`TRUSTED_PROXY_COUNT`, also used by DRF throttling) |
| 3 | Downloads used the content type the uploader's browser claimed, so a `.pdf` uploaded as `text/html` could run script on the app's domain (stored XSS) | High | Type derived from the allow-listed extension; only PDFs and images are shown inline |
| 4 | In the cloud edition an organization administrator could point a webhook or SSO issuer at internal addresses (database, metadata service) and read part of the response (SSRF) | High (cloud) | HTTPS and public addresses only, no redirects followed; self-hosted still allows its own network |
| 5 | SSO `next` accepted `/\evil.com`, which browsers treat as another site (open redirect) | Medium | Backslashes and any host part rejected |
| 6 | No Content-Security-Policy | Low (hardening) | Strict CSP in `docker/nginx.conf` (scripts from the same origin only) |
| 7 | Production dependencies with known high-severity advisories (`axios`, `react-router`) | High | Upgraded |
| 8 | Organization-wide HR users could not see employees' documents in the documents list (functional bug found during the review) | n/a | Fixed |

Regression tests: `backend/apps/core/test_security.py`; isolation between organizations:
`backend/apps/tenancy/tests.py` (crawls every endpoint and every record by id with a second organization present).

### Accepted for now

- `vitest` / `tinypool` advisories (critical): they affect only the developer test runner, never shipped code.
  Fixing needs the next major version of vitest; do it with the next tooling upgrade.
- `react-router` advisories (moderate): open redirect when navigating to attacker-supplied paths, and an issue in
  server-rendered data routers. The app uses neither (all navigation targets are fixed in code). Fixing needs
  React Router 7.
- Letter templates are Django templates edited by users with `documents.manage`; Django's template language can't
  run arbitrary code or call data-changing methods, but keep that permission to trusted HR administrators.
- `/django-admin/` is reachable through nginx for superusers. Restrict it by IP or remove the location if unused.

### Already in place (verified)

Cookie-based JWT with HttpOnly cookies, CSRF checks for cookie-authenticated writes, refresh-token rotation and
blacklisting; MFA for HR, payroll, finance, audit and admin roles; account lockout and login throttling; generic
password-reset responses; permission and data-scope checks on every viewset; field masking for salary, bank and
personal data; encrypted bank account numbers; append-only hash-chained audit log including exports and
downloads; anonymous survey responses; uploaded media never served directly; random 256-bit offer tokens;
multi-organization isolation in the application and in PostgreSQL (row-level security).
