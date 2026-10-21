import datetime as dt
import uuid
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.licensing.services import parse, sign
from apps.tenancy.models import OrganizationFeature


class Command(BaseCommand):
    help = "VENDOR ONLY. Issue a signed licence file for a self-hosted customer."

    def add_arguments(self, parser):
        parser.add_argument("--customer", required=True, help='Legal name, e.g. "Korle Bu Teaching Hospital"')
        parser.add_argument("--organization", default="", help="Organization code to bind to (recommended).")
        parser.add_argument("--employees", type=int, required=True, help="Active-employee cap (0 = unlimited).")
        parser.add_argument("--features", default="payroll,sms", help="Comma list of modules.")
        parser.add_argument("--expires", required=True, help="YYYY-MM-DD")
        parser.add_argument("--grace-days", type=int, default=30)
        parser.add_argument("--key", required=True, help="Path to the vendor private key (PEM).")
        parser.add_argument("--out", required=True, help="Where to write the licence file.")

    def handle(self, *args, **opts):
        known = dict(OrganizationFeature.FEATURES)
        features = [f.strip() for f in opts["features"].split(",") if f.strip()]
        unknown = [f for f in features if f not in known]
        if unknown:
            raise CommandError(f"Unknown features: {', '.join(unknown)}. Known: {', '.join(known)}")
        try:
            expires = dt.date.fromisoformat(opts["expires"])
        except ValueError as exc:
            raise CommandError("--expires must be YYYY-MM-DD") from exc
        payload = {"licence_id": str(uuid.uuid4()), "customer": opts["customer"], "organization": opts["organization"],
                   "max_employees": opts["employees"], "features": features, "issued": str(dt.date.today()),
                   "expires": str(expires), "grace_days": opts["grace_days"], "edition": "self_hosted"}
        text = sign(payload, Path(opts["key"]).expanduser().read_bytes())
        parse(text)                                     # fails here if the key isn't one the product trusts
        Path(opts["out"]).write_text(text, encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(f"Licence {payload['licence_id']} for {opts['customer']} written to {opts['out']}."))
