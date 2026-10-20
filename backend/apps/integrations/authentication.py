import hashlib

from django.utils import timezone
from rest_framework import exceptions
from rest_framework.authentication import BaseAuthentication

from apps.core.context import set_current_org, set_current_user
from apps.core.middleware import client_ip


class ApiKeyAuthentication(BaseAuthentication):
    """`Authorization: Api-Key slk_...` for integrations (finance, BI, identity systems)."""

    keyword = "Api-Key"

    def authenticate(self, request):
        from .models import ApiKey

        header = request.META.get("HTTP_AUTHORIZATION", "")
        if not header.startswith(self.keyword + " "):
            return None
        raw = header[len(self.keyword) + 1:].strip()
        key = ApiKey.all_objects.filter(prefix=raw[:12], is_active=True).select_related("service_user").first()
        if key is None or hashlib.sha256(raw.encode()).hexdigest() != key.key_hash:
            raise exceptions.AuthenticationFailed("Invalid API key.")
        if key.expires_at and key.expires_at < timezone.now():
            raise exceptions.AuthenticationFailed("API key expired.")
        if key.allowed_ips and client_ip(request) not in key.allowed_ips:
            raise exceptions.AuthenticationFailed("IP address not allowed for this key.")
        user = key.service_user
        if not user.is_active:
            raise exceptions.AuthenticationFailed("Service account disabled.")
        ApiKey.all_objects.filter(pk=key.pk).update(last_used_at=timezone.now())
        set_current_user(user)
        set_current_org(user.organization)
        return user, key

    def authenticate_header(self, request):
        return self.keyword
