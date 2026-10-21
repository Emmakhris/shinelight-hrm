from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.core.exceptions import BusinessRuleError
from apps.licensing.services import install


class Command(BaseCommand):
    help = "Install a licence file on this server (the same as Administration > Licence)."

    def add_arguments(self, parser):
        parser.add_argument("path")

    def handle(self, *args, **opts):
        try:
            s = install(Path(opts["path"]).read_text(encoding="utf-8"))
        except BusinessRuleError as exc:
            raise CommandError(exc.message) from exc
        self.stdout.write(self.style.SUCCESS(f"Licence installed: {s['state']}, expires {s.get('expires')}."))
