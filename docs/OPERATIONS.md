# Operations runbook

## 1. Server

- **VPS:** Ubuntu 24.04 LTS, 4 vCPU / 8 GB RAM / 80 GB SSD (comfortably serves about 2,000 employees).
- **Software:** Docker Engine plus the compose plugin. Open only ports 22 (SSH, key-only) and 80/443 in the firewall (`ufw`).
- **Environments:** keep separate **staging** and **production** servers or compose projects with separate databases and `.env` files. Never test on production data.

## 2. First deployment

```bash
git clone <repo> /opt/shinelight && cd /opt/shinelight
cp .env.example .env && nano .env        # see comments in the file
docker compose up -d --build
docker compose exec backend python manage.py setup_organization --name "..." --code org --admin admin --email hr@org.com --features payroll,sms,biometric
```

**TLS:** put a TLS terminator in front of the `frontend` container, e.g. Caddy (`reverse_proxy localhost:80`) or nginx with certbot. Forward `X-Forwarded-Proto: https`. Keep `AUTH_COOKIE_SECURE=True` and HSTS on.

## 3. Backups (RPO 24h, target RTO 4h)

- `scripts/backup.sh` writes AES-256 encrypted database and document archives to `./backups`.
  - Cron: `0 1 * * * BACKUP_PASSPHRASE=... /opt/shinelight/scripts/backup.sh`.
  - Before payroll runs, also take a manual backup.
- **Off-site copy is mandatory:** e.g. `rclone copy ./backups remote:shinelight-backups` after each run.
- **Store separately from the server:**
  - `BACKUP_PASSPHRASE`
  - `FIELD_ENCRYPTION_KEY` (bank numbers cannot be decrypted without it)
  - `SECRET_KEY`
- **Restore test, quarterly, on staging:** `scripts/restore.sh backups/db-....dump.enc backups/media-....tgz.enc`. The script finishes by verifying the audit chain. Record the date, the duration (your actual RTO) and any issues.
- For tighter RPO, enable PostgreSQL WAL archiving (e.g. pgBackRest) or use a managed PostgreSQL service with point-in-time recovery.

## 4. Disaster recovery

1. Provision a new VPS and install Docker.
2. Restore `.env` from the secret store.
3. `docker compose up -d db redis`, then run `restore.sh` with the latest off-site backup.
4. `docker compose up -d`, update DNS, and verify:
   - sign-in;
   - the latest payroll run;
   - `GET /api/audit/logs/verify/`.
5. Notify users. Record the incident in your incident log.

## 5. Monitoring

- Health: `GET /api/health/` (checks DB). Point an uptime monitor (UptimeRobot, Better Stack) at it.
- Logs: `docker compose logs -f backend worker beat`. Ship them to a log service for retention.
- Watch:
  - failed logins (Admin → Users → Login monitoring);
  - SMS/email failures (Admin → Notifications → Delivery log);
  - webhook failures;
  - the device sync status of each biometric terminal.

## 6. Upgrades

```bash
scripts/backup.sh
git pull
docker compose build
docker compose up -d          # migrations run automatically in the backend container
```

Apply OS and Docker security updates monthly. Run `pip-audit` and `npm audit` on each release (CI does this).

## 7. Security operations

- Every HR or payroll officer has an individual account. Shared logins are prohibited.
- MFA is required for HR, payroll, finance, audit and admin roles (Roles → "Require two-step verification").
- **Quarterly access review:** Audit trail → Sensitive access review. Remove access for movers and leavers; exits disable accounts automatically on the exit date.
- **Bulk exports:** users without export permission must request approval, and every export is logged.
- **Incident response:**
  1. Contain: disable the affected accounts and revoke API keys.
  2. Preserve the audit log and run verify.
  3. Assess personal data impact.
  4. Notify the Data Protection Commission and affected individuals as required by Act 843.
  5. Remediate and review.
