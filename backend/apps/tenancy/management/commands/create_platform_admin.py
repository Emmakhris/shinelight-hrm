import getpass

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Create a platform operator: manages organizations and plans, cannot see any organization's HR data."

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("--email", default="")

    def handle(self, *args, **opts):
        from django.conf import settings

        if settings.DEPLOYMENT_MODE != "cloud":
            raise CommandError("Platform operators exist only in the cloud edition (DEPLOYMENT_MODE=cloud).")
        User = get_user_model()
        if User.objects.filter(username__iexact=opts["username"]).exists():
            raise CommandError("That username is already in use.")
        password = getpass.getpass("Password: ")
        User.objects.create_user(opts["username"], opts["email"], password, organization=None,
                                 is_platform_admin=True, mfa_enabled=True)
        self.stdout.write(self.style.SUCCESS("Platform operator created. Two-step verification is required at sign-in."))
