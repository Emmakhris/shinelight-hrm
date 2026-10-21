import datetime as dt

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.http import FileResponse
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit import services as audit
from apps.core.exceptions import BusinessRuleError
from apps.core.views import TenantModelViewSet
from apps.documents.services import file_response as safe_file_response
from apps.employees.models import Employee
from apps.rbac.services import has_perm

from . import services
from .models import Appeal, Case, CaseAction, CaseMeeting, CaseNote

User = get_user_model()


def _name(u):
    return (u.get_full_name() or u.username) if u else None


class NoteSerializer(serializers.ModelSerializer):
    author_name = serializers.SerializerMethodField()
    has_file = serializers.SerializerMethodField()

    class Meta:
        model = CaseNote
        fields = ["id", "kind", "text", "file_name", "has_file", "author_name", "created_at"]

    def get_author_name(self, obj):
        return _name(obj.author)

    def get_has_file(self, obj):
        return bool(obj.file)


class MeetingSerializer(serializers.ModelSerializer):
    invitee_names = serializers.SerializerMethodField()

    class Meta:
        model = CaseMeeting
        fields = ["id", "kind", "scheduled_at", "venue", "attendees", "minutes", "held", "invitee_names"]

    def get_invitee_names(self, obj):
        return [e.full_name for e in obj.invitees.all()]


class AppealSerializer(serializers.ModelSerializer):
    decided_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Appeal
        fields = ["id", "grounds", "status", "decision", "decided_by_name", "decided_at", "created_at"]

    def get_decided_by_name(self, obj):
        return _name(obj.decided_by)


class ActionSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    action_label = serializers.CharField(source="get_action_type_display", read_only=True)
    case_reference = serializers.CharField(source="case.reference", read_only=True)
    appeals = AppealSerializer(many=True, read_only=True)
    can_appeal = serializers.SerializerMethodField()

    class Meta:
        model = CaseAction
        fields = ["id", "case", "case_reference", "employee", "employee_name", "action_type", "action_label",
                  "details", "effective_date", "expires_on", "suspension_days", "letter", "issued_at",
                  "acknowledged_at", "employee_response", "appeal_deadline", "appeals", "can_appeal"]

    def get_can_appeal(self, obj):
        user = self.context["request"].user
        return (obj.employee.user_id == user.pk and bool(obj.issued_at) and not obj.appeals.exists()
                and (obj.appeal_deadline is None or obj.appeal_deadline >= dt.date.today()))


class CaseSerializer(serializers.ModelSerializer):
    case_type_label = serializers.CharField(source="get_case_type_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    outcome_label = serializers.CharField(source="get_outcome_display", read_only=True)
    complainant_name = serializers.SerializerMethodField()
    reporter_name = serializers.SerializerMethodField()
    respondent_names = serializers.SerializerMethodField()
    case_officer_name = serializers.SerializerMethodField()
    overdue = serializers.SerializerMethodField()

    class Meta:
        model = Case
        fields = ["id", "reference", "case_type", "case_type_label", "title", "severity", "status", "status_label",
                  "incident_date", "complainant", "complainant_name", "reporter_name", "is_anonymous",
                  "respondents", "respondent_names", "case_officer", "case_officer_name", "due_date", "overdue",
                  "outcome", "outcome_label", "created_at", "closed_at"]

    def _senior(self):
        return has_perm(self.context["request"].user, "relations.view_all")

    def get_complainant_name(self, obj):
        if obj.is_anonymous and not self._senior():
            return "Anonymous"
        return obj.complainant.full_name if obj.complainant_id else None

    def get_reporter_name(self, obj):
        if obj.is_anonymous and not self._senior():
            return "Anonymous"
        return _name(obj.reported_by)

    def get_respondent_names(self, obj):
        return [e.full_name for e in obj.respondents.all()]

    def get_case_officer_name(self, obj):
        return _name(obj.case_officer)

    def get_overdue(self, obj):
        return obj.status in services.OPEN and obj.due_date is not None and obj.due_date < dt.date.today()


class CaseDetailSerializer(CaseSerializer):
    notes = NoteSerializer(many=True, read_only=True)
    meetings = MeetingSerializer(many=True, read_only=True)
    actions = ActionSerializer(many=True, read_only=True)
    investigators = serializers.SerializerMethodField()
    is_senior = serializers.SerializerMethodField()
    is_officer = serializers.SerializerMethodField()

    class Meta(CaseSerializer.Meta):
        fields = CaseSerializer.Meta.fields + ["description", "policy_reference", "investigation_plan",
                                               "outcome_summary", "notes", "meetings", "actions", "investigators",
                                               "is_senior", "is_officer", "decided_at"]

    def get_investigators(self, obj):
        return [{"id": u.id, "name": _name(u)} for u in obj.investigators.all()]

    def get_is_senior(self, obj):
        return self._senior()

    def get_is_officer(self, obj):
        return obj.case_officer_id == self.context["request"].user.pk


class OpenCaseSerializer(serializers.Serializer):
    case_type = serializers.ChoiceField(choices=Case.TYPES)
    title = serializers.CharField(required=False, allow_blank=True)
    description = serializers.CharField()
    severity = serializers.ChoiceField(choices=Case.SEVERITY, default="medium")
    incident_date = serializers.DateField(required=False, allow_null=True)
    is_anonymous = serializers.BooleanField(default=False)
    policy_reference = serializers.CharField(required=False, allow_blank=True)
    complainant = serializers.PrimaryKeyRelatedField(queryset=Employee.objects, required=False, allow_null=True)
    respondents = serializers.PrimaryKeyRelatedField(queryset=Employee.objects, many=True, required=False)
    own = serializers.BooleanField(default=False, help_text="Raising my own concern (self-service).")


class CaseViewSet(TenantModelViewSet):
    """Cases visible to the user as handler (officer/investigator) or senior reviewer only."""

    queryset = Case.objects.select_related("complainant", "reported_by", "case_officer") \
        .prefetch_related("respondents")
    perm_module = "relations"
    perm_map = {k: None for k in ("list", "retrieve", "create", "assign", "note", "meeting", "minutes", "decide",
                                  "close", "withdraw", "evidence")}
    http_method_names = ["get", "post", "head", "options"]
    filterset_fields = ["status", "case_type", "severity"]
    search_fields = ["reference", "title"]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_serializer_class(self):
        return CaseDetailSerializer if self.action != "list" else CaseSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if has_perm(user, "relations.view_all"):
            visible = qs
        else:
            visible = qs.filter(Q(case_officer=user) | Q(investigators=user)).distinct()
        # a party never sees the case file, even if they hold HR permissions
        return visible.exclude(Q(complainant__user=user) | Q(respondents__user=user))

    def create(self, request, *args, **kwargs):
        s = OpenCaseSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = dict(s.validated_data)
        respondents = d.pop("respondents", [])
        if "complainant" not in request.data or not has_perm(request.user, "relations.manage"):
            d.pop("complainant", None)
        case = services.open_case(request.user, d, respondents)
        return Response({"id": case.id, "reference": case.reference,
                         "detail": "Your report has been received in confidence. HR will be in touch."}, status=201)

    def _case(self):
        try:
            return self.get_object()
        except Exception as exc:  # not visible -> do not reveal that it exists
            raise NotFound() from exc

    def retrieve(self, request, *args, **kwargs):
        case = self._case()
        audit.log("view", case, {"action": "case_viewed"})
        return Response(self.get_serializer(case).data)

    @action(detail=True, methods=["post"])
    def assign(self, request, pk=None):
        case = self._case()
        officer = User.objects.filter(pk=request.data.get("case_officer"), organization=request.user.organization).first() \
            if request.data.get("case_officer") else None
        inv = None
        if "investigators" in request.data:
            inv = list(User.objects.filter(pk__in=request.data.get("investigators") or [],
                                           organization=request.user.organization))
        services.assign(case, request.user, officer, inv, request.data.get("investigation_plan"))
        return Response(self.get_serializer(case).data)

    @action(detail=True, methods=["post"])
    def note(self, request, pk=None):
        case = self._case()
        services.add_note(case, request.user, request.data.get("kind", "note"), request.data.get("text", ""),
                          request.FILES.get("file"))
        return Response(self.get_serializer(case).data)

    @action(detail=True, url_path=r"evidence/(?P<note_id>\d+)")
    def evidence(self, request, pk=None, note_id=None):
        case = self._case()
        note = case.notes.filter(pk=note_id).first()
        if note is None or not note.file:
            raise NotFound()
        audit.log("download", case, {"evidence": note.id})
        return safe_file_response(note.file, note.file_name, inline=True)

    @action(detail=True, methods=["post"])
    def meeting(self, request, pk=None):
        case = self._case()
        from django.utils.dateparse import parse_datetime

        when = parse_datetime(str(request.data.get("scheduled_at") or ""))
        if when is None:
            raise BusinessRuleError("Give the meeting date and time.")
        invitees = list(Employee.objects.filter(pk__in=request.data.get("invitees") or []))
        services.schedule_meeting(case, request.user, {"kind": request.data.get("kind", "interview"),
                                                       "scheduled_at": when, "venue": request.data.get("venue", ""),
                                                       "attendees": request.data.get("attendees", "")}, invitees)
        return Response(self.get_serializer(case).data)

    @action(detail=True, methods=["post"], url_path=r"minutes/(?P<meeting_id>\d+)")
    def minutes(self, request, pk=None, meeting_id=None):
        case = self._case()
        m = case.meetings.filter(pk=meeting_id).first()
        if m is None:
            raise NotFound()
        services.record_minutes(m, request.user, request.data.get("minutes", ""))
        return Response(self.get_serializer(case).data)

    @action(detail=True, methods=["post"])
    def decide(self, request, pk=None):
        case = self._case()
        acts = []
        for a in request.data.get("actions") or []:
            emp = case.respondents.filter(pk=a.get("employee")).first()
            if emp is None:
                raise BusinessRuleError("Sanctions can only be issued to a respondent in the case.")
            acts.append({"employee": emp, "action_type": a.get("action_type"), "details": a.get("details", ""),
                         "effective_date": dt.date.fromisoformat(a["effective_date"]) if a.get("effective_date")
                         else None, "suspension_days": int(a.get("suspension_days") or 0)})
        services.decide(case, request.user, request.data.get("outcome", ""), request.data.get("summary", ""), acts)
        case.refresh_from_db()
        return Response(self.get_serializer(case).data)

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        case = self._case()
        services.close(case, request.user, request.data.get("note", ""))
        return Response(self.get_serializer(case).data)

    @action(detail=True, methods=["post"])
    def withdraw(self, request, pk=None):
        case = self._case()
        services.withdraw(case, request.user, request.data.get("reason", ""))
        return Response(self.get_serializer(case).data)


class MyCasesView(APIView):
    """What a party may see: matters they raised (status only) and outcomes addressed to them."""

    def get(self, request):
        user = request.user
        raised = Case.objects.filter(reported_by=user).order_by("-created_at")
        actions = CaseAction.objects.filter(employee__user=user, issued_at__isnull=False) \
            .select_related("case").prefetch_related("appeals")
        return Response({
            "raised": [{"id": c.id, "reference": c.reference, "type": c.get_case_type_display(), "title": c.title,
                        "status": c.status, "status_label": c.get_status_display(), "created_at": c.created_at,
                        "can_withdraw": c.status in ("reported", "investigating", "hearing")} for c in raised],
            "actions": ActionSerializer(actions, many=True, context={"request": request}).data,
            "types": [{"value": k, "label": v} for k, v in Case.TYPES if k in services.EMPLOYEE_TYPES],
        })

    def post(self, request):
        """Respond to or appeal an outcome addressed to me."""
        a = CaseAction.objects.filter(pk=request.data.get("action"), employee__user=request.user).first()
        if a is None:
            raise NotFound()
        if request.data.get("appeal"):
            services.lodge_appeal(a, request.user, request.data.get("grounds", ""))
        else:
            services.respond(a, request.user, request.data.get("response", ""))
        return Response({"detail": "Saved."})


class MyLetterView(APIView):
    """The addressee can always read their own outcome letter (stored as a restricted personnel document)."""

    def get(self, request, pk):
        a = CaseAction.objects.filter(pk=pk, employee__user=request.user, letter__isnull=False).first()
        version = a.letter.latest if a else None
        if version is None:
            raise NotFound()
        audit.log("download", a.letter, {"own_er_letter": a.id})
        return FileResponse(version.file.open("rb"), filename=version.file_name, as_attachment=False,
                            content_type=version.content_type or "application/pdf")


class WithdrawMineView(APIView):
    def post(self, request, pk):
        case = Case.objects.filter(pk=pk, reported_by=request.user).first()
        if case is None:
            raise NotFound()
        services.withdraw(case, request.user, request.data.get("reason", ""))
        return Response({"status": case.status})


class AppealDecisionView(APIView):
    def post(self, request, pk):
        ap = Appeal.objects.filter(pk=pk).select_related("action__case").first()
        if ap is None or not has_perm(request.user, "relations.view_all"):
            raise PermissionDenied()
        services.decide_appeal(ap, request.user, request.data.get("status", ""), request.data.get("decision", ""))
        return Response(AppealSerializer(ap).data)


class WarningsView(APIView):
    """Active warnings for an employee (handlers and senior reviewers only)."""

    def get(self, request, employee_id):
        if not (has_perm(request.user, "relations.manage") or has_perm(request.user, "relations.view_all")):
            raise PermissionDenied()
        emp = Employee.objects.filter(pk=employee_id).first()
        if emp is None:
            raise NotFound()
        return Response(ActionSerializer(services.active_warnings(emp), many=True, context={"request": request}).data)


class ReportView(APIView):
    def get(self, request):
        if not has_perm(request.user, "relations.view_all"):
            raise PermissionDenied()
        y = request.query_params.get("year")
        return Response(services.report(int(y) if y else None))
