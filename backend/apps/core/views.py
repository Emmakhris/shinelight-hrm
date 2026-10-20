from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from apps.core.context import get_current_org
from apps.rbac.permissions import RBACPermission
from apps.rbac.services import scope_queryset


class TenantModelViewSet(viewsets.ModelViewSet):
    """Base viewset: authentication + RBAC + optional employee data scoping.

    Set `scope_prefix` to the lookup path from the model to Employee ("" for Employee itself,
    "employee__" for related models) to restrict rows to the requester's data scope.
    """

    permission_classes = [IsAuthenticated, RBACPermission]
    scope_prefix: str | None = None

    def get_scope_code(self):
        return getattr(self, "perm_read", None) or f"{self.perm_module}.view"

    def get_queryset(self):
        qs = super().get_queryset()
        # Class-level querysets are built at import time (no org context), so always re-apply the tenant filter.
        org = get_current_org()
        if org is not None and any(f.name == "organization" for f in qs.model._meta.fields):
            qs = qs.filter(organization=org)
        if self.scope_prefix is not None:
            qs = scope_queryset(self.request.user, qs, self.get_scope_code(), self.scope_prefix)
        return qs


class TenantReadOnlyViewSet(TenantModelViewSet):
    http_method_names = ["get", "head", "options"]
