from rest_framework.permissions import SAFE_METHODS, BasePermission

from . import services

ACTION_VERBS = {
    "list": "view",
    "retrieve": "view",
    "create": "create",
    "update": "change",
    "partial_update": "change",
    "destroy": "delete",
}


class RBACPermission(BasePermission):
    """Checks `module.action` permissions declared on the view.

    View attributes:
      perm_module = "employees"          -> list/retrieve need employees.view, create needs employees.create ...
      perm_map = {"approve": "leave.approve"}   -> explicit per-action codes (override)
      perm_write = "organization.manage" -> single code for every non-safe action
    """

    def required_code(self, request, view):
        action = getattr(view, "action", None)
        perm_map = getattr(view, "perm_map", {}) or {}
        if action in perm_map:
            return perm_map[action]
        module = getattr(view, "perm_module", None)
        if module is None:
            return None
        if request.method in SAFE_METHODS:
            return getattr(view, "perm_read", None) or f"{module}.view"
        write = getattr(view, "perm_write", None)
        if write:
            return write
        verb = ACTION_VERBS.get(action, "change")
        return f"{module}.{verb}"

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        code = self.required_code(request, view)
        if code is None:
            return True
        return services.has_perm(request.user, code)


def require(code):
    """Permission class factory: `permission_classes = [require("audit.view")]`."""

    class _Required(BasePermission):
        def has_permission(self, request, view):
            return services.has_perm(request.user, code)

    _Required.__name__ = f"Require_{code.replace('.', '_')}"
    return _Required
