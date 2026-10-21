# Releasing ShineLight HRM

Both editions ship from the same tagged release. Customers on the self-hosted edition upgrade by checking out the
new tag; the cloud is upgraded by you, after staging.

## Version numbers

`VERSION` (repository root) holds the version, e.g. `1.2.0`. It is shown in the app's menu and returned by
`/api/health/`.

- **PATCH** (1.0.**1**): fixes only, no new settings or manual steps.
- **MINOR** (1.**1**.0): new features; migrations are fine; no manual steps for customers.
- **MAJOR** (**2**.0.0): anything that needs customer action beyond a normal upgrade (new required setting,
  data conversion, dropped feature). Spell the steps out in the changelog.

## Checklist

1. **Branch:** release work happens on a branch; `main` only moves by fast-forward or pull request.
2. **Checks pass locally and in CI** (CI runs the same):
   ```bash
   cd backend
   .venv/Scripts/ruff check apps config --select F,E9
   .venv/Scripts/python manage.py makemigrations --check --dry-run
   .venv/Scripts/python -m pytest -p no:cacheprovider --create-db       # also once with DATABASE_URL=postgres://...
   .venv/Scripts/python -m pip_audit -r requirements.txt
   cd ../frontend
   npx tsc -p tsconfig.json --noEmit && npm test && npm run build
   npm audit --omit=dev --audit-level=high
   ```
   Run `scripts/smoke_api.py` and the e2e scripts against a seeded server.
3. **Migrations reviewed:** anything that rewrites a large table or can't be reversed is called out in the changelog.
4. **Statutory tables:** if PAYE bands or SSNIT rates changed, ship them as new effective-dated rows, never by
   editing old ones.
5. **Bump `VERSION`** and add a `CHANGELOG.md` section with the date, what changed, and any upgrade steps.
6. **Staging:** deploy the release candidate to a staging server of each edition, upgrade from the previous
   release, and check sign-in, a payroll calculation, a document download and the health endpoint.
7. **Tag and push:**
   ```bash
   git tag -a v1.2.0 -m "ShineLight HRM 1.2.0"
   git push origin main v1.2.0
   ```
8. **Announce:** send self-hosted customers the changelog section and the upgrade command; schedule the cloud
   upgrade outside payroll week and tell cloud customers' administrators.

## Hotfixes

Branch from the release tag (`git switch -c hotfix-1.2.1 v1.2.0`), fix, bump PATCH, tag, then merge the fix
back into `main`.
