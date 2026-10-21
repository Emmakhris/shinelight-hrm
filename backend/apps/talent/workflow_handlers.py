from apps.workflow.registry import WorkflowHandler, register


@register
class WorkforcePlanHandler(WorkflowHandler):
    request_type = "workforce_plan"
    label = "Workforce plan"

    def subject_employee(self, obj):
        return None

    def title(self, obj):
        return f"Workforce plan: {obj.name} ({obj.year})"

    def link(self, obj):
        return f"/planning/{obj.id}"

    def _set(self, obj, status):
        obj.status = status
        obj.save(update_fields=["status", "updated_at"])

    def on_approved(self, obj, instance):
        self._set(obj, "approved")

    def on_rejected(self, obj, instance):
        self._set(obj, "draft")

    def on_returned(self, obj, instance):
        self._set(obj, "draft")

    def on_cancelled(self, obj, instance):
        self._set(obj, "draft")
