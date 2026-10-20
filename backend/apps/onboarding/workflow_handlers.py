from apps.workflow.registry import WorkflowHandler, register


@register
class ProbationOutcomeHandler(WorkflowHandler):
    request_type = "probation_outcome"
    label = "Probation outcome"
    context_fields = ["recommendation", "review_type"]

    def title(self, obj):
        return (f"Probation: {obj.get_recommendation_display()} - {obj.employee.full_name} "
                f"(rating {obj.overall_rating}/5)")

    def link(self, obj):
        return "/onboarding/probation"

    def on_approved(self, obj, instance):
        from .services import apply_decision

        apply_decision(obj, instance.initiator)

    def on_rejected(self, obj, instance):
        obj.status = "rejected"
        obj.save(update_fields=["status", "updated_at"])

    def on_returned(self, obj, instance):
        obj.status = "returned"
        obj.save(update_fields=["status", "updated_at"])

    def on_cancelled(self, obj, instance):
        obj.status = "cancelled"
        obj.save(update_fields=["status", "updated_at"])

    def on_resubmitted(self, obj, instance):
        obj.status = "submitted"
        obj.save(update_fields=["status", "updated_at"])
