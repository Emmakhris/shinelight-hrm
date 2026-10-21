from apps.workflow.registry import WorkflowHandler, register


@register
class DisciplinaryDecisionHandler(WorkflowHandler):
    request_type = "disciplinary_decision"
    label = "Disciplinary decision"
    context_fields = ["outcome"]

    def subject_employee(self, obj):
        return obj.respondents.first()

    def title(self, obj):
        # deliberately generic: workflow titles appear in inboxes and notifications
        return f"Confidential case {obj.reference}: decision for approval"

    def link(self, obj):
        return f"/relations/cases/{obj.id}"

    def on_approved(self, obj, instance):
        from .services import issue

        issue(obj)

    def _reopen(self, obj):
        obj.actions.filter(issued_at__isnull=True).delete()
        obj.status, obj.outcome, obj.decided_at = "hearing", "", None
        obj.save(update_fields=["status", "outcome", "decided_at", "updated_at"])

    def on_rejected(self, obj, instance):
        self._reopen(obj)

    def on_returned(self, obj, instance):
        self._reopen(obj)

    def on_cancelled(self, obj, instance):
        self._reopen(obj)
