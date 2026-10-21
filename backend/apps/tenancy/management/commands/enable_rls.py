from django.core.management.base import BaseCommand
from django.db import connection

from apps.tenancy import rls


class Command(BaseCommand):
    help = "Apply (or with --remove, drop) PostgreSQL row-level security policies on every tenant table."

    def add_arguments(self, parser):
        parser.add_argument("--remove", action="store_true")

    def handle(self, *args, **opts):
        if connection.vendor != "postgresql":
            self.stdout.write(self.style.WARNING("Row-level security needs PostgreSQL; nothing to do."))
            return
        n = rls.remove() if opts["remove"] else rls.apply()
        verb = "Removed policies from" if opts["remove"] else "Protected"
        self.stdout.write(self.style.SUCCESS(f"{verb} {n} tenant tables."))
        if not opts["remove"]:
            self.stdout.write("Set DB_ROW_LEVEL_SECURITY=True and connect as a non-superuser role without BYPASSRLS.")
