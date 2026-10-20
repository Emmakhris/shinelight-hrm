from django.db.models import Q
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import BusinessRuleError
from apps.core.serializers import DisplayField, TenantSerializer
from apps.core.views import TenantModelViewSet
from apps.documents.models import Document, DocumentCategory
from apps.employees.models import Employee
from apps.organization.models import Department
from apps.rbac.models import Role
from apps.rbac.services import can_access_employee, has_perm

from . import services
from .models import ChecklistTemplate, ChecklistTemplateTask, Onboarding, OnboardingTask, ProbationReview


class TemplateTaskSerializer(TenantSerializer):
    template = serializers.PrimaryKeyRelatedField(queryset=ChecklistTemplate.objects)
    role = serializers.PrimaryKeyRelatedField(queryset=Role.objects, required=False, allow_null=True)
    document_category = serializers.PrimaryKeyRelatedField(queryset=DocumentCategory.objects, required=False,
                                                           allow_null=True)
    policy_document = serializers.PrimaryKeyRelatedField(queryset=Document.objects, required=False, allow_null=True)
    role_name = DisplayField("role")
    document_category_name = DisplayField("document_category")
    policy_document_name = DisplayField("policy_document")

    class Meta(TenantSerializer.Meta):
        model = ChecklistTemplateTask


class TemplateSerializer(TenantSerializer):
    department = serializers.PrimaryKeyRelatedField(queryset=Department.objects, required=False, allow_null=True)
    department_name = DisplayField("department", fallback="All departments")
    task_count = serializers.SerializerMethodField()

    class Meta(TenantSerializer.Meta):
        model = ChecklistTemplate

    def get_task_count(self, obj):
        return obj.tasks.count()


class TemplateViewSet(TenantModelViewSet):
    queryset = ChecklistTemplate.objects.select_related("department")
    serializer_class = TemplateSerializer
    perm_module = "onboarding"
    perm_read = "onboarding.view"
    perm_write = "onboarding.manage"
    pagination_class = None

    @action(detail=True, methods=["post"])
    def duplicate(self, request, pk=None):
        tpl = self.get_object()
        tasks = list(tpl.tasks.all())
        tpl.pk, tpl.id, tpl.name = None, None, f"{tpl.name} (copy)"
        tpl.save()
        for t in tasks:
            t.pk, t.id, t.template = None, None, tpl
            t.save()
        return Response(self.get_serializer(tpl).data, status=201)


class TemplateTaskViewSet(TenantModelViewSet):
    queryset = ChecklistTemplateTask.objects.select_related("role", "document_category", "policy_document")
    serializer_class = TemplateTaskSerializer
    perm_module = "onboarding"
    perm_read = "onboarding.view"
    perm_write = "onboarding.manage"
    filterset_fields = ["template"]
    pagination_class = None


class TaskSerializer(TenantSerializer):
    employee_name = serializers.CharField(source="onboarding.employee.full_name", read_only=True)
    employee_id = serializers.IntegerField(source="onboarding.employee_id", read_only=True)
    department_name = serializers.CharField(source="onboarding.employee.department.name", read_only=True,
                                            default=None)
    start_date = serializers.DateField(source="onboarding.start_date", read_only=True)
    owner_label = serializers.CharField(source="get_owner_type_display", read_only=True)
    category_label = serializers.CharField(source="get_category_display", read_only=True)
    completed_by_name = serializers.SerializerMethodField()
    role_name = DisplayField("role")
    assignee_name = serializers.SerializerMethodField()
    policy = serializers.SerializerMethodField()
    document_category_name = DisplayField("document_category")
    overdue = serializers.SerializerMethodField()
    can_complete = serializers.SerializerMethodField()
    assignee = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta(TenantSerializer.Meta):
        model = OnboardingTask
        read_only_fields = TenantSerializer.Meta.read_only_fields + [
            "onboarding", "status", "completed_by", "completed_at", "escalated_at", "response", "form",
            "policy_document", "document_category"]

    def get_completed_by_name(self, obj):
        return (obj.completed_by.get_full_name() or obj.completed_by.username) if obj.completed_by_id else None

    def get_assignee_name(self, obj):
        return (obj.assignee.get_full_name() or obj.assignee.username) if obj.assignee_id else None

    def get_policy(self, obj):
        d = obj.policy_document
        return {"id": d.id, "title": d.title} if d else None

    def get_overdue(self, obj):
        import datetime as dt

        return obj.status == "pending" and obj.due_date < dt.date.today()

    def get_can_complete(self, obj):
        request = self.context.get("request")
        if request is None:
            return False
        if "_my_task_ids" not in self.context:
            user = request.user
            self.context["_my_task_ids"] = None if has_perm(user, "onboarding.manage") else set(
                services.tasks_for_user(user).values_list("pk", flat=True))
        ids = self.context["_my_task_ids"]
        return ids is None or obj.pk in ids


class OnboardingSerializer(TenantSerializer):
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    staff_number = serializers.CharField(source="employee.staff_number", read_only=True)
    department_name = serializers.CharField(source="employee.department.name", read_only=True, default=None)
    job_title = serializers.CharField(source="employee.job_title.name", read_only=True, default=None)
    supervisor_name = serializers.CharField(source="employee.supervisor.full_name", read_only=True, default=None)
    probation_end_date = serializers.DateField(source="employee.probation_end_date", read_only=True)
    template_name = DisplayField("template")
    buddy_name = DisplayField("buddy")
    employee = serializers.PrimaryKeyRelatedField(queryset=Employee.objects)
    template = serializers.PrimaryKeyRelatedField(queryset=ChecklistTemplate.objects, required=False,
                                                  allow_null=True)
    buddy = serializers.PrimaryKeyRelatedField(queryset=Employee.objects, required=False, allow_null=True)
    start_date = serializers.DateField(required=False)
    progress = serializers.SerializerMethodField()

    class Meta(TenantSerializer.Meta):
        model = Onboarding
        read_only_fields = TenantSerializer.Meta.read_only_fields + ["status", "completed_at", "offer"]

    def get_progress(self, obj):
        return services.progress(obj)


class OnboardingViewSet(TenantModelViewSet):
    queryset = Onboarding.objects.select_related("employee__department", "employee__job_title",
                                                 "employee__supervisor", "template", "buddy") \
        .prefetch_related("tasks")
    serializer_class = OnboardingSerializer
    perm_module = "onboarding"
    perm_read = "onboarding.view"
    perm_write = "onboarding.manage"
    scope_prefix = "employee__"
    http_method_names = ["get", "post", "patch", "head", "options"]
    filterset_fields = ["status", "employee", "employee__department"]
    search_fields = ["employee__first_name", "employee__last_name", "employee__staff_number"]

    def perform_create(self, serializer):
        d = serializer.validated_data
        serializer.instance = services.start(d["employee"], self.request.user, template=d.get("template"),
                                             start_date=d.get("start_date"), buddy=d.get("buddy"))

    def perform_update(self, serializer):
        for k in ("employee", "template", "start_date"):
            serializer.validated_data.pop(k, None)
        serializer.save()

    @action(detail=True)
    def tasks(self, request, pk=None):
        ob = self.get_object()
        return Response(TaskSerializer(ob.tasks.select_related("completed_by", "role", "assignee",
                                                               "policy_document", "document_category"),
                                       many=True, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        ob = self.get_object()
        if ob.status != "in_progress":
            raise BusinessRuleError("Only onboardings in progress can be cancelled.")
        ob.status = "cancelled"
        ob.save(update_fields=["status", "updated_at"])
        return Response(self.get_serializer(ob).data)

    @action(detail=True, methods=["post"], url_path="add-task")
    def add_task(self, request, pk=None):
        ob = self.get_object()
        s = TaskSerializer(data=request.data, context=self.get_serializer_context())
        s.is_valid(raise_exception=True)
        t = s.save(onboarding=ob)
        return Response(TaskSerializer(t, context=self.get_serializer_context()).data, status=201)

    @action(detail=False)
    def dashboard(self, request):
        return Response(services.dashboard())


class TaskViewSet(TenantModelViewSet):
    """Onboarding tasks. `?mine=1` lists the tasks the user is responsible for (any role)."""

    queryset = OnboardingTask.objects.select_related("onboarding__employee__department", "completed_by", "role",
                                                     "assignee", "policy_document", "document_category")
    serializer_class = TaskSerializer
    perm_module = "onboarding"
    perm_map = {"list": None, "retrieve": None, "complete": None, "partial_update": None, "update": None,
                "waive": "onboarding.manage", "reopen": "onboarding.manage", "destroy": "onboarding.manage"}
    http_method_names = ["get", "patch", "post", "delete", "head", "options"]
    filterset_fields = ["status", "owner_type", "category", "onboarding"]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        mine = self.request.query_params.get("mine") == "1"
        if mine or not has_perm(user, "onboarding.view"):
            qs = qs.filter(pk__in=services.tasks_for_user(user).values("pk"))
        if self.request.query_params.get("open") == "1":
            qs = qs.filter(status="pending")
        if self.request.query_params.get("overdue") == "1":
            import datetime as dt

            qs = qs.filter(status="pending", due_date__lt=dt.date.today())
        return qs

    def create(self, request, *args, **kwargs):
        raise BusinessRuleError("Add tasks from the onboarding record.")

    def perform_update(self, serializer):
        task = serializer.instance
        if not services.can_work(task, self.request.user):
            raise PermissionDenied("This task is not assigned to you.")
        allowed = {"notes"} | ({"due_date", "assignee", "title", "description"}
                               if has_perm(self.request.user, "onboarding.manage") else set())
        for k in list(serializer.validated_data):
            if k not in allowed:
                serializer.validated_data.pop(k)
        serializer.save()

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        task = self.get_object()
        services.complete_task(task, request.user, request.data.get("response") or {}, request.data.get("notes", ""))
        return Response(self.get_serializer(task).data)

    @action(detail=True, methods=["post"])
    def waive(self, request, pk=None):
        task = self.get_object()
        services.waive_task(task, request.user, request.data.get("reason", ""))
        return Response(self.get_serializer(task).data)

    @action(detail=True, methods=["post"])
    def reopen(self, request, pk=None):
        return Response(self.get_serializer(services.reopen_task(self.get_object(), request.user)).data)


class ReviewSerializer(TenantSerializer):
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    staff_number = serializers.CharField(source="employee.staff_number", read_only=True)
    department_name = serializers.CharField(source="employee.department.name", read_only=True, default=None)
    job_title = serializers.CharField(source="employee.job_title.name", read_only=True, default=None)
    hire_date = serializers.DateField(source="employee.hire_date", read_only=True)
    probation_end_date = serializers.DateField(source="employee.probation_end_date", read_only=True)
    reviewer_name = serializers.SerializerMethodField()
    criteria = serializers.SerializerMethodField()
    can_review = serializers.SerializerMethodField()
    is_self = serializers.SerializerMethodField()
    reviewer = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta(TenantSerializer.Meta):
        model = ProbationReview
        read_only_fields = [f.name for f in ProbationReview._meta.fields if f.name not in ("due_date",)]

    def get_reviewer_name(self, obj):
        return (obj.reviewer.get_full_name() or obj.reviewer.username) if obj.reviewer_id else None

    def get_criteria(self, obj):
        return ProbationReview.CRITERIA

    def get_can_review(self, obj):
        user = self.context["request"].user
        return obj.status in ("scheduled", "returned") and services.can_review(obj, user) \
            and obj.employee.user_id != user.pk

    def get_is_self(self, obj):
        return obj.employee.user_id == self.context["request"].user.pk

    def to_representation(self, obj):
        data = super().to_representation(obj)
        # the employee sees the review only once it has been submitted
        if data["is_self"] and obj.status in ("scheduled", "returned"):
            for k in ("ratings", "overall_rating", "strengths", "improvements", "recommendation",
                      "reviewer_comments", "extend_months"):
                data[k] = None
        return data


class ReviewViewSet(TenantModelViewSet):
    queryset = ProbationReview.objects.select_related("employee__department", "employee__job_title", "reviewer")
    serializer_class = ReviewSerializer
    perm_module = "onboarding"
    perm_map = {"list": None, "retrieve": None, "submit": None, "acknowledge": None,
                "partial_update": "onboarding.manage", "update": "onboarding.manage", "reassign": "onboarding.manage",
                "schedule": "onboarding.manage"}
    http_method_names = ["get", "patch", "post", "head", "options"]
    filterset_fields = ["status", "review_type", "employee"]
    search_fields = ["employee__first_name", "employee__last_name"]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        emp = getattr(user, "employee", None)
        mine = Q(reviewer=user) | Q(reviewer__isnull=True, employee__supervisor__user=user)
        if emp:
            mine |= Q(employee=emp, status__in=["submitted", "completed", "rejected"])
        if self.request.query_params.get("mine") == "1" or not has_perm(user, "onboarding.view"):
            return qs.filter(mine)
        from apps.rbac.services import scope_queryset

        return (scope_queryset(user, qs, "onboarding.view", "employee__") | qs.filter(mine)).distinct()

    def create(self, request, *args, **kwargs):
        raise BusinessRuleError("Probation reviews are scheduled automatically; use 'schedule' for an employee.")

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        review = self.get_object()
        services.submit_review(review, request.user, request.data)
        return Response(self.get_serializer(review).data)

    @action(detail=True, methods=["post"])
    def acknowledge(self, request, pk=None):
        review = self.get_object()
        services.acknowledge_review(review, request.user, request.data.get("comments", ""))
        return Response(self.get_serializer(review).data)

    @action(detail=True, methods=["post"])
    def reassign(self, request, pk=None):
        from django.contrib.auth import get_user_model

        review = self.get_object()
        user = get_user_model().objects.filter(pk=request.data.get("reviewer"),
                                               organization=request.user.organization).first()
        if user is None:
            raise BusinessRuleError("Select a reviewer.")
        review.reviewer = user
        review.save(update_fields=["reviewer", "updated_at"])
        return Response(self.get_serializer(review).data)

    @action(detail=False, methods=["post"])
    def schedule(self, request):
        emp = Employee.objects.filter(pk=request.data.get("employee")).first()
        if emp is None or not can_access_employee(request.user, "onboarding.manage", emp):
            raise BusinessRuleError("Select an employee.")
        if emp.status != "probation" or not emp.probation_end_date:
            raise BusinessRuleError("The employee is not on probation (set a probation end date first).")
        created = services.schedule_probation_reviews(emp)
        return Response({"created": len(created)})


class MyOnboardingView(APIView):
    """The new hire's own onboarding: progress, their tasks and their buddy."""

    def get(self, request):
        emp = getattr(request.user, "employee", None)
        ob = Onboarding.objects.filter(employee=emp).exclude(status="cancelled").first() if emp else None
        if ob is None:
            return Response(None)
        ctx = {"request": request}
        return Response({
            "onboarding": OnboardingSerializer(ob, context=ctx).data,
            "my_tasks": TaskSerializer(ob.tasks.filter(owner_type="employee", assignee__isnull=True),
                                       many=True, context=ctx).data,
            "others": [{"title": t.title, "owner": t.get_owner_type_display(), "status": t.status,
                        "due_date": t.due_date} for t in ob.tasks.exclude(owner_type="employee")
                       .filter(category__in=["equipment", "access", "induction"])],
        })
