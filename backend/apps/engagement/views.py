import datetime as dt

from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import BusinessRuleError
from apps.core.serializers import DisplayField, TenantSerializer
from apps.core.views import TenantModelViewSet
from apps.employees.models import Employee
from apps.organization.models import Department
from apps.rbac.services import best_scope, department_descendants, has_perm

from . import services
from .models import ActionPlan, Event, Recognition, Suggestion, Survey, SurveyInvite


class SurveySerializer(TenantSerializer):
    departments = serializers.PrimaryKeyRelatedField(queryset=Department.objects, many=True, required=False)
    participation = serializers.SerializerMethodField()

    class Meta(TenantSerializer.Meta):
        model = Survey
        read_only_fields = TenantSerializer.Meta.read_only_fields + ["status"]

    def get_participation(self, obj):
        inv = obj.invites.aggregate(n=Count("id"), r=Count("id", filter=Q(responded=True)))
        return {"invited": inv["n"], "responded": inv["r"]}


def _result_departments(user):
    """None = whole organization; otherwise the department ids the user may see results for."""
    if has_perm(user, "engagement.manage") or best_scope(user, "engagement.view") == "organization":
        return None
    emp = getattr(user, "employee", None)
    if not has_perm(user, "engagement.view") or emp is None or not emp.department_id:
        raise PermissionDenied()
    return department_descendants(emp.department_id)


class SurveyViewSet(TenantModelViewSet):
    queryset = Survey.objects.prefetch_related("departments")
    serializer_class = SurveySerializer
    perm_module = "engagement"
    perm_read = "engagement.view"
    perm_write = "engagement.manage"
    perm_map = {"respond": None, "results": None, "mine": None, "trends": "engagement.view"}
    filterset_fields = ["status", "kind"]

    def perform_update(self, serializer):
        if serializer.instance.status != "draft" and "questions" in serializer.validated_data:
            raise BusinessRuleError("Questions cannot change once the survey is open.")
        serializer.save()

    def perform_destroy(self, instance):
        if instance.status != "draft":
            raise BusinessRuleError("Only drafts can be deleted.")
        instance.delete()

    @action(detail=True, methods=["post"])
    def launch(self, request, pk=None):
        return Response({"invited": services.launch(self.get_object(), request.user)})

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        return Response(self.get_serializer(services.close(self.get_object())).data)

    @action(detail=False)
    def mine(self, request):
        emp = getattr(request.user, "employee", None)
        invites = SurveyInvite.objects.filter(employee=emp, survey__status="open").select_related("survey") if emp else []
        return Response([{"id": i.survey.id, "title": i.survey.title, "kind": i.survey.get_kind_display(),
                          "intro": i.survey.intro, "anonymous": i.survey.anonymous, "closes_on": i.survey.closes_on,
                          "responded": i.responded, "questions": i.survey.questions} for i in invites])

    @action(detail=True, methods=["post"])
    def respond(self, request, pk=None):
        survey = Survey.objects.get(pk=pk)
        services.respond(survey, request.user, request.data.get("answers") or {})
        return Response({"detail": "Thank you for your feedback."})

    @action(detail=True)
    def results(self, request, pk=None):
        survey = Survey.objects.get(pk=pk)
        return Response(services.results(survey, _result_departments(request.user)))

    @action(detail=False)
    def trends(self, request):
        if not has_perm(request.user, "engagement.manage"):
            raise PermissionDenied()
        return Response(services.trends())


class ActionPlanSerializer(TenantSerializer):
    survey = serializers.PrimaryKeyRelatedField(queryset=Survey.objects, required=False, allow_null=True)
    department = serializers.PrimaryKeyRelatedField(queryset=Department.objects, required=False, allow_null=True)
    owner = serializers.PrimaryKeyRelatedField(queryset=Employee.objects, required=False, allow_null=True)
    survey_title = DisplayField("survey")
    department_name = DisplayField("department", fallback="Organization-wide")
    owner_name = DisplayField("owner")

    class Meta(TenantSerializer.Meta):
        model = ActionPlan


class ActionPlanViewSet(TenantModelViewSet):
    queryset = ActionPlan.objects.select_related("survey", "department", "owner")
    serializer_class = ActionPlanSerializer
    perm_module = "engagement"
    perm_read = "engagement.view"
    perm_write = "engagement.manage"
    filterset_fields = ["survey", "status", "department"]
    pagination_class = None


class RecognitionSerializer(serializers.ModelSerializer):
    giver_name = serializers.CharField(source="giver.full_name", read_only=True)
    recipient_name = serializers.CharField(source="recipient.full_name", read_only=True)
    recipient_department = serializers.CharField(source="recipient.department.name", read_only=True, default=None)
    value_label = serializers.CharField(source="get_value_display", read_only=True)
    like_count = serializers.SerializerMethodField()
    liked = serializers.SerializerMethodField()
    recipient = serializers.PrimaryKeyRelatedField(queryset=Employee.objects)

    class Meta:
        model = Recognition
        fields = ["id", "giver_name", "recipient", "recipient_name", "recipient_department", "value", "value_label",
                  "message", "is_public", "like_count", "liked", "created_at"]

    def get_like_count(self, obj):
        return obj.likes.count()

    def get_liked(self, obj):
        return obj.likes.filter(pk=self.context["request"].user.pk).exists()


class RecognitionViewSet(TenantModelViewSet):
    queryset = Recognition.objects.select_related("giver", "recipient__department").prefetch_related("likes")
    serializer_class = RecognitionSerializer
    perm_module = "engagement"
    perm_map = {"list": None, "retrieve": None, "create": None, "like": None}
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        qs = super().get_queryset()
        emp = getattr(self.request.user, "employee", None)
        if self.request.query_params.get("mine") == "1":
            return qs.filter(recipient=emp)
        return qs.filter(Q(is_public=True) | Q(recipient=emp) | Q(giver=emp))

    def perform_create(self, serializer):
        d = serializer.validated_data
        serializer.instance = services.recognise(self.request.user, d["recipient"], d.get("value"),
                                                 d.get("message", ""), d.get("is_public", True))

    @action(detail=True, methods=["post"])
    def like(self, request, pk=None):
        r = self.get_object()
        if r.likes.filter(pk=request.user.pk).exists():
            r.likes.remove(request.user)
        else:
            r.likes.add(request.user)
        return Response(self.get_serializer(r).data)


class SuggestionSerializer(serializers.ModelSerializer):
    author_name = serializers.SerializerMethodField()
    category_label = serializers.CharField(source="get_category_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    vote_count = serializers.SerializerMethodField()
    voted = serializers.SerializerMethodField()
    anonymous = serializers.BooleanField(write_only=True, default=False)

    class Meta:
        model = Suggestion
        fields = ["id", "author_name", "category", "category_label", "title", "text", "status", "status_label",
                  "response", "vote_count", "voted", "anonymous", "created_at"]
        read_only_fields = ["status", "response"]

    def get_author_name(self, obj):
        return obj.author.full_name if obj.author_id else "Anonymous"

    def get_vote_count(self, obj):
        return obj.votes.count()

    def get_voted(self, obj):
        return obj.votes.filter(pk=self.context["request"].user.pk).exists()


class SuggestionViewSet(TenantModelViewSet):
    queryset = Suggestion.objects.select_related("author").prefetch_related("votes")
    serializer_class = SuggestionSerializer
    perm_module = "engagement"
    perm_map = {"list": None, "retrieve": None, "create": None, "vote": None, "review": "engagement.manage"}
    http_method_names = ["get", "post", "head", "options"]
    filterset_fields = ["status", "category"]

    def perform_create(self, serializer):
        d = dict(serializer.validated_data)
        serializer.instance = services.suggest(self.request.user, d, anonymous=d.pop("anonymous", False))

    @action(detail=True, methods=["post"])
    def vote(self, request, pk=None):
        s = self.get_object()
        if s.votes.filter(pk=request.user.pk).exists():
            s.votes.remove(request.user)
        else:
            s.votes.add(request.user)
        return Response(self.get_serializer(s).data)

    @action(detail=True, methods=["post"])
    def review(self, request, pk=None):
        s = self.get_object()
        status = request.data.get("status")
        if status not in dict(Suggestion.STATUS):
            raise BusinessRuleError("Unknown status.")
        s.status, s.response = status, request.data.get("response", s.response)
        s.save(update_fields=["status", "response", "updated_at"])
        if s.author_id and s.author.user_id:
            services._notify([s.author.user], f"Your suggestion: {s.get_status_display()}",
                             s.response or s.title, "/engagement")
        return Response(self.get_serializer(s).data)


class EventSerializer(TenantSerializer):
    attending = serializers.SerializerMethodField()
    attendee_count = serializers.SerializerMethodField()

    class Meta(TenantSerializer.Meta):
        model = Event
        exclude = ["organization", "attendees"]

    def get_attending(self, obj):
        emp = getattr(self.context["request"].user, "employee", None)
        return bool(emp and obj.attendees.filter(pk=emp.pk).exists())

    def get_attendee_count(self, obj):
        return obj.attendees.count()


class EventViewSet(TenantModelViewSet):
    queryset = Event.objects.all()
    serializer_class = EventSerializer
    perm_module = "engagement"
    perm_map = {"list": None, "retrieve": None, "register": None}
    perm_write = "engagement.manage"
    pagination_class = None

    @action(detail=True, methods=["post"])
    def register(self, request, pk=None):
        ev = self.get_object()
        going = services.register(ev, request.user)
        return Response({"attending": going, **self.get_serializer(ev).data})


class OverviewView(APIView):
    """Engagement dashboard for HR: latest results, trend, suggestions and recognition activity."""

    def get(self, request):
        if not has_perm(request.user, "engagement.manage"):
            raise PermissionDenied()
        latest = Survey.objects.exclude(status="draft").order_by("-opens_on", "-id").first()
        return Response({
            "latest": services.results(latest) if latest else None,
            "trends": services.trends(),
            "suggestions": dict(Suggestion.objects.values_list("status").annotate(n=Count("id"))),
            "recognitions_30_days": Recognition.objects.filter(
                created_at__gte=timezone.now() - dt.timedelta(days=30)).count(),
        })
