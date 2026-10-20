from apps.workflow.registry import WorkflowHandler, register

from . import services


class _Status(WorkflowHandler):
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


@register
class SalaryReviewHandler(_Status):
    request_type = "salary_review"
    label = "Salary review"
    context_fields = ["amount", "within_budget"]

    def title(self, obj):
        return f"Salary review: {obj.name} (effective {obj.effective_date:%d/%m/%Y})"

    def subject_employee(self, obj):
        return None

    def context(self, obj):
        return {}

    def link(self, obj):
        return f"/compensation/reviews/{obj.pk}"

    def on_approved(self, obj, instance):
        self._set(obj, "approved")


@register
class BonusSchemeHandler(_Status):
    request_type = "bonus_scheme"
    label = "Bonus awards"
    context_fields = ["amount"]

    def title(self, obj):
        return f"Bonus scheme: {obj.name}"

    def subject_employee(self, obj):
        return None

    def context(self, obj):
        return {}

    def link(self, obj):
        return "/compensation/bonuses"

    def on_approved(self, obj, instance):
        services.post_bonus_to_payroll(obj)
        self._set(obj, "approved")


@register
class BenefitEnrollmentHandler(_Status):
    request_type = "benefit_enrollment"
    label = "Benefit enrolment"
    context_fields = ["plan_type", "amount"]

    def title(self, obj):
        return f"{obj.plan.name} enrolment — {obj.employee.full_name}"

    def link(self, obj):
        return "/me/benefits"

    def on_approved(self, obj, instance):
        services.activate(obj)
