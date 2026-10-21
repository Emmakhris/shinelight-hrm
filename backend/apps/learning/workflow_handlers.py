from apps.workflow.registry import WorkflowHandler, register


@register
class TrainingRequestHandler(WorkflowHandler):
    request_type = "training_request"
    label = "Training request"
    context_fields = ["amount", "external", "over_budget"]

    def title(self, obj):
        when = f" ({obj.session.start:%d/%m/%Y})" if obj.session_id else ""
        return f"Training: {obj.employee.full_name} - {obj.course.title}{when}, GHS {obj.cost:,.2f}"

    def link(self, obj):
        return f"/learning/enrollments/{obj.id}"

    def _set(self, obj, status):
        obj.status = status
        obj.save(update_fields=["status", "updated_at"])

    def on_approved(self, obj, instance):
        from .services import _place

        _place(obj)

    def on_rejected(self, obj, instance):
        self._set(obj, "rejected")

    def on_returned(self, obj, instance):
        self._set(obj, "returned")

    def on_cancelled(self, obj, instance):
        self._set(obj, "cancelled")

    def on_resubmitted(self, obj, instance):
        self._set(obj, "pending")
