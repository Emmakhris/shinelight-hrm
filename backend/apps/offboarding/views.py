import datetime as dt

from django.db.models import Q
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import BusinessRuleError
from apps.core.serializers import DisplayField
from apps.core.views import TenantModelViewSet
from apps.employees.models import Employee
from apps.rbac.services import has_perm, scope_queryset

from . import services
from .models import ClearanceItem, ExitInterview, Separation


class ItemSerializer(serializers.ModelSerializer):
    owner_label = serializers.CharField(source="get_owner_display", read_only=True)
    cleared_by_name = DisplayField("cleared_by")
    check = serializers.SerializerMethodField()
    can_clear = serializers.SerializerMethodField()

    class Meta:
        model = ClearanceItem
        fields = ["id", "order", "owner", "owner_label", "title", "auto_check", "status", "notes", "cleared_by_name",
                  "cleared_at", "check", "can_clear"]

    def get_check(self, obj):
        return services.check_status(obj) if obj.auto_check and obj.status == "pending" else None

    def get_can_clear(self, obj):
        return obj.status == "pending" and services.can_clear(obj, self.context["request"].user)


class SeparationSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    staff_number = serializers.CharField(source="employee.staff_number", read_only=True)
    department_name = serializers.CharField(source="employee.department.name", read_only=True, default=None)
    job_title = serializers.CharField(source="employee.job_title.name", read_only=True, default=None)
    exit_type_label = serializers.CharField(source="get_exit_type_display", read_only=True)
    reason_label = serializers.CharField(source="get_reason_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    handover_to_name = DisplayField("handover_to")
    progress = serializers.SerializerMethodField()

    class Meta:
        model = Separation
        fields = ["id", "reference", "employee", "employee_name", "staff_number", "department_name", "job_title",
                  "exit_type", "exit_type_label", "reason", "reason_label", "details", "notice_date",
                  "last_working_day", "notice_required_days", "notice_shortfall_days", "rehire_eligible",
                  "handover_to", "handover_to_name", "handover_notes", "access_extension_until", "status",
                  "status_label", "approved_at", "completed_at", "certificate", "progress"]
        read_only_fields = fields

    def get_progress(self, obj):
        items = list(obj.clearance.all())
        return {"total": len(items), "done": sum(i.status != "pending" for i in items)}


class SeparationDetailSerializer(SeparationSerializer):
    clearance = ItemSerializer(many=True, read_only=True)
    exit_interview = serializers.SerializerMethodField()
    questions = serializers.SerializerMethodField()

    class Meta(SeparationSerializer.Meta):
        fields = SeparationSerializer.Meta.fields + ["clearance", "exit_interview", "questions"]
        read_only_fields = fields

    def get_exit_interview(self, obj):
        ei = getattr(obj, "exit_interview", None)
        if ei is None:
            return None
        user = self.context["request"].user
        full = has_perm(user, "offboarding.manage") or obj.employee.user_id == user.pk
        data = {"completed_at": ei.completed_at}
        if full:  # interview answers are confidential to HR and the leaver
            data.update({"ratings": ei.ratings, "primary_reason": ei.primary_reason,
                         "what_went_well": ei.what_went_well, "what_to_improve": ei.what_to_improve,
                         "would_recommend": ei.would_recommend, "would_return": ei.would_return})
        return data

    def get_questions(self, obj):
        return ExitInterview.QUESTIONS


class InitiateSerializer(serializers.Serializer):
    employee = serializers.PrimaryKeyRelatedField(queryset=Employee.objects, required=False)
    exit_type = serializers.ChoiceField(choices=Separation.TYPES, default="resignation")
    reason = serializers.ChoiceField(choices=Separation.REASONS, required=False, allow_blank=True)
    details = serializers.CharField(required=False, allow_blank=True)
    notice_date = serializers.DateField(required=False)
    last_working_day = serializers.DateField()
    rehire_eligible = serializers.BooleanField(default=True)
    handover_to = serializers.PrimaryKeyRelatedField(queryset=Employee.objects, required=False, allow_null=True)


class SeparationViewSet(TenantModelViewSet):
    queryset = Separation.objects.select_related("employee__department", "employee__job_title", "handover_to") \
        .prefetch_related("clearance")
    perm_module = "offboarding"
    perm_map = {k: None for k in ("list", "retrieve", "create", "withdraw", "interview")}
    perm_map.update({"extend_access": "offboarding.manage"})
    http_method_names = ["get", "post", "head", "options"]
    filterset_fields = ["status", "exit_type", "employee"]
    search_fields = ["reference", "employee__first_name", "employee__last_name"]

    def get_serializer_class(self):
        return SeparationDetailSerializer if self.action != "list" else SeparationSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if self.request.query_params.get("mine") == "1":
            return qs.filter(employee__user=user)
        if self.request.query_params.get("clearance_for_me") == "1":
            ids = [i.separation_id for i in ClearanceItem.objects.filter(status="pending",
                                                                        separation__status="clearance")
                   .select_related("separation__employee__supervisor") if services.can_clear(i, user)]
            return qs.filter(pk__in=ids)
        cond = Q(employee__user=user) | Q(employee__supervisor__user=user)
        if has_perm(user, "offboarding.view"):
            cond |= Q(pk__in=scope_queryset(user, qs, "offboarding.view", "employee__").values("pk"))
        # clearance owners (IT, finance, payroll...) see exits they have items on
        if any(has_perm(user, p) for p in ("assets.manage", "payroll.prepare", "expenses.pay")):
            cond |= Q(status__in=["clearance", "completed"])
        return qs.filter(cond)

    def create(self, request, *args, **kwargs):
        s = InitiateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = dict(s.validated_data)
        emp = d.pop("employee", None) or getattr(request.user, "employee", None)
        if emp is None:
            raise BusinessRuleError("Your account is not linked to an employee record.")
        sep = services.initiate(request.user, emp, d)
        return Response(SeparationSerializer(sep, context=self.get_serializer_context()).data, status=201)

    @action(detail=True, methods=["post"])
    def withdraw(self, request, pk=None):
        sep = services.withdraw(self.get_object(), request.user, request.data.get("reason", ""))
        return Response(self.get_serializer(sep).data)

    @action(detail=True, methods=["post"], url_path="extend-access")
    def extend_access(self, request, pk=None):
        until = request.data.get("until")
        if not until:
            raise BusinessRuleError("Give the date access should end.")
        sep = services.extend_access(self.get_object(), request.user, dt.date.fromisoformat(until),
                                     request.data.get("reason", ""))
        return Response(self.get_serializer(sep).data)

    @action(detail=True, methods=["post"])
    def interview(self, request, pk=None):
        sep = self.get_object()
        services.submit_exit_interview(sep, request.user, request.data)
        sep.refresh_from_db()
        return Response(self.get_serializer(sep).data)


class ClearView(APIView):
    def post(self, request, pk):
        item = ClearanceItem.objects.filter(pk=pk).select_related("separation__employee").first()
        if item is None:
            raise NotFound()
        services.clear(item, request.user, request.data.get("notes", ""), bool(request.data.get("waive")))
        return Response(ItemSerializer(item, context={"request": request}).data)


class AnalyticsView(APIView):
    def get(self, request):
        if not has_perm(request.user, "offboarding.manage") and not has_perm(request.user, "reports.view"):
            raise PermissionDenied()
        return Response({**services.analytics(int(request.query_params.get("months") or 12)),
                         "upcoming": services.upcoming_exits(90)})
