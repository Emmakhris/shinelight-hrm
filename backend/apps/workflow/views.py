from django.contrib.auth import get_user_model
from django.db.models import Q
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.core.exceptions import BusinessRuleError
from apps.core.serializers import DisplayField, TenantSerializer
from apps.core.views import TenantModelViewSet
from apps.rbac.services import has_perm

from . import engine, registry
from .models import (
    Delegation,
    WorkflowAction,
    WorkflowDefinition,
    WorkflowInstance,
    WorkflowStep,
    WorkflowTask,
)

User = get_user_model()


class StepSerializer(TenantSerializer):
    role_name = serializers.CharField(source="role.name", read_only=True, default=None)
    user_name = DisplayField("user")

    class Meta(TenantSerializer.Meta):
        model = WorkflowStep


class DefinitionSerializer(TenantSerializer):
    steps = StepSerializer(many=True, read_only=True)
    request_type_label = serializers.SerializerMethodField()

    class Meta(TenantSerializer.Meta):
        model = WorkflowDefinition

    def get_request_type_label(self, obj):
        return registry.get_handler(obj.request_type).label or obj.request_type


class DefinitionViewSet(TenantModelViewSet):
    queryset = WorkflowDefinition.objects.prefetch_related("steps__role", "steps__user")
    serializer_class = DefinitionSerializer
    perm_module = "workflow"
    perm_read = "workflow.manage"
    perm_write = "workflow.manage"
    filterset_fields = ["request_type", "is_active"]
    pagination_class = None

    def perform_update(self, serializer):
        obj = serializer.save()
        obj.version += 1
        obj.save(update_fields=["version"])

    @action(detail=False, url_path="request-types")
    def request_types(self, request):
        return Response([{"code": code, "label": h.label, "context_fields": h.context_fields}
                         for code, h in registry.all_handlers().items()])


class StepViewSet(TenantModelViewSet):
    queryset = WorkflowStep.objects.select_related("role", "user")
    serializer_class = StepSerializer
    perm_module = "workflow"
    perm_read = "workflow.manage"
    perm_write = "workflow.manage"
    filterset_fields = ["definition"]
    pagination_class = None


class ActionSerializer(serializers.ModelSerializer):
    actor_name = DisplayField("actor", fallback="System")

    class Meta:
        model = WorkflowAction
        fields = ["id", "action", "comment", "actor", "actor_name", "created_at"]


class TaskBriefSerializer(serializers.ModelSerializer):
    assignee_name = DisplayField("assignee")
    step_name = serializers.CharField(source="step.name", read_only=True)
    delegated_from_name = DisplayField("delegated_from")

    class Meta:
        model = WorkflowTask
        fields = ["id", "step", "step_name", "assignee", "assignee_name", "delegated_from_name", "status", "due_at",
                  "acted_at", "comment", "is_escalation"]


class InstanceSerializer(serializers.ModelSerializer):
    initiator_name = DisplayField("initiator")
    subject_name = serializers.CharField(source="subject_employee.full_name", read_only=True, default=None)
    request_type_label = serializers.SerializerMethodField()
    waiting_on = serializers.SerializerMethodField()
    target_summary = serializers.SerializerMethodField()

    class Meta:
        model = WorkflowInstance
        fields = ["id", "title", "request_type", "request_type_label", "status", "initiator", "initiator_name",
                  "subject_employee", "subject_name", "object_id", "current_order", "created_at", "completed_at",
                  "waiting_on", "target_summary"]

    def get_request_type_label(self, obj):
        return registry.get_handler(obj.request_type).label

    def get_waiting_on(self, obj):
        return [str(u) for u in engine.current_assignees(obj)]

    def get_target_summary(self, obj):
        return target_summary(obj)


class InstanceDetailSerializer(InstanceSerializer):
    history = ActionSerializer(many=True, read_only=True)
    tasks = TaskBriefSerializer(many=True, read_only=True)

    class Meta(InstanceSerializer.Meta):
        fields = InstanceSerializer.Meta.fields + ["history", "tasks", "context"]


def target_summary(instance):
    """Key facts of the request so approvers can decide from the inbox."""
    try:
        obj = instance.content_type.get_object_for_this_type(pk=instance.object_id)
    except Exception:
        return {}
    t = instance.request_type
    if t == "leave_request":
        from apps.leave.services import balance

        bal = balance(obj.employee, obj.leave_type, obj.start_date.year)
        return {"leave_type": obj.leave_type.name, "start_date": obj.start_date, "end_date": obj.end_date,
                "days": obj.days, "reason": "(confidential)" if obj.leave_type.is_confidential else obj.reason,
                "relief_officer": obj.relief_officer.full_name if obj.relief_officer_id else None,
                "balance_available": bal["available"], "warnings": obj.warnings, "status": obj.status,
                "attachment": obj.attachment_id}
    if t == "employee_change":
        return {"changes": [{"field": k, "from": obj.previous.get(k), "to": v} for k, v in obj.changes.items()],
                "reason": obj.reason}
    if t == "attendance_correction":
        return {"date": obj.date, "clock_in": obj.clock_in, "clock_out": obj.clock_out, "reason": obj.reason}
    if t == "payroll_run":
        return {"period": obj.period.name, "run_type": obj.get_run_type_display(), "totals": obj.totals,
                "run_id": obj.id}
    if t == "loan_request":
        return {"loan_type": obj.get_loan_type_display(), "principal": obj.principal,
                "installments": obj.installments, "installment_amount": obj.installment_amount,
                "purpose": obj.purpose, "basic_salary": obj.employee.basic_salary}
    if t == "letter_request":
        return {"letter": obj.template.name, "addressed_to": obj.addressed_to, "purpose": obj.purpose}
    return {}


class TaskSerializer(TaskBriefSerializer):
    instance = InstanceSerializer(read_only=True)

    class Meta(TaskBriefSerializer.Meta):
        fields = TaskBriefSerializer.Meta.fields + ["instance"]


class InboxViewSet(viewsets.ReadOnlyModelViewSet):
    """Tasks assigned to the current user (approvals inbox)."""

    serializer_class = TaskSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["status", "instance__request_type"]

    def get_queryset(self):
        qs = WorkflowTask.objects.select_related("instance", "step", "assignee", "instance__initiator",
                                                 "instance__subject_employee")
        if self.request.query_params.get("all") == "1" and has_perm(self.request.user, "workflow.admin"):
            return qs
        return qs.filter(assignee=self.request.user)

    @action(detail=False)
    def counts(self, request):
        qs = WorkflowTask.objects.filter(assignee=request.user, status="pending", instance__status="in_progress")
        return Response({"pending": qs.count(),
                         "by_type": {r: qs.filter(instance__request_type=r).count()
                                     for r in qs.values_list("instance__request_type", flat=True).distinct()}})

    @action(detail=True, methods=["post"])
    def act(self, request, pk=None):
        task = self.get_object()
        engine.act(task, request.user, request.data.get("action", ""), request.data.get("comment", ""))
        task.refresh_from_db()
        return Response(TaskSerializer(task, context={"request": request}).data)

    @action(detail=False, methods=["post"], url_path="bulk-approve")
    def bulk_approve(self, request):
        done, failed = [], []
        for task in self.get_queryset().filter(pk__in=request.data.get("ids", []), status="pending"):
            try:
                engine.act(task, request.user, "approve", request.data.get("comment", ""))
                done.append(task.id)
            except BusinessRuleError as exc:
                failed.append({"id": task.id, "error": exc.message})
        return Response({"approved": done, "failed": failed})

    @action(detail=True, methods=["post"])
    def reassign(self, request, pk=None):
        task = WorkflowTask.objects.get(pk=pk)
        if not has_perm(request.user, "workflow.admin") and task.assignee != request.user:
            raise PermissionDenied("Not permitted.")
        new_user = User.objects.get(pk=request.data["user"], organization=request.user.organization)
        new = engine.reassign(task, new_user, request.user, request.data.get("comment", ""))
        return Response(TaskBriefSerializer(new).data)


class InstanceViewSet(viewsets.ReadOnlyModelViewSet):
    """Requests: my submissions ('mine'), or every instance for workflow admins/auditors."""

    permission_classes = [IsAuthenticated]
    filterset_fields = ["status", "request_type", "subject_employee"]
    search_fields = ["title"]

    def get_serializer_class(self):
        return InstanceDetailSerializer if self.action == "retrieve" else InstanceSerializer

    def get_queryset(self):
        qs = WorkflowInstance.objects.select_related("initiator", "subject_employee").prefetch_related("history")
        user = self.request.user
        if has_perm(user, "workflow.admin") or has_perm(user, "audit.view"):
            if self.request.query_params.get("mine") != "1":
                return qs
        return qs.filter(Q(initiator=user) | Q(tasks__assignee=user) |
                         Q(subject_employee__user=user)).distinct()

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        inst = self.get_object()
        engine.cancel(inst, request.user, request.data.get("comment", ""))
        return Response(InstanceSerializer(inst, context={"request": request}).data)

    @action(detail=True, methods=["post"])
    def resubmit(self, request, pk=None):
        inst = self.get_object()
        engine.resubmit(inst, request.user, request.data.get("comment", ""))
        return Response(InstanceSerializer(inst, context={"request": request}).data)


class DelegationSerializer(TenantSerializer):
    delegate_name = DisplayField("delegate")
    delegator_name = DisplayField("delegator")

    class Meta(TenantSerializer.Meta):
        model = Delegation
        read_only_fields = TenantSerializer.Meta.read_only_fields + ["delegator"]

    def validate(self, attrs):
        if attrs.get("end_date") and attrs.get("start_date") and attrs["end_date"] < attrs["start_date"]:
            raise serializers.ValidationError("End date must be after start date.")
        if attrs.get("delegate") == self.context["request"].user:
            raise serializers.ValidationError("You cannot delegate to yourself.")
        return attrs


class DelegationViewSet(TenantModelViewSet):
    queryset = Delegation.objects.select_related("delegator", "delegate")
    serializer_class = DelegationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        if has_perm(self.request.user, "workflow.admin"):
            return qs
        return qs.filter(Q(delegator=self.request.user) | Q(delegate=self.request.user))

    def perform_create(self, serializer):
        serializer.save(delegator=self.request.user)
