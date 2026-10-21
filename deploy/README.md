# Deploying ShineLight HRM

One codebase, two editions. Pick the kit that matches how the customer will use it; the code and releases are
the same, so a fix or a tax-table update ships to both.

| | Self-hosted | Cloud |
|---|---|---|
| Who runs the server | The customer (on premises or their own cloud account) | You |
| Organizations | One | Many, each at `<code>.<your domain>` or its own domain |
| Where HR data lives | On the customer's server | On your server (you are the data processor under Act 843) |
| Operator console, plans, trials, sign-up | Off | On |
| PostgreSQL row-level security | Not needed | On |
| HTTPS | Let's Encrypt, or an internal certificate for office-only networks | Certificates issued per organization on demand |
| Upgrades | Per customer, when they're ready | Everyone at once |
| Kit | [`self-hosted/INSTALL.md`](self-hosted/INSTALL.md) | [`cloud/OPERATIONS.md`](cloud/OPERATIONS.md) |

Both kits extend the root `docker-compose.yml`: the `.env` you copy from the kit sets `COMPOSE_FILE`, so the
usual `docker compose ...` commands and `scripts/backup.sh` / `scripts/restore.sh` work without extra flags.
The edition is chosen by `DEPLOYMENT_MODE` (`self_hosted` or `cloud`); `/api/health/` reports which one is running.
