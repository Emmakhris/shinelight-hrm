import datetime as dt

from django.contrib.auth import get_user_model
from django.db.models import Q
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from apps.core.exceptions import BusinessRuleError
from apps.core.serializers import DisplayField, TenantSerializer
from apps.core.views import TenantModelViewSet
from apps.employees.models import Employee
from apps.organization.models import Department
from apps.rbac.services import has_perm, scope_queryset

from . import services
from .models import (
    Appraisal,
    AppraisalTemplate,
    Competency,
    CompetencyRating,
    FeedbackRequest,
    Goal,
    ImprovementPlan,
    Objective,
    PlanMilestone,
    RatingScale,
    ReviewCycle,
)


def _user_name(u):
    return (u.get_full_name() or u.username) if u else None


# ---------------------------------------------------------------- configuration
class ScaleSerializer(TenantSerializer):
    class Meta(TenantSerializer.Meta):
        model = RatingScale

    def validate_levels(self, levels):
        if not isinstance(levels, list) or len(levels) < 3:
            raise serializers.ValidationError("Define at least three levels.")
        values = [lv.get("value") for lv in levels]
        if any(not isinstance(v, int) for v in values) or len(set(values)) != len(values):
            raise serializers.ValidationError("Each level needs a unique whole-number value.")
        return levels


class ScaleViewSet(TenantModelViewSet):
    queryset = RatingScale.objects.all()
    serializer_class = ScaleSerializer
    perm_module = "performance"
    perm_map = {"list": None, "retrieve": None}
    perm_write = "performance.manage"
    pagination_class = None


class CompetencySerializer(TenantSerializer):
    class Meta(TenantSerializer.Meta):
        model = Competency


class CompetencyViewSet(TenantModelViewSet):
    queryset = Competency.objects.all()
    serializer_class = CompetencySerializer
    perm_module = "performance"
    perm_map = {"list": None, "retrieve": None}
    perm_write = "performance.manage"
    pagination_class = None
    filterset_fields = ["category", "is_active"]


class TemplateSerializer(TenantSerializer):
    rating_scale = serializers.PrimaryKeyRelatedField(queryset=RatingScale.objects)
    competencies = serializers.PrimaryKeyRelatedField(queryset=Competency.objects, many=True, required=False)
    rating_scale_name = DisplayField("rating_scale")
    job_family_name = DisplayField("job_family")
    category_name = DisplayField("category")
    competencies_weight = serializers.IntegerField(read_only=True)

    class Meta(TenantSerializer.Meta):
        model = AppraisalTemplate

    def validate_objectives_weight(self, v):
        if v > 100:
            raise serializers.ValidationError("Must be 0-100.")
        return v


class TemplateViewSet(TenantModelViewSet):
    queryset = AppraisalTemplate.objects.select_related("rating_scale", "job_family", "category") \
        .prefetch_related("competencies")
    serializer_class = TemplateSerializer
    perm_module = "performance"
    perm_read = "performance.manage"
    perm_write = "performance.manage"
    pagination_class = None


class CycleSerializer(TenantSerializer):
    departments = serializers.PrimaryKeyRelatedField(queryset=Department.objects, many=True, required=False)
    counts = serializers.SerializerMethodField()

    class Meta(TenantSerializer.Meta):
        model = ReviewCycle
        read_only_fields = TenantSerializer.Meta.read_only_fields + ["status", "launched_at", "closed_at"]

    def get_counts(self, obj):
        return {"appraisals": obj.appraisals.count(),
                "completed": obj.appraisals.filter(status="completed").count()}


class CycleViewSet(TenantModelViewSet):
    queryset = ReviewCycle.objects.prefetch_related("departments")
    serializer_class = CycleSerializer
    perm_module = "performance"
    perm_read = "performance.manage"
    perm_write = "performance.manage"
    perm_map = {"list": None, "retrieve": None}
    filterset_fields = ["status"]

    def perform_update(self, serializer):
        if serializer.instance.status == "closed":
            raise BusinessRuleError("Closed cycles cannot be changed.")
        serializer.save()

    def perform_destroy(self, instance):
        if instance.status != "draft":
            raise BusinessRuleError("Only draft cycles can be deleted.")
        instance.delete()

    @action(detail=True, methods=["post"])
    def launch(self, request, pk=None):
        return Response(services.launch_cycle(self.get_object(), request.user))

    @action(detail=True, methods=["post"])
    def advance(self, request, pk=None):
        return Response(services.advance_cycle(self.get_object(), request.user))

    @action(detail=True)
    def summary(self, request, pk=None):
        if not has_perm(request.user, "performance.manage"):
            raise PermissionDenied()
        return Response(services.cycle_summary(self.get_object()))


class GoalSerializer(TenantSerializer):
    cycle = serializers.PrimaryKeyRelatedField(queryset=ReviewCycle.objects)
    parent = serializers.PrimaryKeyRelatedField(queryset=Goal.objects, required=False, allow_null=True)
    department = serializers.PrimaryKeyRelatedField(queryset=Department.objects, required=False, allow_null=True)
    owner = serializers.PrimaryKeyRelatedField(queryset=Employee.objects, required=False, allow_null=True)
    department_name = DisplayField("department", fallback="Organization-wide")
    parent_title = DisplayField("parent")
    owner_name = DisplayField("owner")
    aligned_objectives = serializers.SerializerMethodField()

    class Meta(TenantSerializer.Meta):
        model = Goal

    def get_aligned_objectives(self, obj):
        return obj.objectives.count()


class GoalViewSet(TenantModelViewSet):
    """Organization and department goals. Everyone can read them to align their objectives."""

    queryset = Goal.objects.select_related("department", "parent", "owner")
    serializer_class = GoalSerializer
    perm_module = "performance"
    perm_map = {"list": None, "retrieve": None}
    perm_write = "performance.manage"
    filterset_fields = ["cycle", "department"]
    pagination_class = None


# ---------------------------------------------------------------- appraisals
class ObjectiveSerializer(TenantSerializer):
    appraisal = serializers.PrimaryKeyRelatedField(queryset=Appraisal.objects)
    goal = serializers.PrimaryKeyRelatedField(queryset=Goal.objects, required=False, allow_null=True)
    goal_title = DisplayField("goal")

    class Meta(TenantSerializer.Meta):
        model = Objective
        read_only_fields = TenantSerializer.Meta.read_only_fields + [
            "midyear_status", "midyear_comment", "achievement", "self_rating", "manager_rating", "manager_comment"]


class CompetencyRatingSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="competency.name", read_only=True)
    category = serializers.CharField(source="competency.get_category_display", read_only=True)
    description = serializers.CharField(source="competency.description", read_only=True)

    class Meta:
        model = CompetencyRating
        fields = ["id", "competency", "name", "category", "description", "self_rating", "manager_rating", "comment"]


MANAGER_FIELDS = ["manager_rating", "final_rating", "objectives_score", "competencies_score", "overall_score",
                  "manager_comments", "development_needs"]


class AppraisalSerializer(TenantSerializer):
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    staff_number = serializers.CharField(source="employee.staff_number", read_only=True)
    department_name = serializers.CharField(source="employee.department.name", read_only=True, default=None)
    job_title = serializers.CharField(source="employee.job_title.name", read_only=True, default=None)
    cycle_name = serializers.CharField(source="cycle.name", read_only=True)
    cycle_status = serializers.CharField(source="cycle.status", read_only=True)
    template_name = serializers.CharField(source="template.name", read_only=True)
    reviewer_name = serializers.SerializerMethodField()
    final_rating_label = serializers.SerializerMethodField()
    role = serializers.SerializerMethodField()

    class Meta(TenantSerializer.Meta):
        model = Appraisal
        fields = ["id", "cycle", "cycle_name", "cycle_status", "employee", "employee_name", "staff_number",
                  "department_name", "job_title", "template", "template_name", "reviewer", "reviewer_name", "status",
                  "manager_rating", "final_rating", "final_rating_label", "overall_score", "employee_agrees",
                  "acknowledged_at", "role"]
        exclude = None
        read_only_fields = fields

    def get_reviewer_name(self, obj):
        return _user_name(obj.reviewer)

    def _role(self, obj):
        user = self.context["request"].user
        if obj.employee.user_id == user.pk:
            return "employee"
        if obj.reviewer_id == user.pk:
            return "reviewer"
        return "hr" if has_perm(user, "performance.manage") else "viewer"

    def get_role(self, obj):
        return self._role(obj)

    def get_final_rating_label(self, obj):
        return obj.template.rating_scale.label(obj.final_rating)

    def to_representation(self, obj):
        data = super().to_representation(obj)
        if self._role(obj) == "employee" and obj.status not in ("acknowledgement", "completed"):
            for k in MANAGER_FIELDS + ["final_rating_label"]:
                if k in data:
                    data[k] = None
        return data


class AppraisalDetailSerializer(AppraisalSerializer):
    objectives = ObjectiveSerializer(many=True, read_only=True)
    competency_ratings = CompetencyRatingSerializer(many=True, read_only=True)
    scale = serializers.JSONField(source="template.rating_scale.levels", read_only=True)
    objectives_weight = serializers.IntegerField(source="template.objectives_weight", read_only=True)
    min_objectives = serializers.IntegerField(source="template.min_objectives", read_only=True)
    max_objectives = serializers.IntegerField(source="template.max_objectives", read_only=True)
    include_360 = serializers.BooleanField(source="template.include_360", read_only=True)
    cycle_deadlines = serializers.SerializerMethodField()
    feedback_requests = serializers.SerializerMethodField()
    plans = serializers.SerializerMethodField()
    can = serializers.SerializerMethodField()

    class Meta(AppraisalSerializer.Meta):
        fields = AppraisalSerializer.Meta.fields + [
            "objectives", "competency_ratings", "scale", "objectives_weight", "min_objectives", "max_objectives",
            "include_360", "objectives_score", "competencies_score", "midyear_comments", "midyear_done_at",
            "self_comments", "manager_comments", "development_needs", "employee_comments", "calibration_reason",
            "self_submitted_at", "manager_submitted_at", "completed_at", "cycle_deadlines", "feedback_requests",
            "plans", "can"]
        read_only_fields = fields

    def get_cycle_deadlines(self, obj):
        c = obj.cycle
        return {"goal_setting": c.goal_setting_deadline, "midyear": c.midyear_date,
                "self_review": c.self_review_deadline, "manager_review": c.manager_review_deadline}

    def get_feedback_requests(self, obj):
        # who was asked and whether they answered, never what they said
        if self._role(obj) not in ("employee", "reviewer", "hr"):
            return []
        return [{"id": f.id, "respondent": _user_name(f.respondent), "relationship": f.get_relationship_display(),
                 "status": f.status} for f in obj.feedback_requests.select_related("respondent")]

    def get_plans(self, obj):
        return [{"id": p.id, "status": p.status, "start_date": p.start_date, "end_date": p.end_date}
                for p in obj.pips.all()]

    def get_can(self, obj):
        user = self.context["request"].user
        role = self._role(obj)
        return {
            "edit_objectives": services.objectives_editable(obj, user),
            "midyear": obj.status == "objectives_agreed" and role in ("employee", "reviewer"),
            "self_review": obj.status == "self_review" and role == "employee",
            "manager_review": role in ("reviewer", "hr") and (obj.status == "manager_review"
                                                               or services._manager_can_skip_self(obj)),
            "calibrate": obj.status == "calibration" and has_perm(user, "performance.manage"),
            "acknowledge": obj.status == "acknowledgement" and role == "employee",
            "request_feedback": obj.template.include_360 and role in ("employee", "reviewer", "hr")
            and obj.status not in ("calibration", "acknowledgement", "completed", "cancelled"),
            "plan": role in ("reviewer", "hr") and obj.final_rating is not None,
        }

    def to_representation(self, obj):
        data = super().to_representation(obj)
        role = self._role(obj)
        hide_manager = role == "employee" and obj.status not in ("acknowledgement", "completed")
        if hide_manager:
            for o in data["objectives"]:
                o["manager_rating"], o["manager_comment"] = None, ""
            for c in data["competency_ratings"]:
                c["manager_rating"], c["comment"] = None, ""
        if role == "employee":
            data["calibration_reason"] = ""
        return data


class AppraisalViewSet(TenantModelViewSet):
    queryset = Appraisal.objects.select_related("employee__department", "employee__job_title", "cycle",
                                                "template__rating_scale", "reviewer")
    perm_module = "performance"
    perm_map = {k: None for k in ("list", "retrieve", "submit_objectives", "midyear", "self_review", "manager_review",
                                  "acknowledge", "request_feedback", "feedback_summary")}
    perm_map.update({"calibrate": "performance.manage", "reassign": "performance.manage",
                     "cancel": "performance.manage"})
    http_method_names = ["get", "post", "head", "options"]
    filterset_fields = ["cycle", "status", "final_rating", "employee", "employee__department"]
    search_fields = ["employee__first_name", "employee__last_name", "employee__staff_number"]

    def get_serializer_class(self):
        return AppraisalDetailSerializer if self.action != "list" else AppraisalSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        p = self.request.query_params
        if p.get("mine") == "1":
            return qs.filter(employee__user=user)
        if p.get("team") == "1":
            return qs.filter(reviewer=user)
        if self.action == "list" and not has_perm(user, "performance.view"):
            return qs.filter(Q(employee__user=user) | Q(reviewer=user))
        own = Q(employee__user=user) | Q(reviewer=user)
        return (scope_queryset(user, qs, "performance.view", "employee__") | qs.filter(own)).distinct()

    def create(self, request, *args, **kwargs):
        raise BusinessRuleError("Appraisals are created by launching a review cycle.")

    def _get(self):
        ap = self.get_object()
        if not services.can_view(ap, self.request.user):
            raise PermissionDenied()
        return ap

    def _out(self, ap):
        ap.refresh_from_db()
        return Response(AppraisalDetailSerializer(ap, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["post"], url_path="submit-objectives")
    def submit_objectives(self, request, pk=None):
        ap = self._get()
        services.submit_objectives(ap, request.user)
        return self._out(ap)

    @action(detail=True, methods=["post"])
    def midyear(self, request, pk=None):
        ap = self._get()
        services.record_midyear(ap, request.user, request.data.get("objectives"), request.data.get("comments", ""))
        return self._out(ap)

    @action(detail=True, methods=["post"], url_path="self-review")
    def self_review(self, request, pk=None):
        ap = self._get()
        services.save_self_review(ap, request.user, request.data, submit=bool(request.data.get("submit")))
        return self._out(ap)

    @action(detail=True, methods=["post"], url_path="manager-review")
    def manager_review(self, request, pk=None):
        ap = self._get()
        services.save_manager_review(ap, request.user, request.data, submit=bool(request.data.get("submit")))
        return self._out(ap)

    @action(detail=True, methods=["post"])
    def calibrate(self, request, pk=None):
        ap = self._get()
        services.calibrate(ap, request.user, request.data.get("rating"), request.data.get("reason", ""))
        return self._out(ap)

    @action(detail=True, methods=["post"])
    def acknowledge(self, request, pk=None):
        ap = self._get()
        agrees = request.data.get("agrees")
        services.acknowledge(ap, request.user, agrees in (True, "true", "1", 1), request.data.get("comments", ""))
        return self._out(ap)

    @action(detail=True, methods=["post"])
    def reassign(self, request, pk=None):
        ap = self._get()
        user = get_user_model().objects.filter(pk=request.data.get("reviewer"),
                                               organization=request.user.organization, is_active=True).first()
        if user is None:
            raise BusinessRuleError("Select a reviewer.")
        services.reassign_reviewer(ap, request.user, user)
        return self._out(ap)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        ap = self._get()
        if ap.status == "completed":
            raise BusinessRuleError("Completed appraisals cannot be cancelled.")
        if not request.data.get("reason"):
            raise BusinessRuleError("Give a reason (e.g. long-term leave, exit).")
        ap.status = "cancelled"
        ap.manager_comments = (ap.manager_comments + "\n" if ap.manager_comments else "") + \
            f"Cancelled: {request.data['reason']}"
        ap.save(update_fields=["status", "manager_comments", "updated_at"])
        return self._out(ap)

    @action(detail=True, methods=["post"], url_path="request-feedback")
    def request_feedback(self, request, pk=None):
        ap = self._get()
        created = services.request_feedback(ap, request.user, request.data.get("respondents") or [])
        return Response({"requested": len(created)})

    @action(detail=True, url_path="feedback-summary")
    def feedback_summary(self, request, pk=None):
        ap = self._get()
        if services.is_employee(ap, request.user) and ap.status not in ("acknowledgement", "completed"):
            return Response({"available_after_review": True})
        return Response(services.feedback_summary(ap))


class ObjectiveViewSet(TenantModelViewSet):
    queryset = Objective.objects.select_related("appraisal__employee", "goal")
    serializer_class = ObjectiveSerializer
    perm_module = "performance"
    perm_map = {k: None for k in ("list", "retrieve", "create", "update", "partial_update", "destroy")}
    filterset_fields = ["appraisal"]
    pagination_class = None

    def get_queryset(self):
        user = self.request.user
        visible = Appraisal.objects.filter(Q(employee__user=user) | Q(reviewer=user))
        if has_perm(user, "performance.view"):
            visible = visible | scope_queryset(user, Appraisal.objects.all(), "performance.view", "employee__")
        return super().get_queryset().filter(appraisal__in=visible.values("pk"))

    def _check(self, ap):
        if not services.objectives_editable(ap, self.request.user):
            raise BusinessRuleError("Objectives can only be changed while they are being set or after being "
                                    "returned.")

    def perform_create(self, serializer):
        ap = serializer.validated_data["appraisal"]
        self._check(ap)
        if ap.objectives.count() >= ap.template.max_objectives:
            raise BusinessRuleError(f"At most {ap.template.max_objectives} objectives.")
        serializer.save()

    def perform_update(self, serializer):
        self._check(serializer.instance.appraisal)
        serializer.validated_data.pop("appraisal", None)
        serializer.save()

    def perform_destroy(self, instance):
        self._check(instance.appraisal)
        instance.delete()


# ---------------------------------------------------------------- 360 feedback (respondent side)
class FeedbackSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source="appraisal.employee.full_name", read_only=True)
    job_title = serializers.CharField(source="appraisal.employee.job_title.name", read_only=True, default=None)
    cycle_name = serializers.CharField(source="appraisal.cycle.name", read_only=True)
    relationship_label = serializers.CharField(source="get_relationship_display", read_only=True)
    competencies = serializers.SerializerMethodField()
    scale = serializers.JSONField(source="appraisal.template.rating_scale.levels", read_only=True)

    class Meta:
        model = FeedbackRequest
        fields = ["id", "employee_name", "job_title", "cycle_name", "relationship", "relationship_label", "status",
                  "ratings", "strengths", "improvements", "submitted_at", "competencies", "scale"]

    def get_competencies(self, obj):
        return [{"id": c.competency_id, "name": c.competency.name, "description": c.competency.description}
                for c in obj.appraisal.competency_ratings.select_related("competency")]


class FeedbackViewSet(TenantModelViewSet):
    """The respondent's own feedback requests only."""

    queryset = FeedbackRequest.objects.select_related("appraisal__employee__job_title", "appraisal__cycle",
                                                      "appraisal__template__rating_scale")
    serializer_class = FeedbackSerializer
    perm_module = "performance"
    perm_map = {"list": None, "retrieve": None, "submit": None}
    http_method_names = ["get", "post", "head", "options"]
    filterset_fields = ["status"]

    def get_queryset(self):
        return super().get_queryset().filter(respondent=self.request.user)

    def create(self, request, *args, **kwargs):
        raise BusinessRuleError("Feedback is requested from an appraisal.")

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        fr = self.get_object()
        services.submit_feedback(fr, request.user, request.data.get("ratings"), request.data.get("strengths", ""),
                                 request.data.get("improvements", ""), bool(request.data.get("decline")))
        return Response(self.get_serializer(fr).data)


# ---------------------------------------------------------------- improvement plans
class MilestoneSerializer(TenantSerializer):
    plan = serializers.PrimaryKeyRelatedField(queryset=ImprovementPlan.objects)

    class Meta(TenantSerializer.Meta):
        model = PlanMilestone


class PlanSerializer(TenantSerializer):
    employee = serializers.PrimaryKeyRelatedField(queryset=Employee.objects)
    appraisal = serializers.PrimaryKeyRelatedField(queryset=Appraisal.objects, required=False, allow_null=True)
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    department_name = serializers.CharField(source="employee.department.name", read_only=True, default=None)
    supervisor_name = serializers.SerializerMethodField()
    milestones = MilestoneSerializer(many=True, read_only=True)
    is_mine = serializers.SerializerMethodField()
    submit = serializers.BooleanField(write_only=True, default=False)

    class Meta(TenantSerializer.Meta):
        model = ImprovementPlan
        read_only_fields = TenantSerializer.Meta.read_only_fields + [
            "status", "supervisor", "outcome_notes", "employee_acknowledged_at", "employee_comments", "closed_at"]

    def get_supervisor_name(self, obj):
        return _user_name(obj.supervisor)

    def get_is_mine(self, obj):
        return obj.employee.user_id == self.context["request"].user.pk


class PlanViewSet(TenantModelViewSet):
    queryset = ImprovementPlan.objects.select_related("employee__department", "supervisor") \
        .prefetch_related("milestones")
    serializer_class = PlanSerializer
    perm_module = "performance"
    perm_map = {k: None for k in ("list", "retrieve", "create", "update", "partial_update", "submit", "close",
                                  "acknowledge")}
    http_method_names = ["get", "post", "patch", "head", "options"]
    filterset_fields = ["status", "employee"]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        own = Q(employee__user=user, status__in=["active", "extended", "successful", "unsuccessful"]) | \
            Q(supervisor=user)
        if self.request.query_params.get("mine") == "1" or not has_perm(user, "performance.view"):
            qs = qs.filter(own)
        else:
            qs = (scope_queryset(user, qs, "performance.view", "employee__") | qs.filter(own)).distinct()
        # the employee sees their plan only once HR has approved it
        return qs.exclude(Q(employee__user=user) & ~Q(status__in=["active", "extended", "successful",
                                                                 "unsuccessful"]))

    def perform_create(self, serializer):
        emp = serializer.validated_data["employee"]
        user = self.request.user
        sup = emp.supervisor
        if not (has_perm(user, "performance.manage") or (sup and sup.user_id == user.pk)):
            raise PermissionDenied("Only the employee's supervisor or HR can open an improvement plan.")
        if emp.user_id == user.pk:
            raise PermissionDenied()
        submit = serializer.validated_data.pop("submit", False)
        plan = serializer.save(supervisor=sup.user if sup and sup.user_id else user)
        if submit:
            services.submit_plan(plan, user)

    def perform_update(self, serializer):
        plan = serializer.instance
        if plan.status not in ("draft", "returned") or not services.can_manage_plan(plan, self.request.user):
            raise BusinessRuleError("Only draft or returned plans can be edited by the supervisor or HR.")
        serializer.validated_data.pop("submit", None)
        serializer.validated_data.pop("employee", None)
        serializer.save()

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        plan = self.get_object()
        if not services.can_manage_plan(plan, request.user):
            raise PermissionDenied()
        return Response(self.get_serializer(services.submit_plan(plan, request.user)).data)

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        plan = self.get_object()
        end = request.data.get("new_end_date")
        services.close_plan(plan, request.user, request.data.get("outcome", ""), request.data.get("notes", ""),
                            dt.date.fromisoformat(end) if end else None)
        return Response(self.get_serializer(plan).data)

    @action(detail=True, methods=["post"])
    def acknowledge(self, request, pk=None):
        from django.utils import timezone

        plan = self.get_object()
        if plan.employee.user_id != request.user.pk:
            raise PermissionDenied()
        if plan.status not in ("active", "extended"):
            raise BusinessRuleError("This plan is not active.")
        plan.employee_acknowledged_at = timezone.now()
        plan.employee_comments = request.data.get("comments", "")
        plan.save(update_fields=["employee_acknowledged_at", "employee_comments", "updated_at"])
        return Response(self.get_serializer(plan).data)


class MilestoneViewSet(TenantModelViewSet):
    queryset = PlanMilestone.objects.select_related("plan")
    serializer_class = MilestoneSerializer
    perm_module = "performance"
    perm_map = {k: None for k in ("list", "retrieve", "create", "update", "partial_update", "destroy")}
    filterset_fields = ["plan"]
    pagination_class = None

    def get_queryset(self):
        user = self.request.user
        plans = ImprovementPlan.objects.filter(Q(supervisor=user) | Q(employee__user=user))
        if has_perm(user, "performance.manage"):
            plans = ImprovementPlan.objects.all()
        return super().get_queryset().filter(plan__in=plans.values("pk"))

    def _check(self, plan, status_only=False):
        if not services.can_manage_plan(plan, self.request.user) or plan.employee.user_id == self.request.user.pk:
            raise PermissionDenied()
        if not status_only and plan.status not in ("draft", "returned"):
            raise BusinessRuleError("Milestones are fixed once the plan is approved; record progress instead.")

    def perform_create(self, serializer):
        self._check(serializer.validated_data["plan"])
        serializer.save()

    def perform_update(self, serializer):
        plan = serializer.instance.plan
        locked = plan.status in ("active", "extended")
        self._check(plan, status_only=locked)
        if locked:  # only progress fields can change on an active plan
            for k in list(serializer.validated_data):
                if k not in ("status", "review_notes"):
                    serializer.validated_data.pop(k)
        serializer.save()

    def perform_destroy(self, instance):
        self._check(instance.plan)
        instance.delete()
