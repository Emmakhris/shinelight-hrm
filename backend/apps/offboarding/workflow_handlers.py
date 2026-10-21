from apps.workflow.registry import WorkflowHandler, register


@register
class SeparationHandler(WorkflowHandler):
    request_type = "separation"
    label = "Employee exit"
    context_fields = ["exit_type", "involuntary", "shortfall"]

    def title(self, obj):
        return (f"Exit {obj.reference}: {obj.employee.full_name} - {obj.get_exit_type_display().lower()}, "
                f"last day {obj.last_working_day:%d/%m/%Y}")

    def link(self, obj):
        return f"/offboarding/{obj.id}"

    def _set(self, obj, status):
        obj.status = status
        obj.save(update_fields=["status", "updated_at"])

    def on_approved(self, obj, instance):
        from .services import approve

        approve(obj, instance.initiator)

    def on_rejected(self, obj, instance):
        self._set(obj, "rejected")

    def on_returned(self, obj, instance):
        self._set(obj, "returned")

    def on_cancelled(self, obj, instance):
        if obj.status in ("pending", "returned"):
            self._set(obj, "withdrawn")

    def on_resubmitted(self, obj, instance):
        self._set(obj, "pending")
