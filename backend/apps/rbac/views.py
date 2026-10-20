from rest_framework import serializers, viewsets
from rest_framework.permissions import IsAuthenticated

from apps.audit import services as audit
from apps.core.serializers import TenantSerializer
from apps.core.views import TenantModelViewSet
from apps.rbac.permissions import require

from .models import Permission, Role, RoleAssignment
from .services import clear_cache


class PermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Permission
        fields = ["id", "code", "name", "module", "is_sensitive"]


class PermissionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Permission.objects.all()
    serializer_class = PermissionSerializer
    permission_classes = [IsAuthenticated, require("admin.roles")]
    pagination_class = None


class RoleSerializer(TenantSerializer):
    permissions = serializers.SlugRelatedField(slug_field="code", many=True, queryset=Permission.objects.all())
    user_count = serializers.IntegerField(source="assignments.count", read_only=True)

    class Meta(TenantSerializer.Meta):
        model = Role


class RoleViewSet(TenantModelViewSet):
    queryset = Role.objects.prefetch_related("permissions")
    serializer_class = RoleSerializer
    perm_module = "admin"
    perm_read = "admin.roles"
    perm_write = "admin.roles"
    pagination_class = None

    def perform_update(self, serializer):
        before = sorted(serializer.instance.permissions.values_list("code", flat=True))
        role = serializer.save()
        after = sorted(role.permissions.values_list("code", flat=True))
        if before != after:
            audit.log("permission", role, {"added": sorted(set(after) - set(before)),
                                           "removed": sorted(set(before) - set(after))})

    def perform_destroy(self, instance):
        if instance.is_system:
            from apps.core.exceptions import BusinessRuleError

            raise BusinessRuleError("System roles cannot be deleted.")
        instance.delete()


class RoleAssignmentSerializer(TenantSerializer):
    role_name = serializers.CharField(source="role.name", read_only=True)
    user_name = serializers.CharField(source="user.__str__", read_only=True)
    effective_scope = serializers.CharField(read_only=True)

    class Meta(TenantSerializer.Meta):
        model = RoleAssignment
        read_only_fields = TenantSerializer.Meta.read_only_fields + ["approved_by"]

    def validate(self, attrs):
        request = self.context["request"]
        user = attrs.get("user") or getattr(self.instance, "user", None)
        if user == request.user and not request.user.is_superuser:
            raise serializers.ValidationError("You cannot change your own role assignments (segregation of duties).")
        return attrs


class RoleAssignmentViewSet(TenantModelViewSet):
    queryset = RoleAssignment.objects.select_related("role", "user")
    serializer_class = RoleAssignmentSerializer
    perm_module = "admin"
    perm_read = "admin.roles"
    perm_write = "admin.roles"
    filterset_fields = ["user", "role"]

    def perform_create(self, serializer):
        ra = serializer.save(approved_by=self.request.user)
        clear_cache(ra.user)
        audit.log("permission", ra, {"granted": ra.role.code, "user": ra.user.username, "scope": ra.effective_scope})

    def perform_destroy(self, instance):
        audit.log("permission", instance, {"revoked": instance.role.code, "user": instance.user.username})
        instance.delete()
