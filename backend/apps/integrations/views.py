from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.audit import services as audit
from apps.core.serializers import TenantSerializer
from apps.core.views import TenantModelViewSet

from .models import EVENTS, ApiKey, Webhook, WebhookDelivery
from .services import deliver


class ApiKeySerializer(TenantSerializer):
    service_user_name = serializers.CharField(source="service_user.__str__", read_only=True)

    class Meta(TenantSerializer.Meta):
        model = ApiKey
        exclude = ["organization", "key_hash"]
        read_only_fields = TenantSerializer.Meta.read_only_fields + ["prefix", "last_used_at"]


class ApiKeyViewSet(TenantModelViewSet):
    queryset = ApiKey.objects.select_related("service_user")
    serializer_class = ApiKeySerializer
    perm_module = "integrations"
    perm_read = "integrations.manage"
    perm_write = "integrations.manage"
    pagination_class = None

    def create(self, request, *args, **kwargs):
        s = self.get_serializer(data=request.data)
        s.is_valid(raise_exception=True)
        raw, prefix, digest = ApiKey.generate()
        key = s.save(prefix=prefix, key_hash=digest)
        audit.log("create", key, {"api_key": prefix})
        data = self.get_serializer(key).data
        data["key"] = raw  # shown once
        return Response(data, status=201)


class WebhookSerializer(TenantSerializer):
    class Meta(TenantSerializer.Meta):
        model = Webhook
        extra_kwargs = {"secret": {"write_only": True, "required": False}}

    def validate_events(self, events):
        valid = {c for c, _ in EVENTS}
        bad = [e for e in events if e not in valid]
        if bad:
            raise serializers.ValidationError(f"Unknown events: {', '.join(bad)}")
        return events


class WebhookViewSet(TenantModelViewSet):
    queryset = Webhook.objects.all()
    serializer_class = WebhookSerializer
    perm_module = "integrations"
    perm_read = "integrations.manage"
    perm_write = "integrations.manage"
    pagination_class = None

    @action(detail=False)
    def events(self, request):
        return Response([{"code": c, "label": n} for c, n in EVENTS])

    @action(detail=True)
    def deliveries(self, request, pk=None):
        hook = self.get_object()
        return Response([{"id": d.id, "event": d.event, "status": d.status, "attempts": d.attempts,
                          "response_code": d.response_code, "error": d.error, "created_at": d.created_at}
                         for d in hook.deliveries.all()[:100]])

    @action(detail=True, methods=["post"], url_path=r"retry/(?P<delivery_id>\d+)")
    def retry(self, request, pk=None, delivery_id=None):
        d = WebhookDelivery.objects.get(pk=delivery_id, webhook_id=pk)
        d.status = "pending"
        deliver(d)
        return Response({"status": d.status})
