from django.utils import timezone

from apps.workflow.registry import WorkflowHandler, register


class _StatusHandler(WorkflowHandler):
    def _set(self, obj, status, **extra):
        obj.status = status
        for k, v in extra.items():
            setattr(obj, k, v)
        obj.save(update_fields=["status", "updated_at", *extra])

    def on_approved(self, obj, instance):
        self._set(obj, "approved")

    def on_rejected(self, obj, instance):
        self._set(obj, "rejected")

    def on_returned(self, obj, instance):
        self._set(obj, "returned")

    def on_cancelled(self, obj, instance):
        if obj.status in ("pending", "returned"):
            self._set(obj, "cancelled")

    def on_resubmitted(self, obj, instance):
        self._set(obj, "pending")


@register
class RequisitionHandler(_StatusHandler):
    request_type = "job_requisition"
    label = "Manpower requisition"
    context_fields = ["amount", "headcount", "reason", "department"]

    def subject_employee(self, obj):
        return obj.requested_by

    def title(self, obj):
        return (f"Requisition {obj.reference}: {obj.headcount} x {obj.job_title.name} "
                f"({obj.department.name}, {obj.get_reason_display().lower()})")

    def link(self, obj):
        return "/recruitment/requisitions"

    def on_approved(self, obj, instance):
        self._set(obj, "approved", approved_at=timezone.now())


@register
class OfferHandler(_StatusHandler):
    request_type = "job_offer"
    label = "Offer of employment"
    context_fields = ["amount", "above_budget", "department"]

    def subject_employee(self, obj):
        req = obj.application.vacancy.requisition
        return req.requested_by if req else None

    def title(self, obj):
        return (f"Offer {obj.reference} rev {obj.revision}: {obj.application.candidate.full_name} as "
                f"{obj.job_title.name} - GHS {obj.basic_salary:,.2f}/month")

    def link(self, obj):
        return f"/recruitment/applications/{obj.application_id}"
