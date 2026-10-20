from apps.workflow.registry import WorkflowHandler, register

from . import services


@register
class LeaveRequestHandler(WorkflowHandler):
    request_type = "leave_request"
    label = "Leave request"
    context_fields = ["days", "leave_type", "is_paid", "department", "grade_level", "category"]

    def title(self, obj):
        return (f"{obj.leave_type.name} - {obj.employee.full_name} ({obj.days} day(s), "
                f"{obj.start_date:%d/%m/%Y} to {obj.end_date:%d/%m/%Y})")

    def context(self, obj):
        ctx = super().context(obj)
        ctx.update({"days": float(obj.days), "leave_type": obj.leave_type.code, "is_paid": obj.leave_type.is_paid})
        return ctx

    def link(self, obj):
        return "/leave/my"

    def on_approved(self, obj, instance):
        services.on_approved(obj)

    def _set(self, obj, status):
        obj.status = status
        obj.save(update_fields=["status", "updated_at"])

    def on_rejected(self, obj, instance):
        self._set(obj, "rejected")

    def on_returned(self, obj, instance):
        self._set(obj, "returned")

    def on_cancelled(self, obj, instance):
        self._set(obj, "cancelled")

    def on_resubmitted(self, obj, instance):
        self._set(obj, "pending")
