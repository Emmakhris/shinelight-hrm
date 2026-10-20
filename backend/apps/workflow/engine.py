"""Generic approval workflow engine.

start()      -> picks the matching definition, creates the instance and first-level tasks
act()        -> approve / reject / return on a task; advances, completes or ends the instance
resubmit()   -> restarts a returned instance
cancel()     -> initiator withdraws
reassign()   -> admin moves a task to another user
process_sla()-> reminders and escalation of overdue tasks (Celery beat)

Controls: separation of duties (initiator can never approve own request), mandatory comments,
delegation of authority, full action history and audit log entries.
"""

import datetime as dt
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.audit import services as audit
from apps.core.exceptions import BusinessRuleError
from apps.notifications.services import notify
from apps.rbac.models import RoleAssignment
from apps.rbac.services import department_descendants, has_perm

from . import conditions, registry
from .models import (
    Delegation,
    WorkflowAction,
    WorkflowDefinition,
    WorkflowInstance,
    WorkflowStep,
    WorkflowTask,
)

User = get_user_model()


# ------------------------------------------------------------------ resolution
def _user_of(employee):
    return getattr(employee, "user", None) if employee is not None else None


def _dept_head_user(employee):
    dept = employee.department if employee is not None else None
    seen = set()
    while dept is not None and dept.pk not in seen:
        seen.add(dept.pk)
        if dept.head_id and dept.head_id != employee.pk and dept.head.user_id:
            return dept.head.user
        dept = dept.parent
    return None


def _role_users(role, employee):
    today = dt.date.today()
    qs = (
        RoleAssignment.objects.filter(role=role, user__is_active=True)
        .filter(Q(valid_from__isnull=True) | Q(valid_from__lte=today))
        .filter(Q(valid_to__isnull=True) | Q(valid_to__gte=today))
        .select_related("user", "user__employee")
    )
    users = []
    for ra in qs:
        scope = ra.effective_scope
        if employee is None or scope == "organization":
            users.append(ra.user)
            continue
        approver_emp = getattr(ra.user, "employee", None)
        if scope == "department":
            dept_id = ra.department_id or (approver_emp.department_id if approver_emp else None)
            if dept_id and employee.department_id in department_descendants(dept_id):
                users.append(ra.user)
        elif scope == "branch":
            branch_id = ra.branch_id or (approver_emp.branch_id if approver_emp else None)
            if branch_id and employee.branch_id == branch_id:
                users.append(ra.user)
    return users


def resolve_approvers(step: WorkflowStep, employee) -> list:
    t = step.approver_type
    if t == "supervisor":
        users = [_user_of(employee.supervisor)] if employee and employee.supervisor_id else []
    elif t == "supervisor_2":
        sup = employee.supervisor if employee and employee.supervisor_id else None
        users = [_user_of(sup.supervisor)] if sup and sup.supervisor_id else []
    elif t == "dept_head":
        users = [_dept_head_user(employee)]
    elif t == "role" and step.role_id:
        users = _role_users(step.role, employee)
    elif t == "user" and step.user_id:
        users = [step.user]
    else:
        users = []
    unique = []
    for u in users:
        if u is not None and u.is_active and u not in unique:
            unique.append(u)
    return unique


def active_delegate(user, request_type, on_date=None):
    on_date = on_date or dt.date.today()
    for d in Delegation.objects.filter(delegator=user, is_active=True, start_date__lte=on_date, end_date__gte=on_date):
        if not d.request_types or request_type in d.request_types:
            return d.delegate
    return None


def _fallback_users():
    """Workflow administrators receive tasks that cannot be routed (exception handling)."""
    return [u for u in User.objects.filter(is_active=True) if has_perm(u, "workflow.admin")]


# ------------------------------------------------------------------ helpers
def find_definition(request_type, ctx):
    for d in WorkflowDefinition.objects.filter(request_type=request_type, is_active=True).order_by("priority", "id"):
        if conditions.evaluate(d.conditions, ctx):
            return d
    return None


def _record(instance, action, actor=None, task=None, comment=""):
    WorkflowAction.objects.create(instance=instance, task=task, actor=actor, action=action, comment=comment)


def _target(instance):
    return instance.content_type.get_object_for_this_type(pk=instance.object_id)


def _create_tasks_for_order(instance: WorkflowInstance, order: int) -> int:
    """Create tasks for every step at `order`. Returns number of tasks created."""
    employee = instance.subject_employee
    created = 0
    for step in instance.definition.steps.filter(order=order):
        if not conditions.evaluate(step.condition, instance.context):
            _record(instance, "step_skipped", comment=f"{step.name}: condition not met")
            continue
        approvers = [u for u in resolve_approvers(step, employee) if u != instance.initiator]
        if not approvers:
            if step.skip_if_no_approver:
                _record(instance, "step_skipped", comment=f"{step.name}: no eligible approver")
                continue
            approvers = [u for u in _fallback_users() if u != instance.initiator]
            _record(instance, "routed_to_admin", comment=f"{step.name}: no eligible approver, routed to admins")
            if not approvers:
                continue
        due = timezone.now() + timedelta(hours=step.sla_hours) if step.sla_hours else None
        for user in approvers:
            delegate = active_delegate(user, instance.request_type)
            assignee, delegated_from = (delegate, user) if delegate and delegate != instance.initiator else (user, None)
            WorkflowTask.objects.create(instance=instance, step=step, assignee=assignee,
                                        delegated_from=delegated_from, due_at=due)
            created += 1
            notify("workflow.task_assigned", [assignee], {
                "title": instance.title, "step": step.name, "due_at": due,
                "link": f"/inbox?task_instance={instance.pk}",
            }, related=instance)
    return created


def _advance(instance: WorkflowInstance, actor=None):
    """Move to the next order that yields tasks, or complete the instance."""
    orders = sorted(set(instance.definition.steps.filter(order__gt=instance.current_order)
                        .values_list("order", flat=True)))
    for order in orders:
        instance.current_order = order
        instance.save(update_fields=["current_order", "updated_at"])
        if _create_tasks_for_order(instance, order):
            return
    _finish(instance, "approved", actor)


def _finish(instance: WorkflowInstance, status, actor=None, comment=""):
    instance.status = status
    instance.completed_at = timezone.now()
    instance.save(update_fields=["status", "completed_at", "updated_at"])
    instance.tasks.filter(status="pending").update(status="cancelled")
    handler = registry.get_handler(instance.request_type)
    target = _target(instance)
    hook = {"approved": handler.on_approved, "rejected": handler.on_rejected,
            "returned": handler.on_returned, "cancelled": handler.on_cancelled}.get(status)
    if hook:
        hook(target, instance)
    _record(instance, f"instance_{status}", actor=actor, comment=comment)
    audit.log("workflow", instance, {"status": status, "request_type": instance.request_type})
    if instance.initiator and status != "cancelled":
        notify(f"workflow.{status}", [instance.initiator], {
            "title": instance.title, "comment": comment, "link": handler.link(target),
        }, related=instance)


# ------------------------------------------------------------------ public API
@transaction.atomic
def start(obj, request_type, initiator, subject_employee=None, extra_context=None) -> WorkflowInstance:
    handler = registry.get_handler(request_type)
    employee = subject_employee or handler.subject_employee(obj)
    ctx = handler.context(obj)
    ctx.update(extra_context or {})
    definition = find_definition(request_type, ctx)
    if definition is None:
        raise BusinessRuleError(f"No approval workflow is configured for '{request_type}'. Contact HR.",
                                code="workflow_missing")
    instance = WorkflowInstance.objects.create(
        definition=definition, request_type=request_type,
        content_type=ContentType.objects.get_for_model(obj), object_id=obj.pk,
        title=handler.title(obj)[:255], initiator=initiator, subject_employee=employee,
        context={k: v for k, v in ctx.items() if isinstance(v, (str, int, float, bool, type(None)))},
    )
    _record(instance, "submitted", actor=initiator)
    _advance(instance, initiator)
    return instance


@transaction.atomic
def act(task: WorkflowTask, user, action: str, comment: str = "") -> WorkflowInstance:
    task = WorkflowTask.objects.select_for_update().select_related("instance", "step").get(pk=task.pk)
    instance = task.instance
    if action not in ("approve", "reject", "return"):
        raise BusinessRuleError("Unknown action.")
    if task.status != "pending" or instance.status != "in_progress":
        raise BusinessRuleError("This task has already been completed.")
    is_admin = has_perm(user, "workflow.admin")
    if task.assignee_id != user.id and not is_admin:
        raise BusinessRuleError("You are not the assignee of this task.")
    if instance.initiator_id == user.id:
        raise BusinessRuleError("You cannot act on a request you initiated (segregation of duties).")
    if instance.subject_employee_id and getattr(user, "employee", None) and \
            user.employee.id == instance.subject_employee_id and action == "approve":
        raise BusinessRuleError("You cannot approve a request about yourself.")
    rule = task.step.comment_rule
    if not comment.strip() and (rule == "all" or (rule == "reject" and action in ("reject", "return"))):
        raise BusinessRuleError("A comment is required for this decision.")

    status_map = {"approve": "approved", "reject": "rejected", "return": "returned"}
    task.status = status_map[action]
    task.acted_at = timezone.now()
    task.acted_by = user
    task.comment = comment
    task.save()
    _record(instance, action, actor=user, task=task, comment=comment)

    if action in ("reject", "return"):
        _finish(instance, status_map[action], user, comment)
        return instance

    # approve: does this step need more approvals?
    step_tasks = instance.tasks.filter(step=task.step).exclude(status__in=["cancelled", "reassigned"])
    if task.step.approval_mode == "any":
        step_tasks.filter(status="pending").exclude(pk=task.pk).update(status="skipped")
    if instance.tasks.filter(step__order=instance.current_order, status="pending").exists():
        return instance  # parallel steps or "all" mode still outstanding
    _advance(instance, user)
    return instance


@transaction.atomic
def resubmit(instance: WorkflowInstance, user, comment=""):
    if instance.status != "returned":
        raise BusinessRuleError("Only returned requests can be resubmitted.")
    if instance.initiator_id != user.id and not has_perm(user, "workflow.admin"):
        raise BusinessRuleError("Only the requester can resubmit.")
    instance.status = "in_progress"
    instance.current_order = 0
    instance.completed_at = None
    instance.save(update_fields=["status", "current_order", "completed_at", "updated_at"])
    _record(instance, "resubmitted", actor=user, comment=comment)
    registry.get_handler(instance.request_type).on_resubmitted(_target(instance), instance)
    _advance(instance, user)
    return instance


@transaction.atomic
def cancel(instance: WorkflowInstance, user, comment=""):
    if instance.status not in ("in_progress", "returned"):
        raise BusinessRuleError("This request can no longer be cancelled.")
    if instance.initiator_id != user.id and not has_perm(user, "workflow.admin"):
        raise BusinessRuleError("Only the requester can cancel.")
    _finish(instance, "cancelled", user, comment)
    return instance


@transaction.atomic
def reassign(task: WorkflowTask, new_user, by_user, comment=""):
    if task.status != "pending":
        raise BusinessRuleError("Only pending tasks can be reassigned.")
    if new_user == task.instance.initiator:
        raise BusinessRuleError("Cannot assign a request to its initiator.")
    task.status = "reassigned"
    task.save(update_fields=["status", "updated_at"])
    new_task = WorkflowTask.objects.create(instance=task.instance, step=task.step, assignee=new_user,
                                           due_at=task.due_at, delegated_from=task.assignee)
    _record(task.instance, "reassigned", actor=by_user, task=new_task, comment=f"{task.assignee} -> {new_user}. {comment}")
    notify("workflow.task_assigned", [new_user], {"title": task.instance.title, "step": task.step.name,
                                                  "due_at": task.due_at}, related=task.instance)
    return new_task


def current_assignees(instance):
    return [t.assignee for t in instance.tasks.filter(status="pending").select_related("assignee")]


def process_sla(now=None):
    """Remind assignees at 75% of SLA; escalate overdue tasks once to the escalation role or the
    assignee's supervisor. Returns (reminded, escalated)."""
    now = now or timezone.now()
    reminded = escalated = 0
    pending = WorkflowTask.all_objects.filter(status="pending", due_at__isnull=False,
                                              instance__status="in_progress").select_related("step", "instance",
                                                                                             "assignee")
    for task in pending:
        total = timedelta(hours=task.step.sla_hours or 0)
        if task.due_at <= now and task.escalated_at is None:
            targets = []
            if task.step.escalate_to_role_id:
                targets = _role_users(task.step.escalate_to_role, task.instance.subject_employee)
            else:
                emp = getattr(task.assignee, "employee", None)
                if emp and emp.supervisor_id and emp.supervisor.user_id:
                    targets = [emp.supervisor.user]
            targets = [u for u in targets if u != task.instance.initiator and u != task.assignee]
            for u in targets:
                WorkflowTask.all_objects.create(organization_id=task.organization_id, instance=task.instance,
                                                step=task.step, assignee=u, is_escalation=True,
                                                due_at=now + total)
            notify("workflow.escalated", [task.assignee] + targets,
                   {"title": task.instance.title, "step": task.step.name}, related=task.instance)
            WorkflowAction.all_objects.create(organization_id=task.organization_id, instance=task.instance,
                                              task=task, action="escalated",
                                              comment=f"SLA exceeded; escalated to {', '.join(map(str, targets)) or 'nobody'}")
            task.escalated_at = now
            task.save(update_fields=["escalated_at"])
            escalated += 1
        elif task.reminded_at is None and total and task.due_at - now <= total * 0.25:
            notify("workflow.reminder", [task.assignee], {"title": task.instance.title, "due_at": task.due_at},
                   related=task.instance)
            task.reminded_at = now
            task.save(update_fields=["reminded_at"])
            reminded += 1
    return reminded, escalated
