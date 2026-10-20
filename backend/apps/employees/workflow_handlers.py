from apps.workflow.registry import WorkflowHandler, register

from . import services


@register
class EmployeeChangeHandler(WorkflowHandler):
    request_type = "employee_change"
    label = "Personal information change"

    def title(self, obj):
        fields = ", ".join(obj.changes.keys())
        return f"Profile update for {obj.employee.full_name}: {fields}"

    def link(self, obj):
        return "/me/requests"

    def on_approved(self, obj, instance):
        services.apply_change_request(obj)

    def on_rejected(self, obj, instance):
        obj.status = "rejected"
        obj.save(update_fields=["status", "updated_at"])

    def on_returned(self, obj, instance):
        obj.status = "returned"
        obj.save(update_fields=["status", "updated_at"])

    def on_resubmitted(self, obj, instance):
        obj.status = "pending"
        obj.save(update_fields=["status", "updated_at"])

    def on_cancelled(self, obj, instance):
        obj.status = "cancelled"
        obj.save(update_fields=["status", "updated_at"])
