# Licensing the self-hosted edition (vendor guide)

Self-hosted customers run ShineLight HRM on their own servers. A **signed licence file** sets what they may use:
an employee cap, the modules, and an expiry date. The cloud edition doesn't use licences; it uses plans.

## How it works

- You sign licences with your **Ed25519 private key**. The product contains only the matching **public key**
  (`backend/apps/licensing/keys.py`), so an installation can check a licence offline but nobody can change the
  cap, modules or expiry without breaking the signature.
- A licence can be bound to the customer's organization code, so it can't be reused on someone else's server.
- On the customer's server:

| State | What happens |
|---|---|
| No licence | Evaluation: up to 25 active employees, all modules |
| Active | The licence's employee cap and modules apply; modules not licensed can't be switched on |
| 60, 30, 7 and 1 day before expiry | Administrators get an email and a banner |
| Expired, within the grace period (30 days by default) | Everything still works; weekly reminders |
| After the grace period | Read-only: everyone can still sign in, view and export, but changes are refused until a renewal is installed |

Data is never locked away and nothing phones home.

## Your signing key

The key pair was created with:

```bash
python manage.py licence_keygen --out ~/.shinelight/licence-signing-key.pem
```

The current private key is at `C:\Users\kwame\.shinelight\licence-signing-key.pem` on the machine where it was
generated. **Back it up now** (password manager or an encrypted USB key kept offline).
- Never commit it, email it or copy it to a customer server. `*.pem` and `*.lic` are git-ignored.
- If you lose it you can't issue licences that existing releases accept. Generate a new pair, add the new
  public key to `keys.py` and ship a release, then re-issue licences.
- If it leaks, anyone can mint licences: rotate the same way, and remove the old public key from `keys.py` once
  customers have new licences.

## Issuing a licence

```bash
cd backend
.venv/Scripts/python manage.py issue_licence \
    --customer "Korle Bu Teaching Hospital" --organization korlebu \
    --employees 1500 --features payroll,sms,hospital,biometric \
    --expires 2027-12-31 \
    --key ~/.shinelight/licence-signing-key.pem --out korlebu-2027.lic
```

- `--organization` must match the code the customer used in `setup_organization`.
- `--employees 0` means unlimited.
- Modules: `payroll`, `hospital`, `sms`, `biometric`, `geofence`, `ai_assistant`.
- The command checks the new file against the product's public keys before writing it.

Send the `.lic` file to the customer. Their administrator installs it under **Administration → Licence**
(upload or paste), or on the server:

```bash
docker compose exec backend python manage.py install_licence /path/to/korlebu-2027.lic
```

To renew or upgrade (more employees, extra modules), issue a new file with a later expiry and send it the same way.
Installing it replaces the old one immediately and lifts read-only mode if it was on.
