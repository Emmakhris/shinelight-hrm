import getpass

from django.core.management.base import BaseCommand

from apps.core.setup import setup_organization


class Command(BaseCommand):
    help = "Create/refresh an organization with default roles, policies, Ghana statutory tables and workflows."

    def add_arguments(self, parser):
        parser.add_argument("--name", required=True)
        parser.add_argument("--code", required=True)
        parser.add_argument("--admin", help="Admin username to create")
        parser.add_argument("--email", default="")
        parser.add_argument("--features", default="payroll", help="Comma list: payroll,hospital,sms,biometric,geofence")

    def handle(self, *args, **opts):
        password = None
        if opts["admin"]:
            password = getpass.getpass(f"Password for {opts['admin']}: ")
        org, admin = setup_organization(opts["name"], opts["code"], opts["admin"], password, opts["email"],
                                        [f.strip() for f in opts["features"].split(",") if f.strip()])
        self.stdout.write(self.style.SUCCESS(f"Organization '{org.name}' ready."))
        self.stdout.write(self.style.WARNING(
            "Statutory PAYE/SSNIT tables are seeded UNVERIFIED. Review Payroll > Statutory settings before go-live."))
