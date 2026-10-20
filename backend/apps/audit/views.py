from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.core.context import get_current_org
from apps.rbac.permissions import require

from .models import AuditLog
from .services import verify_chain


class AuditLogSerializer(serializers.ModelSerializer):
    model = serializers.SerializerMethodField()

    class Meta:
        model = AuditLog
        fields = ["id", "timestamp", "actor", "actor_repr", "ip_address", "action", "model", "object_id",
                  "object_repr", "changes", "message"]

    def get_model(self, obj):
        return obj.content_type.model if obj.content_type_id else None


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AuditLogSerializer
    permission_classes = [IsAuthenticated, require("audit.view")]
    filterset_fields = ["action", "actor", "object_id", "content_type__model"]
    search_fields = ["object_repr", "actor_repr", "message"]

    def get_queryset(self):
        qs = AuditLog.objects.filter(organization=get_current_org()).select_related("content_type")
        p = self.request.query_params
        if p.get("start"):
            qs = qs.filter(timestamp__date__gte=p["start"])
        if p.get("end"):
            qs = qs.filter(timestamp__date__lte=p["end"])
        return qs

    @action(detail=False)
    def verify(self, request):
        ok, bad = verify_chain(get_current_org().id)
        return Response({"intact": ok, "first_invalid_entry": bad,
                         "entries": AuditLog.objects.filter(organization=get_current_org()).count()})

    @action(detail=False, url_path="access-review")
    def access_review(self, request):
        """Data-access review: who holds sensitive permissions (for periodic review / role changes)."""
        from apps.rbac.models import RoleAssignment

        rows = []
        for ra in RoleAssignment.objects.select_related("user", "role", "user__employee").prefetch_related(
                "role__permissions"):
            sensitive = [p.code for p in ra.role.permissions.all() if p.is_sensitive]
            if not sensitive:
                continue
            emp = getattr(ra.user, "employee", None)
            rows.append({"user": str(ra.user), "username": ra.user.username, "active": ra.user.is_active,
                         "employee_status": emp.status if emp else None, "role": ra.role.name,
                         "scope": ra.effective_scope, "sensitive_permissions": sensitive,
                         "last_login": ra.user.last_login,
                         "flag": "Exited employee still holds access" if emp and emp.status == "exited" and
                         ra.user.is_active else ""})
        return Response(rows)
