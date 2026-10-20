"""Request-type handlers connect domain objects (leave requests, change requests, payroll runs...)
to the generic workflow engine."""


class WorkflowHandler:
    request_type: str = ""
    label: str = ""
    # Fields exposed to conditions, for the admin UI
    context_fields: list[str] = []

    def title(self, obj) -> str:
        return str(obj)

    def subject_employee(self, obj):
        return getattr(obj, "employee", None)

    def context(self, obj) -> dict:
        emp = self.subject_employee(obj)
        ctx = {}
        if emp is not None:
            ctx.update({
                "department_id": emp.department_id,
                "department": emp.department.code if emp.department_id else None,
                "grade_level": emp.grade.level if emp.grade_id else None,
                "category": emp.category.code if emp.category_id else None,
                "branch_id": emp.branch_id,
                "employment_type": emp.employment_type,
            })
        return ctx

    def link(self, obj) -> str:
        return ""

    # lifecycle hooks
    def on_approved(self, obj, instance):
        pass

    def on_rejected(self, obj, instance):
        pass

    def on_returned(self, obj, instance):
        pass

    def on_cancelled(self, obj, instance):
        pass

    def on_resubmitted(self, obj, instance):
        pass


_handlers: dict[str, WorkflowHandler] = {}


def register(handler_cls):
    handler = handler_cls()
    _handlers[handler.request_type] = handler
    return handler_cls


def get_handler(request_type) -> WorkflowHandler:
    return _handlers.get(request_type) or WorkflowHandler()


def all_handlers():
    return dict(_handlers)
