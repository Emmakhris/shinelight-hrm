from django.contrib.auth import get_user_model
from django.db.models import Q
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.serializers import DisplayField, TenantSerializer
from apps.core.views import TenantModelViewSet
from apps.employees.models import Employee
from apps.organization.models import Department
from apps.rbac.services import best_scope, department_descendants, has_perm

from . import services
from .models import CorrectiveAction, Incident, Inspection, OHRecord, RiskAssessment

User = get_user_model()


def _name(u):
    return (u.get_full_name() or u.username) if u else None


class ActionSerializer(TenantSerializer):
    owner = serializers.PrimaryKeyRelatedField(queryset=User.objects.none(), required=False, allow_null=True)
    owner_name = serializers.SerializerMethodField()
    source = serializers.SerializerMethodField()
    incident = serializers.PrimaryKeyRelatedField(queryset=Incident.objects, required=False, allow_null=True)
    risk_assessment = serializers.PrimaryKeyRelatedField(queryset=RiskAssessment.objects, required=False,
                                                         allow_null=True)
    inspection = serializers.PrimaryKeyRelatedField(queryset=Inspection.objects, required=False, allow_null=True)

    class Meta(TenantSerializer.Meta):
        model = CorrectiveAction
        read_only_fields = TenantSerializer.Meta.read_only_fields + ["status", "completed_at", "reminded_at"]

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        req = self.context.get("request")
        if req is not None:
            self.fields["owner"].queryset = User.objects.filter(organization=req.user.organization, is_active=True)

    def get_owner_name(self, obj):
        return _name(obj.owner)

    def get_source(self, obj):
        if obj.incident_id:
            return f"Incident {obj.incident.reference}"
        if obj.risk_assessment_id:
            return f"Risk: {obj.risk_assessment.title}"
        if obj.inspection_id:
            return f"Inspection: {obj.inspection.title}"
        return ""


class IncidentSerializer(TenantSerializer):
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)
    severity_label = serializers.CharField(source="get_severity_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    department_name = DisplayField("department")
    reported_by_name = serializers.SerializerMethodField()
    investigator_name = serializers.SerializerMethodField()
    persons = serializers.SerializerMethodField()

    class Meta(TenantSerializer.Meta):
        model = Incident
        exclude = ["organization", "persons_involved"]
        read_only_fields = [f.name for f in Incident._meta.fields]

    def get_reported_by_name(self, obj):
        return _name(obj.reported_by)

    def get_investigator_name(self, obj):
        return _name(obj.investigator)

    def get_persons(self, obj):
        return [{"id": e.id, "name": e.full_name} for e in obj.persons_involved.all()]


class IncidentDetailSerializer(IncidentSerializer):
    actions = ActionSerializer(many=True, read_only=True)


class ReportSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=Incident.KINDS)
    severity = serializers.ChoiceField(choices=Incident.SEVERITY, default="none")
    occurred_at = serializers.DateTimeField()
    location = serializers.CharField(max_length=200)
    department = serializers.PrimaryKeyRelatedField(queryset=Department.objects, required=False, allow_null=True)
    description = serializers.CharField()
    immediate_action = serializers.CharField(required=False, allow_blank=True)
    others_involved = serializers.CharField(required=False, allow_blank=True)
    persons = serializers.PrimaryKeyRelatedField(queryset=Employee.objects, many=True, required=False)


def _incident_scope(user, qs):
    if best_scope(user, "ohs.view") == "organization":
        return qs
    cond = Q(reported_by=user) | Q(investigator=user)
    emp = getattr(user, "employee", None)
    if has_perm(user, "ohs.view") and emp and emp.department_id:
        cond |= Q(department_id__in=department_descendants(emp.department_id))
    return qs.filter(cond)


class IncidentViewSet(TenantModelViewSet):
    queryset = Incident.objects.select_related("department", "reported_by", "investigator") \
        .prefetch_related("persons_involved", "actions__owner")
    perm_module = "ohs"
    perm_map = {k: None for k in ("list", "retrieve", "create", "investigate", "add_action", "close")}
    http_method_names = ["get", "post", "head", "options"]
    filterset_fields = ["status", "kind", "severity", "department"]
    search_fields = ["reference", "location", "description"]

    def get_serializer_class(self):
        return IncidentDetailSerializer if self.action == "retrieve" else IncidentSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get("mine") == "1":
            return qs.filter(reported_by=self.request.user)
        return _incident_scope(self.request.user, qs)

    def create(self, request, *args, **kwargs):
        s = ReportSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = dict(s.validated_data)
        persons = d.pop("persons", [])
        inc = services.report(request.user, d, persons)
        return Response({"id": inc.id, "reference": inc.reference,
                         "detail": "Thank you. The safety team has been notified."}, status=201)

    @action(detail=True, methods=["post"])
    def investigate(self, request, pk=None):
        inc = self.get_object()
        d = request.data
        inv = User.objects.filter(pk=d.get("investigator"), organization=request.user.organization).first() \
            if d.get("investigator") else None
        services.investigate(inc, request.user, inv, d.get("root_cause"), d.get("contributing_factors"),
                             int(d["lost_time_days"]) if d.get("lost_time_days") not in (None, "") else None,
                             d.get("reportable") if "reportable" in d else None,
                             d.get("reported_to_authority_on") or None)
        return Response(IncidentDetailSerializer(inc, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["post"], url_path="add-action")
    def add_action(self, request, pk=None):
        import datetime as dt

        inc = self.get_object()
        owner = User.objects.filter(pk=request.data.get("owner"), organization=request.user.organization).first()
        due = request.data.get("due_date")
        services.add_action(request.user, request.data.get("description", ""), owner,
                            dt.date.fromisoformat(due) if due else None, incident=inc)
        return Response(IncidentDetailSerializer(inc, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        inc = services.close_incident(self.get_object(), request.user)
        return Response(IncidentDetailSerializer(inc, context=self.get_serializer_context()).data)


class ActionViewSet(TenantModelViewSet):
    queryset = CorrectiveAction.objects.select_related("owner", "incident", "risk_assessment", "inspection")
    serializer_class = ActionSerializer
    perm_module = "ohs"
    perm_write = "ohs.manage"
    perm_map = {"list": None, "retrieve": None, "complete": None}
    http_method_names = ["get", "post", "patch", "head", "options"]
    filterset_fields = ["status", "incident", "risk_assessment", "inspection"]

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get("mine") == "1" or not has_perm(self.request.user, "ohs.view"):
            return qs.filter(owner=self.request.user)
        return qs

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        a = services.complete_action(self.get_object(), request.user, request.data.get("notes", ""))
        return Response(self.get_serializer(a).data)


class RiskSerializer(TenantSerializer):
    department = serializers.PrimaryKeyRelatedField(queryset=Department.objects, required=False, allow_null=True)
    department_name = DisplayField("department", fallback="Organization-wide")
    risk_score = serializers.IntegerField(read_only=True)
    residual_score = serializers.IntegerField(read_only=True)
    assessed_by_name = serializers.SerializerMethodField()
    open_actions = serializers.SerializerMethodField()

    class Meta(TenantSerializer.Meta):
        model = RiskAssessment
        read_only_fields = TenantSerializer.Meta.read_only_fields + ["assessed_by"]

    def validate(self, data):
        for f in ("likelihood", "severity", "residual_likelihood", "residual_severity"):
            if f in data and not 1 <= data[f] <= 5:
                raise serializers.ValidationError({f: "Use a 1-5 scale."})
        return data

    def get_assessed_by_name(self, obj):
        return _name(obj.assessed_by)

    def get_open_actions(self, obj):
        return obj.actions.filter(status="open").count()


class RiskViewSet(TenantModelViewSet):
    queryset = RiskAssessment.objects.select_related("department", "assessed_by")
    serializer_class = RiskSerializer
    perm_module = "ohs"
    perm_read = "ohs.view"
    perm_write = "ohs.manage"
    filterset_fields = ["status", "department"]
    search_fields = ["title", "hazard", "activity"]

    def perform_create(self, serializer):
        serializer.save(assessed_by=self.request.user)


class InspectionSerializer(TenantSerializer):
    department = serializers.PrimaryKeyRelatedField(queryset=Department.objects, required=False, allow_null=True)
    department_name = DisplayField("department")
    inspector_name = serializers.SerializerMethodField()
    score = serializers.IntegerField(read_only=True)

    class Meta(TenantSerializer.Meta):
        model = Inspection
        read_only_fields = TenantSerializer.Meta.read_only_fields + ["inspector"]

    def get_inspector_name(self, obj):
        return _name(obj.inspector)


class InspectionViewSet(TenantModelViewSet):
    queryset = Inspection.objects.select_related("department", "inspector")
    serializer_class = InspectionSerializer
    perm_module = "ohs"
    perm_read = "ohs.view"
    perm_write = "ohs.manage"
    filterset_fields = ["department"]

    def perform_create(self, serializer):
        serializer.save(inspector=self.request.user)


class OHRecordSerializer(TenantSerializer):
    employee = serializers.PrimaryKeyRelatedField(queryset=Employee.objects)
    incident = serializers.PrimaryKeyRelatedField(queryset=Incident.objects, required=False, allow_null=True)
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)
    fitness_label = serializers.CharField(source="get_fitness_display", read_only=True)
    clinician_name = serializers.SerializerMethodField()

    class Meta(TenantSerializer.Meta):
        model = OHRecord
        read_only_fields = TenantSerializer.Meta.read_only_fields + ["clinician"]

    def get_clinician_name(self, obj):
        return _name(obj.clinician)


class OHRecordViewSet(TenantModelViewSet):
    """Clinical occupational-health records: OH professionals only (ohs.medical), every read audited."""

    queryset = OHRecord.objects.select_related("employee", "clinician", "incident")
    serializer_class = OHRecordSerializer
    perm_module = "ohs"
    perm_read = "ohs.medical"
    perm_write = "ohs.medical"
    http_method_names = ["get", "post", "patch", "head", "options"]
    filterset_fields = ["employee", "kind", "fitness"]
    search_fields = ["employee__first_name", "employee__last_name"]

    def retrieve(self, request, *args, **kwargs):
        from apps.audit import services as audit

        rec = self.get_object()
        audit.log("view", rec, {"oh_record": rec.id})
        return Response(self.get_serializer(rec).data)

    def perform_create(self, serializer):
        d = dict(serializer.validated_data)
        emp = d.pop("employee")
        serializer.instance = services.add_oh_record(self.request.user, emp, d)


class FitnessView(APIView):
    """Non-clinical fitness outcomes: who is unfit or restricted (HR, safety, OH)."""

    def get(self, request, employee_id=None):
        allowed = any(has_perm(request.user, p) for p in ("ohs.view", "ohs.medical", "employees.change"))
        if employee_id is not None:
            emp = Employee.objects.filter(pk=employee_id).first()
            if emp is None:
                raise NotFound()
            own = getattr(request.user, "employee", None) == emp
            if not (allowed or own):
                raise PermissionDenied()
            return Response(services.fitness_status(emp))
        if not allowed:
            raise PermissionDenied()
        return Response(services.fitness_board())


class StatsView(APIView):
    def get(self, request):
        if not has_perm(request.user, "ohs.view"):
            raise PermissionDenied()
        y = request.query_params.get("year")
        return Response(services.stats(int(y) if y else None))
