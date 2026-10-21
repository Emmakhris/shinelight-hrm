import datetime as dt

from django.db.models import Q
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import BusinessRuleError
from apps.core.serializers import DisplayField, TenantSerializer
from apps.core.views import TenantModelViewSet
from apps.employees.models import Employee
from apps.organization.models import Department, JobTitle
from apps.performance.models import Competency
from apps.rbac.services import can_access_employee, has_perm, scope_queryset

from . import services
from .models import (
    Course,
    CourseModule,
    CPDRecord,
    CPDRequirement,
    DevelopmentGoal,
    Enrollment,
    MentoringSession,
    Mentorship,
    QuizQuestion,
    Session,
    TrainingBudget,
)


def _scoped(user, qs, prefix="employee__", extra=None):
    """Own records (plus `extra`), and records in the user's learning.view scope."""
    cond = Q(**{f"{prefix}user": user})
    if extra is not None:
        cond |= extra
    if has_perm(user, "learning.view"):
        cond |= Q(pk__in=scope_queryset(user, qs, "learning.view", prefix).values("pk"))
    return qs.filter(cond)


# ---------------------------------------------------------------- catalogue
class CourseSerializer(TenantSerializer):
    job_titles = serializers.PrimaryKeyRelatedField(queryset=JobTitle.objects, many=True, required=False)
    competencies = serializers.PrimaryKeyRelatedField(many=True, required=False,
                                                      queryset=Competency.objects)
    category_label = serializers.CharField(source="get_category_display", read_only=True)
    delivery_label = serializers.CharField(source="get_delivery_display", read_only=True)
    competency_requirement_name = DisplayField("competency_requirement")
    upcoming_sessions = serializers.SerializerMethodField()
    module_count = serializers.SerializerMethodField()
    question_count = serializers.SerializerMethodField()
    my_enrollment = serializers.SerializerMethodField()

    class Meta(TenantSerializer.Meta):
        model = Course

    def get_upcoming_sessions(self, obj):
        now = dt.datetime.now(dt.UTC)
        return [{"id": s.id, "start": s.start, "end": s.end, "venue": s.venue,
                 "seats_left": services._seats_left(s)}
                for s in obj.sessions.all() if s.status == "scheduled" and s.start >= now]

    def get_module_count(self, obj):
        return obj.modules.count()

    def get_question_count(self, obj):
        return obj.questions.count()

    def get_my_enrollment(self, obj):
        emp = getattr(self.context["request"].user, "employee", None)
        if emp is None:
            return None
        e = obj.enrollments.filter(employee=emp).order_by("-created_at").first()
        return {"id": e.id, "status": e.status, "completed_at": e.completed_at, "expires_on": e.expires_on} if e else None


class CourseViewSet(TenantModelViewSet):
    queryset = Course.objects.prefetch_related("job_titles", "competencies", "sessions", "modules", "questions") \
        .select_related("competency_requirement")
    serializer_class = CourseSerializer
    perm_module = "learning"
    perm_map = {"list": None, "retrieve": None, "assign": "learning.manage"}
    perm_write = "learning.manage"
    filterset_fields = ["category", "delivery", "is_mandatory", "is_active"]
    search_fields = ["title", "code", "description", "provider"]

    def get_queryset(self):
        qs = super().get_queryset()
        if not has_perm(self.request.user, "learning.manage"):
            qs = qs.filter(is_active=True)
        return qs

    @action(detail=True, methods=["post"])
    def assign(self, request, pk=None):
        course = self.get_object()
        ids = request.data.get("employees") or []
        emps = Employee.objects.filter(pk__in=ids)
        if request.data.get("department"):
            from apps.rbac.services import department_descendants

            emps = Employee.objects.filter(department_id__in=department_descendants(int(request.data["department"])),
                                           status__in=services.ACTIVE)
        due = request.data.get("due_date")
        n = services.assign(course, emps, request.user, dt.date.fromisoformat(due) if due else None)
        return Response({"assigned": n})


class ModuleSerializer(TenantSerializer):
    course = serializers.PrimaryKeyRelatedField(queryset=Course.objects)

    class Meta(TenantSerializer.Meta):
        model = CourseModule


class ModuleViewSet(TenantModelViewSet):
    queryset = CourseModule.objects.all()
    serializer_class = ModuleSerializer
    perm_module = "learning"
    perm_read = "learning.manage"
    perm_write = "learning.manage"
    filterset_fields = ["course"]
    pagination_class = None


class QuestionSerializer(TenantSerializer):
    course = serializers.PrimaryKeyRelatedField(queryset=Course.objects)

    class Meta(TenantSerializer.Meta):
        model = QuizQuestion

    def validate(self, data):
        opts = data.get("options", getattr(self.instance, "options", []))
        correct = data.get("correct", getattr(self.instance, "correct", []))
        if len(opts) < 2:
            raise serializers.ValidationError({"options": "Give at least two options."})
        if not correct or any(not isinstance(i, int) or not 0 <= i < len(opts) for i in correct):
            raise serializers.ValidationError({"correct": "Mark at least one correct option (0-based index)."})
        return data


class QuestionViewSet(TenantModelViewSet):
    """Assessment questions with answers: training administrators only."""

    queryset = QuizQuestion.objects.all()
    serializer_class = QuestionSerializer
    perm_module = "learning"
    perm_read = "learning.manage"
    perm_write = "learning.manage"
    filterset_fields = ["course"]
    pagination_class = None


class SessionSerializer(TenantSerializer):
    course = serializers.PrimaryKeyRelatedField(queryset=Course.objects)
    course_title = serializers.CharField(source="course.title", read_only=True)
    booked = serializers.SerializerMethodField()

    class Meta(TenantSerializer.Meta):
        model = Session
        read_only_fields = TenantSerializer.Meta.read_only_fields + ["status"]

    def get_booked(self, obj):
        return obj.capacity - services._seats_left(obj)

    def validate(self, data):
        if data.get("end") and data.get("start") and data["end"] <= data["start"]:
            raise serializers.ValidationError({"end": "End must be after start."})
        return data


class SessionViewSet(TenantModelViewSet):
    queryset = Session.objects.select_related("course")
    serializer_class = SessionSerializer
    perm_module = "learning"
    perm_map = {"list": None, "retrieve": None, "roster": "learning.manage", "attendance": "learning.manage",
                "cancel": "learning.manage"}
    perm_write = "learning.manage"
    filterset_fields = ["course", "status"]

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get("upcoming") == "1":
            qs = qs.filter(status="scheduled", start__gte=dt.datetime.now(dt.UTC))
        return qs

    @action(detail=True)
    def roster(self, request, pk=None):
        s = self.get_object()
        return Response([{"enrollment": e.id, "employee": e.employee.full_name, "staff_number": e.employee.staff_number,
                          "department": e.employee.department.name if e.employee.department_id else None,
                          "status": e.status, "score": e.quiz_score}
                         for e in s.enrollments.select_related("employee__department")
                         .exclude(status__in=["cancelled", "rejected", "pending", "returned"])])

    @action(detail=True, methods=["post"])
    def attendance(self, request, pk=None):
        n = services.record_attendance(self.get_object(), request.user, request.data.get("rows") or [])
        return Response({"recorded": n})

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        s = self.get_object()
        if s.status != "scheduled":
            raise BusinessRuleError("Only scheduled sessions can be cancelled.")
        s.status = "cancelled"
        s.save(update_fields=["status", "updated_at"])
        affected = [e for e in s.enrollments.filter(status__in=["enrolled", "waitlisted"]).select_related("employee__user")]
        for e in affected:
            e.session = None
            e.save(update_fields=["session", "updated_at"])
        services._notify([e.employee.user for e in affected], f"Training session cancelled: {s.course.title}",
                         "Your session was cancelled. You will be offered another date.", "/learning")
        return Response(self.get_serializer(s).data)


# ---------------------------------------------------------------- enrolments
class EnrollmentSerializer(TenantSerializer):
    employee = serializers.PrimaryKeyRelatedField(queryset=Employee.objects, required=False)
    course = serializers.PrimaryKeyRelatedField(queryset=Course.objects)
    session = serializers.PrimaryKeyRelatedField(queryset=Session.objects, required=False, allow_null=True)
    development_goal = serializers.PrimaryKeyRelatedField(queryset=DevelopmentGoal.objects, required=False,
                                                          allow_null=True)
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    department_name = serializers.CharField(source="employee.department.name", read_only=True, default=None)
    course_title = serializers.CharField(source="course.title", read_only=True)
    delivery = serializers.CharField(source="course.delivery", read_only=True)
    session_start = serializers.DateTimeField(source="session.start", read_only=True, default=None)
    session_venue = serializers.CharField(source="session.venue", read_only=True, default=None)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    is_mine = serializers.SerializerMethodField()
    is_supervisor = serializers.SerializerMethodField()

    class Meta(TenantSerializer.Meta):
        model = Enrollment
        read_only_fields = TenantSerializer.Meta.read_only_fields + [
            "status", "cost", "modules_done", "quiz_score", "attempts", "completed_at", "expires_on",
            "feedback_rating", "feedback_comments", "effectiveness_rating", "effectiveness_comments",
            "effectiveness_by", "due_date"]

    def get_is_mine(self, obj):
        return obj.employee.user_id == self.context["request"].user.pk

    def get_is_supervisor(self, obj):
        sup = obj.employee.supervisor
        return bool(sup and sup.user_id == self.context["request"].user.pk)


class EnrollmentDetailSerializer(EnrollmentSerializer):
    modules = serializers.SerializerMethodField()
    questions = serializers.SerializerMethodField()
    pass_mark = serializers.IntegerField(source="course.pass_mark", read_only=True)
    course_description = serializers.CharField(source="course.description", read_only=True)
    course_objectives = serializers.CharField(source="course.objectives", read_only=True)
    cpd_credits = serializers.DecimalField(source="course.cpd_credits", max_digits=5, decimal_places=1, read_only=True)

    def get_modules(self, obj):
        return [{"id": m.id, "title": m.title, "kind": m.kind, "content": m.content, "url": m.url,
                 "minutes": m.minutes, "done": m.id in (obj.modules_done or [])} for m in obj.course.modules.all()]

    def get_questions(self, obj):
        # never send the correct answers to the browser
        return [{"id": q.id, "text": q.text, "options": q.options, "multiple": len(q.correct) > 1}
                for q in obj.course.questions.all()]


class EnrollmentViewSet(TenantModelViewSet):
    queryset = Enrollment.objects.select_related("employee__department", "employee__supervisor", "course", "session")
    perm_module = "learning"
    perm_map = {k: None for k in ("list", "retrieve", "create", "module", "quiz", "feedback", "effectiveness",
                                  "cancel")}
    perm_map.update({"complete": "learning.manage"})
    http_method_names = ["get", "post", "head", "options"]
    filterset_fields = ["status", "course", "session", "source", "employee"]
    search_fields = ["employee__first_name", "employee__last_name", "course__title"]

    def get_serializer_class(self):
        return EnrollmentDetailSerializer if self.action == "retrieve" else EnrollmentSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        p = self.request.query_params
        if p.get("mine") == "1":
            return qs.filter(employee__user=user)
        if p.get("team") == "1":
            return qs.filter(employee__supervisor__user=user)
        if p.get("open") == "1":
            qs = qs.filter(status__in=Enrollment.OPEN)
        return _scoped(user, qs, extra=Q(employee__supervisor__user=user))

    def create(self, request, *args, **kwargs):
        s = EnrollmentSerializer(data=request.data, context=self.get_serializer_context())
        s.is_valid(raise_exception=True)
        d = s.validated_data
        own = getattr(request.user, "employee", None)
        emp = d.get("employee") or own
        if emp is None:
            raise BusinessRuleError("Your account is not linked to an employee record.")
        source = "request" if emp == own else ("hr" if has_perm(request.user, "learning.manage") else "manager")
        e = services.request_training(emp, d["course"], request.user, d.get("session"), d.get("reason", ""), source,
                                      d.get("development_goal"))
        return Response(EnrollmentSerializer(e, context=self.get_serializer_context()).data, status=201)

    def _get(self):
        return self.get_object()

    @action(detail=True, methods=["post"])
    def module(self, request, pk=None):
        e = services.mark_module(self._get(), int(request.data.get("module", 0)), request.user)
        return Response(EnrollmentDetailSerializer(e, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["post"])
    def quiz(self, request, pk=None):
        e = self._get()
        score = services.submit_quiz(e, request.user, request.data.get("answers") or {})
        e.refresh_from_db()
        return Response({"score": score, "passed": score >= e.course.pass_mark, "status": e.status,
                         "attempts": e.attempts})

    @action(detail=True, methods=["post"])
    def feedback(self, request, pk=None):
        e = services.give_feedback(self._get(), request.user, request.data.get("rating"),
                                   request.data.get("comments", ""))
        return Response(EnrollmentSerializer(e, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["post"])
    def effectiveness(self, request, pk=None):
        e = services.evaluate_effectiveness(self._get(), request.user, request.data.get("rating"),
                                            request.data.get("comments", ""))
        return Response(EnrollmentSerializer(e, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        e = self._get()
        if not (e.employee.user_id == request.user.pk or has_perm(request.user, "learning.manage")):
            raise PermissionDenied()
        services.cancel(e, request.user, request.data.get("reason", ""))
        return Response(EnrollmentSerializer(e, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        """Record completion of external / on-the-job training (training officer)."""
        e = self._get()
        if e.status not in ("enrolled", "in_progress"):
            raise BusinessRuleError("Only active enrolments can be completed.")
        on = request.data.get("completed_on")
        score = request.data.get("score")
        services.complete(e, dt.date.fromisoformat(on) if on else None,
                          int(score) if score not in (None, "") else None, request.data.get("assessor", ""))
        return Response(EnrollmentSerializer(e, context=self.get_serializer_context()).data)


# ---------------------------------------------------------------- budgets, CPD, development
class BudgetSerializer(TenantSerializer):
    department = serializers.PrimaryKeyRelatedField(queryset=Department.objects)
    department_name = DisplayField("department")
    status = serializers.SerializerMethodField()

    class Meta(TenantSerializer.Meta):
        model = TrainingBudget

    def get_status(self, obj):
        return services.budget_status(obj.department, obj.year)


class BudgetViewSet(TenantModelViewSet):
    queryset = TrainingBudget.objects.select_related("department")
    serializer_class = BudgetSerializer
    perm_module = "learning"
    perm_read = "learning.manage"
    perm_write = "learning.manage"
    filterset_fields = ["year", "department"]
    pagination_class = None


class CPDSerializer(TenantSerializer):
    employee = serializers.PrimaryKeyRelatedField(queryset=Employee.objects, required=False)
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    verified_by_name = DisplayField("verified_by")

    class Meta(TenantSerializer.Meta):
        model = CPDRecord
        read_only_fields = TenantSerializer.Meta.read_only_fields + ["status", "verified_by", "enrollment"]


class CPDViewSet(TenantModelViewSet):
    queryset = CPDRecord.objects.select_related("employee", "verified_by")
    serializer_class = CPDSerializer
    perm_module = "learning"
    perm_map = {"list": None, "retrieve": None, "create": None, "destroy": None, "summary": None,
                "verify": "learning.manage"}
    http_method_names = ["get", "post", "delete", "head", "options"]
    filterset_fields = ["status", "employee"]

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get("mine") == "1":
            return qs.filter(employee__user=self.request.user)
        return _scoped(self.request.user, qs)

    def perform_create(self, serializer):
        own = getattr(self.request.user, "employee", None)
        emp = serializer.validated_data.get("employee") or own
        if emp is None:
            raise BusinessRuleError("Your account is not linked to an employee record.")
        if emp != own and not can_access_employee(self.request.user, "learning.manage", emp):
            raise PermissionDenied()
        if serializer.validated_data["credits"] <= 0:
            raise BusinessRuleError("Credits must be positive.")
        serializer.save(employee=emp, status="verified" if emp != own else "pending",
                        verified_by=self.request.user if emp != own else None)

    def perform_destroy(self, instance):
        if instance.status == "verified" and not has_perm(self.request.user, "learning.manage"):
            raise BusinessRuleError("Verified records can only be removed by the training office.")
        if instance.employee.user_id != self.request.user.pk and not has_perm(self.request.user, "learning.manage"):
            raise PermissionDenied()
        instance.delete()

    @action(detail=True, methods=["post"])
    def verify(self, request, pk=None):
        rec = services.verify_cpd(self.get_object(), request.user, request.data.get("approve", True) in (True, "true"))
        return Response(self.get_serializer(rec).data)

    @action(detail=False)
    def summary(self, request):
        emp_id = request.query_params.get("employee")
        emp = Employee.objects.filter(pk=emp_id).first() if emp_id else getattr(request.user, "employee", None)
        if emp is None:
            raise BusinessRuleError("No employee record.")
        if emp != getattr(request.user, "employee", None) and not can_access_employee(request.user, "learning.view",
                                                                                         emp):
            raise PermissionDenied()
        year = int(request.query_params.get("year") or dt.date.today().year)
        return Response(services.cpd_summary(emp, year))


class CPDRequirementSerializer(TenantSerializer):
    job_titles = serializers.PrimaryKeyRelatedField(queryset=JobTitle.objects, many=True)

    class Meta(TenantSerializer.Meta):
        model = CPDRequirement


class CPDRequirementViewSet(TenantModelViewSet):
    queryset = CPDRequirement.objects.prefetch_related("job_titles")
    serializer_class = CPDRequirementSerializer
    perm_module = "learning"
    perm_read = "learning.manage"
    perm_write = "learning.manage"
    pagination_class = None


class GoalSerializer(TenantSerializer):
    employee = serializers.PrimaryKeyRelatedField(queryset=Employee.objects, required=False)
    competency = serializers.PrimaryKeyRelatedField(queryset=Competency.objects, required=False,
                                                    allow_null=True)
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    competency_name = DisplayField("competency")
    courses = serializers.SerializerMethodField()
    enrollments = serializers.SerializerMethodField()

    class Meta(TenantSerializer.Meta):
        model = DevelopmentGoal
        read_only_fields = TenantSerializer.Meta.read_only_fields + ["appraisal"]

    def get_courses(self, obj):
        if not obj.competency_id:
            return []
        return [{"id": c.id, "title": c.title} for c in Course.objects.filter(is_active=True, competencies=obj.competency)]

    def get_enrollments(self, obj):
        return [{"id": e.id, "course": e.course.title, "status": e.status} for e in obj.enrollments.all()]


def _can_edit_employee(user, emp):
    sup = emp.supervisor
    return (emp.user_id == user.pk or (sup and sup.user_id == user.pk)
            or can_access_employee(user, "learning.manage", emp))


class GoalViewSet(TenantModelViewSet):
    queryset = DevelopmentGoal.objects.select_related("employee", "competency").prefetch_related("enrollments__course")
    serializer_class = GoalSerializer
    perm_module = "learning"
    perm_map = {k: None for k in ("list", "retrieve", "create", "update", "partial_update", "destroy",
                                  "from_appraisal")}
    filterset_fields = ["employee", "status"]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if self.request.query_params.get("mine") == "1":
            return qs.filter(employee__user=user)
        return _scoped(user, qs, extra=Q(employee__supervisor__user=user))

    def perform_create(self, serializer):
        emp = serializer.validated_data.get("employee") or getattr(self.request.user, "employee", None)
        if emp is None or not _can_edit_employee(self.request.user, emp):
            raise PermissionDenied()
        serializer.save(employee=emp)

    def perform_update(self, serializer):
        if not _can_edit_employee(self.request.user, serializer.instance.employee):
            raise PermissionDenied()
        serializer.validated_data.pop("employee", None)
        serializer.save()

    def perform_destroy(self, instance):
        if not _can_edit_employee(self.request.user, instance.employee):
            raise PermissionDenied()
        instance.delete()

    @action(detail=False, methods=["post"], url_path="from-appraisal")
    def from_appraisal(self, request):
        """Turn an appraisal's low-rated competencies and development needs into plan items."""
        from apps.performance.models import Appraisal

        ap = Appraisal.objects.filter(pk=request.data.get("appraisal")).select_related("employee").first()
        if ap is None or not _can_edit_employee(request.user, ap.employee) or ap.final_rating is None:
            raise BusinessRuleError("Choose a reviewed appraisal you can manage.")
        created = 0
        for cr in ap.competency_ratings.filter(manager_rating__lte=2).select_related("competency"):
            _, was = DevelopmentGoal.objects.get_or_create(
                employee=ap.employee, appraisal=ap, competency=cr.competency,
                defaults={"title": f"Develop: {cr.competency.name}", "actions": ap.development_needs,
                          "target_date": ap.cycle.period_end.replace(year=ap.cycle.period_end.year + 1)})
            created += was
        if not created and ap.development_needs:
            _, was = DevelopmentGoal.objects.get_or_create(employee=ap.employee, appraisal=ap, competency=None,
                                                           defaults={"title": "Development plan from appraisal",
                                                                     "actions": ap.development_needs})
            created += was
        return Response({"created": created})


class MentorshipSerializer(TenantSerializer):
    mentor = serializers.PrimaryKeyRelatedField(queryset=Employee.objects)
    mentee = serializers.PrimaryKeyRelatedField(queryset=Employee.objects)
    mentor_name = serializers.CharField(source="mentor.full_name", read_only=True)
    mentee_name = serializers.CharField(source="mentee.full_name", read_only=True)
    sessions = serializers.SerializerMethodField()

    class Meta(TenantSerializer.Meta):
        model = Mentorship

    def get_sessions(self, obj):
        return [{"id": s.id, "date": s.date, "notes": s.notes, "next_steps": s.next_steps} for s in obj.sessions.all()]

    def validate(self, data):
        if data.get("mentor") and data.get("mentor") == data.get("mentee"):
            raise serializers.ValidationError("Mentor and mentee must be different people.")
        return data


class MentorshipViewSet(TenantModelViewSet):
    queryset = Mentorship.objects.select_related("mentor", "mentee").prefetch_related("sessions")
    serializer_class = MentorshipSerializer
    perm_module = "learning"
    perm_map = {k: None for k in ("list", "retrieve", "create", "update", "partial_update", "log")}
    http_method_names = ["get", "post", "patch", "head", "options"]
    filterset_fields = ["status"]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        mine = Q(mentor__user=user) | Q(mentee__user=user) | Q(mentee__supervisor__user=user)
        if has_perm(user, "learning.manage"):
            return qs
        return qs.filter(mine)

    def perform_create(self, serializer):
        mentee = serializer.validated_data["mentee"]
        sup = mentee.supervisor
        if not ((sup and sup.user_id == self.request.user.pk) or has_perm(self.request.user, "learning.manage")):
            raise PermissionDenied("The mentee's supervisor or HR sets up mentoring.")
        serializer.save()

    def perform_update(self, serializer):
        m = serializer.instance
        user = self.request.user
        if not (m.mentor.user_id == user.pk or has_perm(user, "learning.manage")
                or (m.mentee.supervisor and m.mentee.supervisor.user_id == user.pk)):
            raise PermissionDenied()
        serializer.save()

    @action(detail=True, methods=["post"])
    def log(self, request, pk=None):
        m = self.get_object()
        if request.user.pk not in (m.mentor.user_id, m.mentee.user_id):
            raise PermissionDenied("Only the mentor or mentee can log sessions.")
        if not request.data.get("notes"):
            raise BusinessRuleError("Add notes for the session.")
        MentoringSession.objects.create(mentorship=m, date=request.data.get("date") or dt.date.today(),
                                        notes=request.data["notes"], next_steps=request.data.get("next_steps", ""),
                                        recorded_by=request.user)
        return Response(self.get_serializer(m).data)


# ---------------------------------------------------------------- analytics
class ComplianceView(APIView):
    def get(self, request):
        if not has_perm(request.user, "learning.view", "department") and not has_perm(request.user, "learning.manage"):
            raise PermissionDenied()
        return Response(services.compliance_matrix(request.query_params.get("department") or None))


class NeedsView(APIView):
    def get(self, request):
        if not has_perm(request.user, "learning.manage"):
            raise PermissionDenied()
        p = request.query_params
        return Response(services.training_needs(p.get("cycle") or None, p.get("department") or None))


class ReportView(APIView):
    def get(self, request):
        if not has_perm(request.user, "learning.manage") and not has_perm(request.user, "reports.view"):
            raise PermissionDenied()
        p = request.query_params
        return Response(services.report(int(p["year"]) if p.get("year") else None, p.get("department") or None))
