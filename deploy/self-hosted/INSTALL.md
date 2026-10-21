# Installing ShineLight HRM on a customer's server (self-hosted edition)

One organization, running entirely on the customer's own server. Their HR data never leaves their premises.

## 1. Server

| Staff | CPU / RAM / disk |
|---|---|
| up to 500 | 2 vCPU, 4 GB, 60 GB SSD |
| up to 2,000 | 4 vCPU, 8 GB, 100 GB SSD |
| more | 8 vCPU, 16 GB, plus a separate managed PostgreSQL |

- Ubuntu Server 24.04 LTS (recommended), or any Linux with Docker Engine and the compose plugin (v2.24 or later).
  Windows Server works with Docker Desktop but Linux is simpler to support.
- A fixed IP on the office network, and a host name staff will use, e.g. `hr.korlebu.gov.gh` or `hr.clinic.local`.
- Firewall (`ufw`): allow 22 (SSH, keys only), 80 and 443. Nothing else.
- A UPS: an unclean power loss during a payroll run is the most common cause of trouble on site.

## 2. Install

```bash
sudo apt update && sudo apt install -y docker.io docker-compose-v2 git
git clone <repository> /opt/shinelight && cd /opt/shinelight
git checkout <release tag, e.g. v1.0.0>
cp deploy/self-hosted/env.example .env
nano .env                       # fill in every change-me; set SITE_ADDRESS and the matching URLs
docker compose up -d --build    # first build takes a few minutes
docker compose exec backend python manage.py setup_organization \
    --name "Korle Bu Teaching Hospital" --code korlebu --admin hradmin --email hr@korlebu.gov.gh \
    --features payroll,sms,hospital
```

`setup_organization` asks for the administrator's password, then seeds Ghana defaults: roles, leave types,
public holidays, PAYE/SSNIT tables (**unverified**: confirm them with the customer's payroll team, see
`docs/GO_LIVE_CHECKLIST.md`), approval workflows and letter templates. The self-hosted edition refuses to
create a second organization.

Open `https://<SITE_ADDRESS>` and sign in as the administrator.

### Licence

Until a licence is installed the system runs in evaluation mode (up to 25 active employees). Install the
customer's `.lic` file under **Administration → Licence**, or on the server:

```bash
docker compose cp korlebu-2027.lic backend:/tmp/ && docker compose exec backend python manage.py install_licence /tmp/korlebu-2027.lic
```

The licence is checked on the server; nothing is sent anywhere. Administrators are reminded before it expires.
After expiry and a grace period the system becomes read-only until a renewal is installed (data stays viewable
and exportable). How to issue licences: `docs/LICENSING.md`.

## 3. HTTPS

- **Reachable from the internet** (`TLS_MODE=public`): point the DNS name at the server; Caddy obtains and renews
  a Let's Encrypt certificate automatically.
- **Office network only** (`TLS_MODE=internal`): Caddy issues its own certificate. Install its root certificate on
  staff devices once so browsers trust it:
  ```bash
  docker compose cp caddy:/data/caddy/pki/authorities/local/root.crt ./shinelight-root.crt
  ```
  Distribute `shinelight-root.crt` through Group Policy / MDM, or install it manually on each device.
  The mobile app (PWA) needs HTTPS to install, so don't skip this.

## 4. Backups (do this before go-live)

```bash
sudo crontab -e
# 01:00 daily encrypted backup of the database and documents
0 1 * * * cd /opt/shinelight && BACKUP_PASSPHRASE='...' scripts/backup.sh >> /var/log/shinelight-backup.log 2>&1
```

- Copy `./backups` off the server every day (a NAS, an external drive rotated weekly, or cloud storage with rclone).
  A backup that only exists on the same server is not a backup.
- Keep `BACKUP_PASSPHRASE`, `FIELD_ENCRYPTION_KEY` and `SECRET_KEY` in the customer's password manager.
- Test a restore every quarter on a spare machine: `scripts/restore.sh backups/db-....dump.enc backups/media-....tgz.enc`.

## 5. Upgrades

```bash
cd /opt/shinelight
scripts/backup.sh                    # always back up first
git fetch --tags && git checkout <new release tag>
docker compose up -d --build         # migrations run automatically
```

Read the release notes first; never upgrade during a payroll run. For sites without internet access, build the
images elsewhere and move them with `docker save` / `docker load`.

## 6. Optional

- **Single sign-on** with the customer's Microsoft 365 / Google Workspace: Administration → Single sign-on.
- **AI assistant**: put the customer's own Anthropic key in `ANTHROPIC_API_KEY`, restart (`docker compose up -d`),
  then enable it in Organization settings → Features. Policy-only mode keeps all personal data on the server.
- **Biometric devices** (ZKTeco): they must be reachable from the server on the office network.
- Health check for monitoring: `https://<SITE_ADDRESS>/api/health/` returns `{"status": "ok", "edition": "self_hosted"}`.
