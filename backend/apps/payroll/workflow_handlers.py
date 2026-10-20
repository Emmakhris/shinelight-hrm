from apps.workflow.registry import WorkflowHandler, register

from . import services


@register
class PayrollRunHandler(WorkflowHandler):
    request_type = "payroll_run"
    label = "Payroll approval"
    context_fields = ["net", "employees"]

    def title(self, obj):
        return f"Payroll {obj.period.name} ({obj.get_run_type_display()} #{obj.number})"

    def subject_employee(self, obj):
        return None

    def context(self, obj):
        return {"run_type": obj.run_type}

    def link(self, obj):
        return f"/payroll/runs/{obj.pk}"

    def on_approved(self, obj, instance):
        services.on_run_approved(obj, instance)

    def on_rejected(self, obj, instance):
        services.on_run_rejected(obj, instance)

    def on_returned(self, obj, instance):
        services.on_run_rejected(obj, instance)

    def on_cancelled(self, obj, instance):
        obj.status = "calculated"
        obj.save(update_fields=["status", "updated_at"])


@register
class LoanRequestHandler(WorkflowHandler):
    request_type = "loan_request"
    label = "Loan / salary advance"
    context_fields = ["amount", "loan_type"]

    def title(self, obj):
        return f"{obj.get_loan_type_display()} of GHS {obj.principal:,.2f} - {obj.employee.full_name}"

    def link(self, obj):
        return "/me/loans"

    def on_approved(self, obj, instance):
        obj.status = "active"
        obj.save(update_fields=["status", "updated_at"])

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
