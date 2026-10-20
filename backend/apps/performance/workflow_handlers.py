from apps.workflow.registry import WorkflowHandler, register


@register
class ObjectivesHandler(WorkflowHandler):
    request_type = "appraisal_objectives"
    label = "Appraisal objectives"

    def title(self, obj):
        return f"Objectives: {obj.employee.full_name} - {obj.cycle.name}"

    def link(self, obj):
        return f"/performance/appraisals/{obj.id}"

    def _set(self, obj, status):
        obj.status = status
        obj.save(update_fields=["status", "updated_at"])

    def on_approved(self, obj, instance):
        self._set(obj, "objectives_agreed")

    def on_rejected(self, obj, instance):
        self._set(obj, "objectives_returned")

    def on_returned(self, obj, instance):
        self._set(obj, "objectives_returned")

    def on_cancelled(self, obj, instance):
        self._set(obj, "objective_setting")

    def on_resubmitted(self, obj, instance):
        self._set(obj, "objectives_pending")


@register
class ImprovementPlanHandler(WorkflowHandler):
    request_type = "improvement_plan"
    label = "Performance improvement plan"

    def title(self, obj):
        return f"Improvement plan: {obj.employee.full_name} ({obj.start_date:%d/%m/%Y}-{obj.end_date:%d/%m/%Y})"

    def link(self, obj):
        return "/performance/plans"

    def _set(self, obj, status):
        obj.status = status
        obj.save(update_fields=["status", "updated_at"])

    def on_approved(self, obj, instance):
        from .services import _notify

        self._set(obj, "active")
        _notify([obj.employee.user], "Performance improvement plan",
                "A performance improvement plan has been agreed with you. Please read it and acknowledge it under "
                "My performance. You may add your comments.", "/performance/my")

    def on_rejected(self, obj, instance):
        self._set(obj, "rejected")

    def on_returned(self, obj, instance):
        self._set(obj, "returned")

    def on_cancelled(self, obj, instance):
        self._set(obj, "cancelled")

    def on_resubmitted(self, obj, instance):
        self._set(obj, "pending")
