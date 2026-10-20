"""Pluggable SMS gateways for Ghana (Hubtel, Arkesel) plus a console provider for development."""

import logging

import requests
from django.conf import settings

from apps.core.validators import normalize_gh_phone

logger = logging.getLogger(__name__)


class SmsProvider:
    name = "base"

    def send(self, to: str, message: str) -> str:
        raise NotImplementedError


class ConsoleProvider(SmsProvider):
    name = "console"

    def send(self, to, message):
        logger.info("SMS to %s: %s", to, message)
        print(f"[SMS] to={to} msg={message}")
        return "console"


class HubtelProvider(SmsProvider):
    name = "hubtel"
    url = "https://smsc.hubtel.com/v1/messages/send"

    def send(self, to, message):
        resp = requests.get(self.url, params={
            "clientid": settings.HUBTEL_CLIENT_ID, "clientsecret": settings.HUBTEL_CLIENT_SECRET,
            "from": settings.SMS_SENDER_ID, "to": to.lstrip("+"), "content": message,
        }, timeout=15)
        resp.raise_for_status()
        return str(resp.json().get("messageId", ""))


class ArkeselProvider(SmsProvider):
    name = "arkesel"
    url = "https://sms.arkesel.com/api/v2/sms/send"

    def send(self, to, message):
        resp = requests.post(self.url, headers={"api-key": settings.ARKESEL_API_KEY}, json={
            "sender": settings.SMS_SENDER_ID[:11], "message": message, "recipients": [to.lstrip("+")],
        }, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") not in ("success", "ok"):
            raise RuntimeError(f"Arkesel error: {data}")
        return str(data.get("data", [{}])[0].get("id", "")) if isinstance(data.get("data"), list) else ""


PROVIDERS = {p.name: p for p in (ConsoleProvider, HubtelProvider, ArkeselProvider)}


def get_provider() -> SmsProvider:
    return PROVIDERS.get(settings.SMS_PROVIDER, ConsoleProvider)()


def send_sms(to: str, message: str) -> str:
    return get_provider().send(normalize_gh_phone(to), message)
