from rest_framework import serializers

from apps.core.fields import mask
from apps.rbac.services import can_access_employee, has_perm


class SensitiveFieldsMixin:
    """Masks fields unless the requester holds the permission for that employee's record.

    sensitive_fields = {"basic_salary": "employees.view_salary", "account_number": ("employees.view_bank", "mask")}
    employee_attr = "employee"  # attribute path from instance to Employee ("" = instance is the Employee)
    Mode "hide" (default) returns None; "mask" keeps the last 4 characters.
    """

    sensitive_fields: dict = {}
    employee_attr: str | None = "employee"

    def _employee_of(self, instance):
        if self.employee_attr is None:
            return None
        if self.employee_attr == "":
            return instance
        obj = instance
        for part in self.employee_attr.split("."):
            obj = getattr(obj, part, None)
            if obj is None:
                return None
        return obj

    def _allowed(self, user, code, instance):
        cache = self.context.setdefault("_sensitive_cache", {})
        employee = self._employee_of(instance)
        key = (code, getattr(employee, "pk", None))
        if key not in cache:
            if employee is None:
                cache[key] = has_perm(user, code)
            else:
                cache[key] = can_access_employee(user, code, employee)
        return cache[key]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if user is None:
            return data
        for field, rule in self.sensitive_fields.items():
            code, mode = (rule, "hide") if isinstance(rule, str) else rule
            if field in data and not self._allowed(user, code, instance):
                data[field] = mask(data[field]) if mode == "mask" else None
        return data


class TenantSerializer(serializers.ModelSerializer):
    """ModelSerializer that never exposes/accepts the organization FK."""

    class Meta:
        exclude = ["organization"]
        read_only_fields = ["created_at", "updated_at", "created_by"]
