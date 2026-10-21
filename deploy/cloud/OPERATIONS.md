# Running the ShineLight HRM cloud (multi-organization SaaS)

You host one installation; each customer organization gets its own address, `<code>.<SAAS_BASE_DOMAIN>`, or its
own custom domain. Their data is separated in the application, and PostgreSQL row-level security is the backstop.
Under Ghana's Data Protection Act, 2012 (Act 843) you are the data **processor** for every customer: sign a data
processing agreement with each, register with the Data Protection Commission, and keep the security measures
below in place.

## 1. Infrastructure

- Start with one VPS (8 vCPU / 16 GB / 200 GB SSD serves roughly 20,000 employees across organizations), in a
  region close to Ghana. Grow by moving PostgreSQL to a managed service with point-in-time recovery, then by
  adding worker containers.
- Object storage for documents (`USE_S3=True`, server-side encryption on).
- A transactional email provider and an SMS gateway account (Hubtel or Arkesel).
- DNS: `A` records for `shinelighthrm.com` **and** `*.shinelighthrm.com` pointing at the server.

## 2. First deployment

```bash
git clone <repository> /opt/shinelight && cd /opt/shinelight
git checkout <release tag>
cp deploy/cloud/env.example .env && nano .env      # fill in every change-me
docker compose up -d --build                       # creates the app DB role, migrates, applies RLS policies
docker compose exec backend python manage.py create_platform_admin <your-username> --email you@company.com
```

Sign in at `https://<SAAS_BASE_DOMAIN>/login` as the operator (you'll be asked to set up two-step verification).
The **platform console** lists organizations, plans and usage. Operators can't open any organization's HR data.

Check that row-level security is active:

```bash
docker compose exec db psql -U "$POSTGRES_USER" -d shinelight -c \
  "select count(*) from pg_policies where policyname = 'shinelight_tenant_isolation';"
```

## 3. Onboarding a customer

1. Platform console → **New organization**: name, address code (e.g. `korlebu`), administrator username and email,
   plan, trial or active. The administrator receives a temporary password by email.
2. Certificates are issued automatically the first time `https://korlebu.shinelighthrm.com` is opened.
3. **Custom domain** (optional): the customer creates a CNAME `hr.korlebu.gov.gh -> korlebu.shinelighthrm.com`;
   you set the domain on the organization in the console **and** add it to `ALLOWED_HOSTS` in `.env`, then
   `docker compose up -d`.
4. Their administrator signs in, changes the password, reviews the statutory tables (`docs/GO_LIVE_CHECKLIST.md`)
   and loads employees.

Plans set the employee cap and which modules an organization may switch on. Trials send a reminder three days
before they end and are suspended the day after. Suspending an organization signs its users out immediately; its
data is kept. Every operator action is recorded in that organization's own audit trail.

Self-service sign-up (`SAAS_SIGNUP_ENABLED=True`) creates trial organizations from `/signup`. Leave it off until
you have terms of service, a data processing agreement and abuse monitoring in place.

## 4. Backups

The root `scripts/backup.sh` works unchanged (it dumps the whole database as the superuser, so row-level
security doesn't hide anything):

```bash
0 1 * * * cd /opt/shinelight && BACKUP_PASSPHRASE='...' scripts/backup.sh && rclone copy backups remote:shinelight-backups
```

With managed PostgreSQL, also keep its point-in-time recovery switched on. Restores are whole-installation;
restoring one customer means restoring to a staging copy and exporting that organization's data from there.
Test a restore every quarter.

## 5. Upgrades

All customers upgrade together, so use staging first:

```bash
scripts/backup.sh
git fetch --tags && git checkout <new release tag>
docker compose up -d --build        # migrations run, then RLS policies are re-applied to any new tables
```

Announce maintenance windows to customer administrators, and avoid month-end payroll days.

## 6. Monitoring and security

- Uptime: `https://<SAAS_BASE_DOMAIN>/api/health/` returns `{"status": "ok", "edition": "cloud"}`.
- Logs: `docker compose logs -f backend worker beat caddy`; ship them to a log service.
- The application must keep connecting as `APP_DB_USER`. A superuser connection would silently bypass
  row-level security.
- Rotate the operator accounts' passwords and keep two-step verification on. Give operators separate accounts;
  never share one.
- Before each release run the test suite, including `apps/tenancy/tests.py`, which crawls every endpoint with a
  second organization present.
