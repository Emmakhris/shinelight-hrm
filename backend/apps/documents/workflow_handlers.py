from apps.notifications.services import notify
from apps.workflow.registry import WorkflowHandler, register


@register
class LetterRequestHandler(WorkflowHandler):
    request_type = "letter_request"
    label = "HR letter request"

    def title(self, obj):
        return f"{obj.template.name} for {obj.employee.full_name}"

    def context(self, obj):
        ctx = super().context(obj)
        ctx["letter_type"] = obj.template.letter_type
        return ctx

    def link(self, obj):
        return "/me/documents"

    def on_approved(self, obj, instance):
        from .services import generate_letter

        doc = generate_letter(obj.template, obj.employee,
                              extra={"addressed_to": obj.addressed_to, "purpose": obj.purpose},
                              reference=f"HR/LTR/{obj.pk:05d}")
        obj.document = doc
        obj.status = "issued"
        obj.save(update_fields=["document", "status", "updated_at"])
        if obj.employee.user_id:
            notify("generic", [obj.employee.user], {"title": f"Your {obj.template.name} is ready",
                                                    "body": "Download it under My Documents.",
                                                    "link": "/me/documents"})

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
