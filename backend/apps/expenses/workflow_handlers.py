from apps.workflow.registry import WorkflowHandler, register


class _StatusHandler(WorkflowHandler):
    def _set(self, obj, status):
        obj.status = status
        obj.save(update_fields=["status", "updated_at"])

    def on_approved(self, obj, instance):
        self._set(obj, "approved")

    def on_rejected(self, obj, instance):
        self._set(obj, "rejected")

    def on_returned(self, obj, instance):
        self._set(obj, "returned")

    def on_cancelled(self, obj, instance):
        self._set(obj, "cancelled")

    def on_resubmitted(self, obj, instance):
        self._set(obj, "pending")


@register
class TravelRequestHandler(_StatusHandler):
    request_type = "travel_request"
    label = "Official travel"
    context_fields = ["amount", "advance", "destination_class"]

    def title(self, obj):
        return (f"Travel {obj.reference}: {obj.employee.full_name} to {obj.destination} "
                f"({obj.departure_date:%d/%m}–{obj.return_date:%d/%m/%Y})")

    def link(self, obj):
        return "/expenses/my"


@register
class ExpenseClaimHandler(_StatusHandler):
    request_type = "expense_claim"
    label = "Expense claim"
    context_fields = ["amount", "has_advance"]

    def title(self, obj):
        return f"Expense claim {obj.reference}: {obj.employee.full_name} — {obj.currency} {obj.total:,.2f}"

    def link(self, obj):
        return "/expenses/my"
