import datetime as dt

from django.db.models import Count, Q
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from rest_framework import permissions, serializers
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.audit import services as audit
from apps.core.context import org_context
from apps.core.exceptions import BusinessRuleError
from apps.core.middleware import client_ip
from apps.core.serializers import DisplayField, TenantSerializer
from apps.core.views import TenantModelViewSet
from apps.documents.services import file_response as safe_file_response
from apps.employees.models import Employee
from apps.organization.models import Department, Grade, GradeStep, JobTitle, Location, Position
from apps.rbac.services import has_perm

from . import services
from .models import (
    QUALIFICATIONS,
    Application,
    ApplicationEvent,
    Candidate,
    Interview,
    Offer,
    ReferenceCheck,
    Requisition,
    Scorecard,
    Vacancy,
)


def _bool(v):
    return str(v).lower() in ("1", "true", "yes", "on")


# ---------------------------------------------------------------- requisitions
class RequisitionSerializer(TenantSerializer):
    job_title_name = DisplayField("job_title")
    department_name = DisplayField("department")
    grade_name = DisplayField("grade")
    requested_by_name = DisplayField("requested_by")
    replacing_name = DisplayField("replacing")
    position_code = serializers.CharField(source="position.code", read_only=True, default=None)
    annual_budget = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)
    job_title = serializers.PrimaryKeyRelatedField(queryset=JobTitle.objects)
    department = serializers.PrimaryKeyRelatedField(queryset=Department.objects)
    position = serializers.PrimaryKeyRelatedField(queryset=Position.objects, required=False, allow_null=True)
    grade = serializers.PrimaryKeyRelatedField(queryset=Grade.objects, required=False, allow_null=True)
    location = serializers.PrimaryKeyRelatedField(queryset=Location.objects, required=False, allow_null=True)
    replacing = serializers.PrimaryKeyRelatedField(queryset=Employee.objects, required=False, allow_null=True)
    vacancy = serializers.SerializerMethodField()
    submit = serializers.BooleanField(write_only=True, default=False)

    class Meta(TenantSerializer.Meta):
        model = Requisition
        read_only_fields = TenantSerializer.Meta.read_only_fields + [
            "reference", "status", "submitted_at", "approved_at", "filled_count", "requested_by"]

    def get_vacancy(self, obj):
        v = obj.vacancies.exclude(status="cancelled").first()
        return {"id": v.id, "reference": v.reference, "status": v.status} if v else None


class RequisitionViewSet(TenantModelViewSet):
    queryset = Requisition.objects.select_related("job_title", "department", "grade", "requested_by", "replacing",
                                                  "position").prefetch_related("vacancies")
    serializer_class = RequisitionSerializer
    perm_module = "recruitment"
    perm_map = {"list": "recruitment.requisition", "retrieve": "recruitment.requisition",
                "create": "recruitment.requisition", "update": "recruitment.requisition",
                "partial_update": "recruitment.requisition", "destroy": "recruitment.requisition",
                "submit": "recruitment.requisition", "create_vacancy": "recruitment.manage",
                "close": "recruitment.manage"}
    filterset_fields = ["status", "department", "reason"]
    search_fields = ["reference", "job_title__name", "justification"]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if has_perm(user, "recruitment.view"):
            return qs
        emp = getattr(user, "employee", None)
        return qs.filter(Q(created_by=user) | Q(requested_by=emp) if emp else Q(created_by=user))

    def _editable(self, req):
        if req.status not in ("draft", "returned"):
            raise BusinessRuleError("Only draft or returned requisitions can be changed.")
        if not (req.created_by_id == self.request.user.pk or has_perm(self.request.user, "recruitment.manage")):
            raise PermissionDenied("You can only edit your own requisitions.")

    def perform_create(self, serializer):
        submit = serializer.validated_data.pop("submit", False)
        req = serializer.save(requested_by=getattr(self.request.user, "employee", None),
                              created_by=self.request.user)
        if req.position_id and not req.grade_id:
            req.grade = req.position.grade
            req.save(update_fields=["grade"])
        if submit:
            services.submit_requisition(req, self.request.user)

    def perform_update(self, serializer):
        self._editable(serializer.instance)
        serializer.validated_data.pop("submit", None)
        serializer.save()

    def perform_destroy(self, instance):
        if instance.status != "draft":
            raise BusinessRuleError("Only drafts can be deleted; cancel the request instead.")
        self._editable(instance)
        instance.delete()

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        req = self.get_object()
        self._editable(req)
        services.submit_requisition(req, request.user)
        return Response(self.get_serializer(req).data)

    @action(detail=True, methods=["post"], url_path="create-vacancy")
    def create_vacancy(self, request, pk=None):
        v = services.vacancy_from_requisition(self.get_object(), request.user)
        return Response(VacancySerializer(v, context=self.get_serializer_context()).data, status=201)

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        req = self.get_object()
        if req.status not in ("approved", "filled"):
            raise BusinessRuleError("Only approved requisitions can be closed.")
        req.status = "closed"
        req.save(update_fields=["status", "updated_at"])
        return Response(self.get_serializer(req).data)


# ---------------------------------------------------------------- vacancies
class VacancySerializer(TenantSerializer):
    department_name = DisplayField("department")
    location_name = DisplayField("location")
    requisition_reference = serializers.CharField(source="requisition.reference", read_only=True, default=None)
    recruiter_name = serializers.SerializerMethodField()
    department = serializers.PrimaryKeyRelatedField(queryset=Department.objects)
    location = serializers.PrimaryKeyRelatedField(queryset=Location.objects, required=False, allow_null=True)
    requisition = serializers.PrimaryKeyRelatedField(queryset=Requisition.objects, required=False, allow_null=True)
    criteria = serializers.ListField(read_only=True)
    pipeline = serializers.SerializerMethodField()
    days_open = serializers.SerializerMethodField()

    class Meta(TenantSerializer.Meta):
        model = Vacancy
        read_only_fields = TenantSerializer.Meta.read_only_fields + ["reference", "status", "published_at",
                                                                     "closed_at"]

    def get_recruiter_name(self, obj):
        return obj.recruiter.get_full_name() or obj.recruiter.username if obj.recruiter_id else None

    def get_pipeline(self, obj):
        counts = getattr(obj, "_stage_counts", None)
        if counts is None:
            counts = dict(obj.applications.values_list("stage").annotate(n=Count("id")))
        return counts

    def get_days_open(self, obj):
        if not obj.published_at:
            return None
        end = obj.closed_at or dt.datetime.now(dt.UTC)
        return (end - obj.published_at).days


class VacancyViewSet(TenantModelViewSet):
    queryset = Vacancy.objects.select_related("department", "location", "requisition", "recruiter")
    serializer_class = VacancySerializer
    perm_module = "recruitment"
    perm_read = "recruitment.view"
    perm_write = "recruitment.manage"
    filterset_fields = ["status", "department", "visibility", "requisition"]
    search_fields = ["reference", "title"]

    def perform_create(self, serializer):
        serializer.save(recruiter=self.request.user)

    def perform_update(self, serializer):
        if serializer.instance.status in ("filled", "cancelled"):
            raise BusinessRuleError("Finished vacancies cannot be edited.")
        serializer.save()

    def perform_destroy(self, instance):
        if instance.applications.exists():
            raise BusinessRuleError("This vacancy has applications; cancel it instead.")
        instance.delete()

    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        return Response(self.get_serializer(services.publish_vacancy(self.get_object(), request.user)).data)

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        status = request.data.get("status", "closed")
        if status not in ("closed", "cancelled", "filled"):
            raise BusinessRuleError("Unknown status.")
        return Response(self.get_serializer(services.close_vacancy(self.get_object(), status)).data)


# ---------------------------------------------------------------- candidates
class CandidateSerializer(TenantSerializer):
    applications = serializers.SerializerMethodField()
    full_name = serializers.CharField(read_only=True)

    class Meta(TenantSerializer.Meta):
        model = Candidate
        read_only_fields = TenantSerializer.Meta.read_only_fields + ["consent_given_at", "anonymised", "employee",
                                                                     "email"]

    def get_applications(self, obj):
        return [{"id": a.id, "reference": a.reference, "vacancy": a.vacancy.title, "stage": a.stage,
                 "applied_at": a.applied_at} for a in obj.applications.all()]


class CandidateViewSet(TenantModelViewSet):
    queryset = Candidate.objects.prefetch_related("applications__vacancy")
    serializer_class = CandidateSerializer
    perm_module = "recruitment"
    perm_read = "recruitment.view"
    perm_write = "recruitment.manage"
    http_method_names = ["get", "patch", "post", "head", "options"]
    filterset_fields = ["talent_pool", "source", "highest_qualification", "anonymised"]
    search_fields = ["first_name", "last_name", "email", "current_title", "field_of_study", "location"]

    def create(self, request, *args, **kwargs):
        raise BusinessRuleError("Add candidates by recording an application against a vacancy.")

    @action(detail=True, methods=["post"])
    def anonymise(self, request, pk=None):
        cand = self.get_object()
        if cand.applications.filter(stage__in=Application.ACTIVE_STAGES + ["hired"]).exists():
            raise BusinessRuleError("The candidate has an active or successful application.")
        services.anonymise(cand)
        return Response(self.get_serializer(cand).data)


# ---------------------------------------------------------------- applications
class EventSerializer(serializers.ModelSerializer):
    actor_name = serializers.SerializerMethodField()

    class Meta:
        model = ApplicationEvent
        fields = ["id", "kind", "from_stage", "to_stage", "note", "actor_name", "created_at"]

    def get_actor_name(self, obj):
        return (obj.actor.get_full_name() or obj.actor.username) if obj.actor_id else None


class ApplicationListSerializer(TenantSerializer):
    candidate_name = serializers.CharField(source="candidate.full_name", read_only=True)
    candidate_email = serializers.CharField(source="candidate.email", read_only=True)
    candidate_phone = serializers.CharField(source="candidate.phone", read_only=True)
    qualification = serializers.CharField(source="candidate.get_highest_qualification_display", read_only=True)
    years_experience = serializers.DecimalField(source="candidate.years_experience", max_digits=4, decimal_places=1,
                                                read_only=True)
    source = serializers.CharField(source="candidate.get_source_display", read_only=True)
    internal = serializers.SerializerMethodField()
    vacancy_title = serializers.CharField(source="vacancy.title", read_only=True)
    vacancy_reference = serializers.CharField(source="vacancy.reference", read_only=True)
    has_cv = serializers.SerializerMethodField()

    class Meta(TenantSerializer.Meta):
        model = Application
        exclude = ["organization", "cv"]
        read_only_fields = [f.name for f in Application._meta.fields if f.name not in ("rating", "screening_notes")]

    def get_internal(self, obj):
        return obj.candidate.employee_id is not None

    def get_has_cv(self, obj):
        return bool(obj.cv)


class ApplicationDetailSerializer(ApplicationListSerializer):
    candidate = CandidateSerializer(read_only=True)
    events = EventSerializer(many=True, read_only=True)
    interviews = serializers.SerializerMethodField()
    checks = serializers.SerializerMethodField()
    offers = serializers.SerializerMethodField()
    summary = serializers.SerializerMethodField()
    criteria = serializers.ListField(source="vacancy.criteria", read_only=True)
    questions = serializers.ListField(source="vacancy.screening_questions", read_only=True)

    def get_interviews(self, obj):
        return InterviewSerializer(obj.interviews.all(), many=True, context=self.context).data

    def get_checks(self, obj):
        return CheckSerializer(obj.checks.all(), many=True, context=self.context).data

    def get_offers(self, obj):
        user = self.context["request"].user
        if not has_perm(user, "recruitment.offer") and not has_perm(user, "recruitment.manage"):
            return []
        return OfferSerializer(obj.offers.all(), many=True, context=self.context).data

    def get_summary(self, obj):
        return services.interview_summary(obj)


class ApplicationCreateSerializer(serializers.Serializer):
    """Recruiter records an application (agency, walk-in, referral)."""

    vacancy = serializers.PrimaryKeyRelatedField(queryset=Vacancy.objects)
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    email = serializers.EmailField()
    phone = serializers.CharField(required=False, allow_blank=True)
    gender = serializers.CharField(required=False, allow_blank=True)
    location = serializers.CharField(required=False, allow_blank=True)
    highest_qualification = serializers.ChoiceField(choices=QUALIFICATIONS, required=False)
    field_of_study = serializers.CharField(required=False, allow_blank=True)
    years_experience = serializers.DecimalField(max_digits=4, decimal_places=1, required=False)
    current_employer = serializers.CharField(required=False, allow_blank=True)
    current_title = serializers.CharField(required=False, allow_blank=True)
    source = serializers.ChoiceField(choices=Candidate.SOURCES, default="agency")
    referred_by = serializers.PrimaryKeyRelatedField(queryset=Employee.objects, required=False, allow_null=True)
    cover_letter = serializers.CharField(required=False, allow_blank=True)
    cv = serializers.FileField(required=False, allow_null=True)
    consent = serializers.BooleanField(default=False)
    talent_pool = serializers.BooleanField(default=False)


class ApplicationViewSet(TenantModelViewSet):
    queryset = Application.objects.select_related("candidate", "vacancy")
    perm_module = "recruitment"
    perm_read = "recruitment.view"
    perm_write = "recruitment.manage"
    http_method_names = ["get", "patch", "post", "head", "options"]
    filterset_fields = ["vacancy", "stage", "knocked_out", "candidate"]
    search_fields = ["reference", "candidate__first_name", "candidate__last_name", "candidate__email"]
    ordering_fields = ["applied_at", "screening_score", "rating"]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_serializer_class(self):
        if self.action == "retrieve":
            return ApplicationDetailSerializer
        return ApplicationListSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        if self.action == "retrieve":
            qs = qs.prefetch_related("events__actor", "interviews__panel", "interviews__scorecards", "checks",
                                     "offers")
        if self.request.query_params.get("active") == "1":
            qs = qs.filter(stage__in=Application.ACTIVE_STAGES)
        return qs

    def create(self, request, *args, **kwargs):
        s = ApplicationCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = dict(s.validated_data)
        vac = d.pop("vacancy")
        app = services.apply(vac, d, cv=d.pop("cv", None), cover_letter=d.pop("cover_letter", ""),
                             source=d.pop("source"), referred_by=d.pop("referred_by", None),
                             consent=d.pop("consent"), talent_pool=d.pop("talent_pool"), actor=request.user)
        return Response(ApplicationListSerializer(app, context=self.get_serializer_context()).data, status=201)

    @action(detail=True, methods=["post"])
    def move(self, request, pk=None):
        app = self.get_object()
        services.move_stage(app, request.data.get("stage", ""), request.user, note=request.data.get("note", ""),
                            notify_candidate=_bool(request.data.get("notify", True)),
                            reason=request.data.get("reason", ""))
        return Response(ApplicationListSerializer(app, context=self.get_serializer_context()).data)

    @action(detail=False, methods=["post"], url_path="bulk-move")
    def bulk_move(self, request):
        ids = request.data.get("ids") or []
        n = 0
        for app in self.get_queryset().filter(pk__in=ids):
            services.move_stage(app, request.data.get("stage", ""), request.user, note=request.data.get("note", ""),
                                notify_candidate=_bool(request.data.get("notify", True)),
                                reason=request.data.get("reason", ""))
            n += 1
        return Response({"moved": n})

    @action(detail=True, methods=["post"])
    def note(self, request, pk=None):
        app = self.get_object()
        if not request.data.get("note"):
            raise BusinessRuleError("Enter a note.")
        ApplicationEvent.objects.create(application=app, kind="note", note=request.data["note"], actor=request.user)
        return Response({"detail": "Saved."})

    @action(detail=True, methods=["post"])
    def rescreen(self, request, pk=None):
        app = self.get_object()
        services.screen(app)
        app.save(update_fields=["screening_score", "screening_flags", "knocked_out", "updated_at"])
        return Response(ApplicationListSerializer(app, context=self.get_serializer_context()).data)

    @action(detail=True)
    def cv(self, request, pk=None):
        app = self.get_object()
        if not app.cv:
            raise BusinessRuleError("No CV was attached.")
        audit.log("download", app, {"file": "cv"})
        return safe_file_response(app.cv, app.cv_name or "cv", inline=True)


# ---------------------------------------------------------------- interviews
class ScorecardSerializer(serializers.ModelSerializer):
    panelist_name = serializers.SerializerMethodField()

    class Meta:
        model = Scorecard
        exclude = ["organization"]

    def get_panelist_name(self, obj):
        return obj.panelist.get_full_name() or obj.panelist.username


class OrgUserField(serializers.PrimaryKeyRelatedField):
    def get_queryset(self):
        from django.contrib.auth import get_user_model

        from apps.core.context import get_current_org

        return get_user_model().objects.filter(organization=get_current_org(), is_active=True)


class InterviewSerializer(TenantSerializer):
    panel = OrgUserField(many=True)
    panel_names = serializers.SerializerMethodField()
    candidate_name = serializers.CharField(source="application.candidate.full_name", read_only=True)
    vacancy_title = serializers.CharField(source="application.vacancy.title", read_only=True)
    criteria = serializers.ListField(source="application.vacancy.criteria", read_only=True)
    scorecards = serializers.SerializerMethodField()
    my_scorecard = serializers.SerializerMethodField()
    application = serializers.PrimaryKeyRelatedField(queryset=Application.objects)
    notify_candidate = serializers.BooleanField(write_only=True, default=True)

    class Meta(TenantSerializer.Meta):
        model = Interview
        read_only_fields = TenantSerializer.Meta.read_only_fields + ["status", "candidate_notified"]

    def get_panel_names(self, obj):
        return [u.get_full_name() or u.username for u in obj.panel.all()]

    def get_scorecards(self, obj):
        """Panelists see colleagues' scores only after submitting their own (avoids anchoring bias)."""
        user = self.context["request"].user
        cards = list(obj.scorecards.all())
        mine = any(c.panelist_id == user.pk for c in cards)
        if has_perm(user, "recruitment.manage") or mine:
            return ScorecardSerializer(cards, many=True).data
        return []

    def get_my_scorecard(self, obj):
        user = self.context["request"].user
        c = next((c for c in obj.scorecards.all() if c.panelist_id == user.pk), None)
        return ScorecardSerializer(c).data if c else None


class InterviewViewSet(TenantModelViewSet):
    queryset = Interview.objects.select_related("application__candidate", "application__vacancy") \
        .prefetch_related("panel", "scorecards__panelist")
    serializer_class = InterviewSerializer
    perm_module = "recruitment"
    perm_read = "recruitment.view"
    perm_write = "recruitment.manage"
    perm_map = {"list": None, "retrieve": None, "score": None, "cv": None}
    http_method_names = ["get", "post", "patch", "head", "options"]
    filterset_fields = ["application", "status"]

    def get_queryset(self):
        qs = super().get_queryset()
        if not has_perm(self.request.user, "recruitment.view") or self.request.query_params.get("mine") == "1":
            qs = qs.filter(panel=self.request.user)
        return qs.distinct()

    def perform_create(self, serializer):
        d = dict(serializer.validated_data)
        panel = d.pop("panel")
        notify = d.pop("notify_candidate", True)
        app = d.pop("application")
        serializer.instance = services.schedule_interview(app, d, panel, self.request.user, notify=notify)

    def perform_update(self, serializer):
        if serializer.instance.status != "scheduled":
            raise BusinessRuleError("Only scheduled interviews can be changed.")
        serializer.validated_data.pop("notify_candidate", None)
        serializer.validated_data.pop("application", None)
        serializer.save()

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        iv = services.cancel_interview(self.get_object(), request.user, _bool(request.data.get("notify", True)))
        return Response(self.get_serializer(iv).data)

    @action(detail=True, methods=["post"], url_path="mark")
    def mark(self, request, pk=None):
        iv = self.get_object()
        status = request.data.get("status")
        if status not in ("completed", "no_show"):
            raise BusinessRuleError("Status must be completed or no_show.")
        iv.status = status
        iv.save(update_fields=["status", "updated_at"])
        return Response(self.get_serializer(iv).data)

    @action(detail=True)
    def cv(self, request, pk=None):
        """Panel members can read the candidate's CV for interviews they sit on."""
        app = self.get_object().application
        if not app.cv:
            raise BusinessRuleError("No CV was attached.")
        audit.log("download", app, {"file": "cv", "via": "interview"})
        return safe_file_response(app.cv, app.cv_name or "cv", inline=True)

    @action(detail=True, methods=["post"])
    def score(self, request, pk=None):
        iv = get_object_or_404(Interview.objects.all(), pk=pk)
        d = request.data
        services.submit_scorecard(iv, request.user, d.get("ratings") or {}, d.get("recommendation", ""),
                                  d.get("strengths", ""), d.get("concerns", ""),
                                  _bool(d.get("conflict_of_interest", False)))
        iv.refresh_from_db()
        return Response(self.get_serializer(iv).data)


# ---------------------------------------------------------------- reference checks
class CheckSerializer(TenantSerializer):
    checked_by_name = serializers.SerializerMethodField()
    application = serializers.PrimaryKeyRelatedField(queryset=Application.objects)

    class Meta(TenantSerializer.Meta):
        model = ReferenceCheck
        read_only_fields = TenantSerializer.Meta.read_only_fields + ["status", "completed_at", "checked_by"]

    def get_checked_by_name(self, obj):
        return (obj.checked_by.get_full_name() or obj.checked_by.username) if obj.checked_by_id else None


class CheckViewSet(TenantModelViewSet):
    queryset = ReferenceCheck.objects.select_related("checked_by")
    serializer_class = CheckSerializer
    perm_module = "recruitment"
    perm_read = "recruitment.view"
    perm_write = "recruitment.manage"
    filterset_fields = ["application", "status", "check_type"]

    @action(detail=True, methods=["post"], url_path="set-status")
    def set_status(self, request, pk=None):
        chk = self.get_object()
        if "consent_obtained" in request.data:
            chk.consent_obtained = _bool(request.data["consent_obtained"])
        services.update_check(chk, request.user, request.data.get("status", chk.status),
                              request.data.get("outcome_notes", ""))
        return Response(self.get_serializer(chk).data)


# ---------------------------------------------------------------- offers
class OfferSerializer(TenantSerializer):
    candidate_name = serializers.CharField(source="application.candidate.full_name", read_only=True)
    vacancy_title = serializers.CharField(source="application.vacancy.title", read_only=True)
    job_title_name = DisplayField("job_title")
    department_name = DisplayField("department")
    grade_name = DisplayField("grade")
    supervisor_name = DisplayField("supervisor")
    application = serializers.PrimaryKeyRelatedField(queryset=Application.objects)
    job_title = serializers.PrimaryKeyRelatedField(queryset=JobTitle.objects)
    department = serializers.PrimaryKeyRelatedField(queryset=Department.objects)
    position = serializers.PrimaryKeyRelatedField(queryset=Position.objects, required=False, allow_null=True)
    grade = serializers.PrimaryKeyRelatedField(queryset=Grade.objects, required=False, allow_null=True)
    grade_step = serializers.PrimaryKeyRelatedField(queryset=GradeStep.objects, required=False, allow_null=True)
    supervisor = serializers.PrimaryKeyRelatedField(queryset=Employee.objects, required=False, allow_null=True)
    warnings = serializers.SerializerMethodField()
    has_letter = serializers.SerializerMethodField()
    revise = serializers.BooleanField(write_only=True, default=False)
    submit = serializers.BooleanField(write_only=True, default=False)

    class Meta(TenantSerializer.Meta):
        model = Offer
        exclude = ["organization", "token", "letter", "accepted_ip"]
        read_only_fields = TenantSerializer.Meta.read_only_fields + [
            "reference", "revision", "status", "sent_at", "responded_at", "response_note", "accepted_name"]

    def get_warnings(self, obj):
        return services.offer_warnings(obj)

    def get_has_letter(self, obj):
        return bool(obj.letter)


class OfferViewSet(TenantModelViewSet):
    queryset = Offer.objects.select_related("application__candidate", "application__vacancy__requisition",
                                            "job_title", "department", "grade", "grade_step", "supervisor")
    serializer_class = OfferSerializer
    perm_module = "recruitment"
    perm_read = "recruitment.offer"
    perm_write = "recruitment.offer"
    http_method_names = ["get", "post", "patch", "head", "options"]
    filterset_fields = ["application", "status"]
    search_fields = ["reference", "application__candidate__last_name"]

    def perform_create(self, serializer):
        d = dict(serializer.validated_data)
        submit = d.pop("submit", False)
        app = d.pop("application")
        offer = services.create_offer(app, d, self.request.user)
        if submit:
            services.submit_offer(offer, self.request.user)
        serializer.instance = offer

    def perform_update(self, serializer):
        if serializer.instance.status not in ("draft", "returned"):
            raise BusinessRuleError("Only draft or returned offers can be edited; create a revision instead.")
        for k in ("submit", "revise", "application"):
            serializer.validated_data.pop(k, None)
        serializer.save()

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        return Response(self.get_serializer(services.submit_offer(self.get_object(), request.user)).data)

    @action(detail=True, methods=["post"])
    def send(self, request, pk=None):
        return Response(self.get_serializer(services.send_offer(self.get_object(), request.user)).data)

    @action(detail=True, methods=["post"])
    def withdraw(self, request, pk=None):
        return Response(self.get_serializer(
            services.withdraw_offer(self.get_object(), request.user, request.data.get("reason", ""))).data)

    @action(detail=True)
    def letter(self, request, pk=None):
        from django.http import HttpResponse

        offer = self.get_object()
        if offer.letter:
            return FileResponse(offer.letter.open("rb"), filename=f"offer-{offer.reference}.pdf",
                                content_type="application/pdf")
        return HttpResponse(services.offer_letter_pdf(offer), content_type="application/pdf")

    @action(detail=True, methods=["post"])
    def hire(self, request, pk=None):
        offer = self.get_object()
        extra = {k: request.data.get(k) for k in ("staff_number", "allow_duplicate") if k in request.data}
        if "allow_duplicate" in extra:
            extra["allow_duplicate"] = _bool(extra["allow_duplicate"])
        emp = services.hire_from_offer(offer, request.user, extra)
        return Response({"employee": emp.id, "staff_number": emp.staff_number,
                         "detail": f"{emp.full_name} hired as {emp.staff_number}. Onboarding has started."},
                        status=201)


# ---------------------------------------------------------------- analytics
class AnalyticsView(APIView):
    def get(self, request):
        if not has_perm(request.user, "recruitment.view"):
            raise PermissionDenied()
        p = request.query_params
        return Response(services.analytics(p.get("date_from") or None, p.get("date_to") or None,
                                           p.get("department") or None))


# ---------------------------------------------------------------- internal vacancies (self-service)
class PublicVacancySerializer(serializers.ModelSerializer):
    department = serializers.CharField(source="department.name", read_only=True)
    location = serializers.CharField(source="location.name", read_only=True, default=None)
    employment_type = serializers.CharField(source="get_employment_type_display", read_only=True)
    min_qualification = serializers.CharField(source="get_min_qualification_display", read_only=True)
    questions = serializers.SerializerMethodField()

    class Meta:
        model = Vacancy
        fields = ["id", "reference", "title", "department", "location", "employment_type", "openings", "summary",
                  "responsibilities", "requirements", "salary_display", "min_qualification",
                  "min_experience_years", "closing_date", "published_at", "questions"]

    def get_questions(self, obj):
        return [{"key": q_["key"], "question": q_["question"], "type": q_.get("type", "text"),
                 "required": q_.get("required", True)} for q_ in obj.screening_questions or []]


class InternalVacancyView(APIView):
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get(self, request):
        emp = getattr(request.user, "employee", None)
        mine = []
        if emp:
            mine = [{"id": a.id, "reference": a.reference, "vacancy": a.vacancy.title, "vacancy_id": a.vacancy_id,
                     "stage": a.get_stage_display(), "applied_at": a.applied_at}
                    for a in Application.objects.filter(candidate__employee=emp).select_related("vacancy")]
        vacancies = services.open_vacancies(internal=True).select_related("department", "location")
        return Response({"vacancies": PublicVacancySerializer(vacancies, many=True).data, "my_applications": mine})

    def post(self, request):
        emp = getattr(request.user, "employee", None)
        if emp is None:
            raise BusinessRuleError("Your account is not linked to an employee record.")
        vac = get_object_or_404(services.open_vacancies(internal=True), pk=request.data.get("vacancy"))
        data = {"first_name": emp.first_name, "last_name": emp.last_name, "phone": emp.phone,
                "email": emp.work_email or emp.personal_email or request.user.email,
                "current_employer": emp.organization.name,
                "current_title": emp.job_title.name if emp.job_title_id else "", "gender": emp.gender,
                "highest_qualification": request.data.get("highest_qualification") or "none",
                "years_experience": request.data.get("years_experience") or 0}
        answers = request.data.get("answers") or {}
        if isinstance(answers, str):
            import json

            answers = json.loads(answers or "{}")
        app = services.apply(vac, data, cv=request.FILES.get("cv"), cover_letter=request.data.get("cover_letter", ""),
                             answers=answers, source="internal", employee=emp,
                             consent=_bool(request.data.get("consent")), actor=request.user)
        return Response({"id": app.id, "reference": app.reference}, status=201)


# ---------------------------------------------------------------- public career portal & offer response
def _org(code):
    from apps.tenancy.models import Organization

    org = Organization.objects.filter(code=code, is_active=True).first()
    if org is None:
        raise NotFound("Careers page not found.")
    return org


class PublicBase(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []


class CareersView(PublicBase):
    def get(self, request, org_code):
        org = _org(org_code)
        with org_context(org):
            vacancies = services.open_vacancies(internal=False).select_related("department", "location")
            return Response({"organization": {"name": org.name, "website": org.website},
                             "vacancies": PublicVacancySerializer(vacancies, many=True).data,
                             "qualifications": [{"value": k, "label": v} for k, v in QUALIFICATIONS]})


class CareerVacancyView(PublicBase):
    def get(self, request, org_code, pk):
        org = _org(org_code)
        with org_context(org):
            vac = get_object_or_404(services.open_vacancies(internal=False), pk=pk)
            return Response({"organization": {"name": org.name}, "vacancy": PublicVacancySerializer(vac).data,
                             "qualifications": [{"value": k, "label": v} for k, v in QUALIFICATIONS]})


class PublicApplySerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=80)
    last_name = serializers.CharField(max_length=80)
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=20)
    gender = serializers.ChoiceField(choices=[("male", "Male"), ("female", "Female"), ("", "Prefer not to say")],
                                     required=False, allow_blank=True)
    location = serializers.CharField(max_length=100, required=False, allow_blank=True)
    highest_qualification = serializers.ChoiceField(choices=QUALIFICATIONS)
    field_of_study = serializers.CharField(max_length=120, required=False, allow_blank=True)
    years_experience = serializers.DecimalField(max_digits=4, decimal_places=1, min_value=0, max_value=60)
    current_employer = serializers.CharField(max_length=150, required=False, allow_blank=True)
    current_title = serializers.CharField(max_length=150, required=False, allow_blank=True)
    linkedin = serializers.URLField(required=False, allow_blank=True)
    cover_letter = serializers.CharField(max_length=5000, required=False, allow_blank=True)
    answers = serializers.JSONField(required=False)
    cv = serializers.FileField()
    consent = serializers.BooleanField()
    talent_pool = serializers.BooleanField(default=False)
    website = serializers.CharField(required=False, allow_blank=True)  # honeypot


class CareerApplyView(PublicBase):
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "apply"

    def post(self, request, org_code, pk):
        org = _org(org_code)
        s = PublicApplySerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = dict(s.validated_data)
        if d.pop("website", ""):
            return Response({"reference": "received"}, status=201)  # silently drop bots
        answers = d.pop("answers", None) or {}
        if isinstance(answers, str):
            import json

            answers = json.loads(answers or "{}")
        with org_context(org):
            vac = get_object_or_404(services.open_vacancies(internal=False), pk=pk)
            app = services.apply(vac, d, cv=d.pop("cv"), cover_letter=d.pop("cover_letter", ""), answers=answers,
                                 consent=d.pop("consent"), talent_pool=d.pop("talent_pool"))
            return Response({"reference": app.reference,
                             "detail": "Thank you. Your application has been received and a confirmation sent "
                                       "to your email."}, status=201)


class OfferResponseView(PublicBase):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "apply"

    def _offer(self, token):
        offer = services.offer_by_token(token)
        if offer.status not in ("sent", "negotiating", "accepted", "declined", "expired"):
            raise NotFound("This offer link is no longer valid.")
        return offer

    def get(self, request, token):
        offer = self._offer(token)
        with org_context(offer.organization):
            if request.query_params.get("letter") == "1":
                if not offer.letter:
                    raise BusinessRuleError("The offer letter is not available.")
                return FileResponse(offer.letter.open("rb"), filename=f"offer-{offer.reference}.pdf",
                                    content_type="application/pdf", as_attachment=False)
            cand = offer.application.candidate
            return Response({
                "organization": offer.organization.name, "candidate_name": cand.full_name,
                "job_title": offer.job_title.name, "department": offer.department.name,
                "start_date": offer.start_date, "expiry_date": offer.expiry_date,
                "basic_salary": offer.basic_salary, "allowances": offer.allowances,
                "employment_type": offer.get_employment_type_display(), "probation_months": offer.probation_months,
                "status": offer.status, "reference": offer.reference, "revision": offer.revision,
                "expired": offer.expiry_date < dt.date.today()})

    def post(self, request, token):
        offer = self._offer(token)
        with org_context(offer.organization):
            services.respond_offer(offer, request.data.get("decision", ""), request.data.get("typed_name", ""),
                                   request.data.get("note", ""), client_ip(request))
            return Response({"status": offer.status})
