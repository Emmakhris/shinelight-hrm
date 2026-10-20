from apps.workflow.registry import WorkflowHandler, register

from . import services


@register
class AttendanceCorrectionHandler(WorkflowHandler):
    request_type = "attendance_correction"
    label = "Attendance correction"

    def title(self, obj):
        return f"Attendance correction for {obj.employee.full_name} on {obj.date:%d/%m/%Y}"

    def link(self, obj):
        return "/attendance/my"

    def on_approved(self, obj, instance):
        services.apply_correction(obj)

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
