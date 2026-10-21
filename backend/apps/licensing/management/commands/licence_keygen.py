import base64
import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = ("VENDOR ONLY. Create the Ed25519 key pair used to sign licences. Keep the private key off customer "
            "servers and out of the repository; add the printed public key to apps/licensing/keys.py.")

    def add_arguments(self, parser):
        parser.add_argument("--out", required=True, help="Where to write the private key (PEM).")

    def handle(self, *args, **opts):
        out = Path(opts["out"]).expanduser()
        if out.exists():
            raise CommandError(f"{out} already exists; refusing to overwrite a signing key.")
        key = Ed25519PrivateKey.generate()
        pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption())
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(pem)
        try:
            os.chmod(out, 0o600)
        except OSError:
            pass
        raw = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        self.stdout.write(self.style.SUCCESS(f"Private key written to {out}. Back it up in a password manager."))
        self.stdout.write(f"Public key (add to TRUSTED_PUBLIC_KEYS): {base64.urlsafe_b64encode(raw).decode().rstrip('=')}")
