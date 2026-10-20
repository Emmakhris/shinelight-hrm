from django.contrib.auth import get_user_model
from django.db.models import F, Q
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.core.exceptions import BusinessRuleError
from apps.core.serializers import TenantSerializer
from apps.core.views import TenantModelViewSet
from apps.rbac.services import has_perm

from . import services
from .models import KnowledgeArticle, ServiceCategory, ServiceType, Ticket, TicketComment, TicketEvent

User = get_user_model()


class CategorySerializer(TenantSerializer):
    service_count = serializers.IntegerField(source="services.count", read_only=True)

    class Meta(TenantSerializer.Meta):
        model = ServiceCategory


class ServiceTypeSerializer(TenantSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    team_role_name = serializers.CharField(source="team_role.name", read_only=True, default=None)

    class Meta(TenantSerializer.Meta):
        model = ServiceType


class CatalogueViewSet(TenantModelViewSet):
    perm_module = "servicedesk"
    perm_map = {"list": None, "retrieve": None}
    perm_write = "servicedesk.manage"
    pagination_class = None


class CategoryViewSet(CatalogueViewSet):
    queryset = ServiceCategory.objects.all()
    serializer_class = CategorySerializer


class ServiceTypeViewSet(CatalogueViewSet):
    queryset = ServiceType.objects.select_related("category", "team_role")
    serializer_class = ServiceTypeSerializer
    filterset_fields = ["category", "is_active", "self_service"]
    search_fields = ["name", "description"]


class ArticleSerializer(TenantSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True, default=None)

    class Meta(TenantSerializer.Meta):
        model = KnowledgeArticle
        read_only_fields = TenantSerializer.Meta.read_only_fields + ["views", "helpful_yes", "helpful_no"]


class ArticleViewSet(CatalogueViewSet):
    queryset = KnowledgeArticle.objects.select_related("category")
    serializer_class = ArticleSerializer
    search_fields = ["title", "body", "tags"]
    filterset_fields = ["category", "is_published"]
    perm_map = {"list": None, "retrieve": None, "helpful": None, "suggest": None}
    pagination_class = None

    def get_queryset(self):
        qs = super().get_queryset()
        if not has_perm(self.request.user, "servicedesk.manage"):
            qs = qs.filter(is_published=True)
        return qs

    def retrieve(self, request, *args, **kwargs):
        art = self.get_object()
        KnowledgeArticle.objects.filter(pk=art.pk).update(views=F("views") + 1)
        return Response(self.get_serializer(art).data)

    @action(detail=True, methods=["post"])
    def helpful(self, request, pk=None):
        field = "helpful_yes" if request.data.get("helpful", True) else "helpful_no"
        KnowledgeArticle.objects.filter(pk=pk).update(**{field: F(field) + 1})
        return Response({"detail": "Thanks for the feedback."})

    @action(detail=False)
    def suggest(self, request):
        """Deflection: suggest articles while an employee types a request."""
        q = request.query_params.get("q", "").strip()
        words = [w for w in q.split() if len(w) > 3][:6]
        if not words:
            return Response([])
        cond = Q()
        for w in words:
            cond |= Q(title__icontains=w) | Q(tags__icontains=w) | Q(body__icontains=w)
        arts = self.get_queryset().filter(cond)[:5]
        return Response([{"id": a.id, "title": a.title} for a in arts])


class CommentSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source="author.__str__", read_only=True)
    is_staff_reply = serializers.SerializerMethodField()

    class Meta:
        model = TicketComment
        fields = ["id", "author", "author_name", "body", "is_internal", "attachment", "created_at", "is_staff_reply"]

    def get_is_staff_reply(self, obj):
        return obj.author_id != obj.ticket.requester_id


class EventSerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(source="actor.__str__", read_only=True, default="System")

    class Meta:
        model = TicketEvent
        fields = ["id", "event", "detail", "actor_name", "created_at"]


class TicketSerializer(TenantSerializer):
    service_name = serializers.CharField(source="service_type.name", read_only=True)
    category_name = serializers.CharField(source="service_type.category.name", read_only=True)
    requester_name = serializers.CharField(source="requester.__str__", read_only=True)
    assignee_name = serializers.CharField(source="assignee.__str__", read_only=True, default=None)
    employee_name = serializers.CharField(source="employee.full_name", read_only=True, default=None)
    is_overdue = serializers.SerializerMethodField()

    class Meta(TenantSerializer.Meta):
        model = Ticket
        read_only_fields = [f.name for f in Ticket._meta.fields if f.name not in (
            "service_type", "subject", "description", "form_data", "priority", "channel", "employee")]

    def get_is_overdue(self, obj):
        from django.utils import timezone

        return obj.status in ("new", "open") and bool(obj.resolution_due and obj.resolution_due < timezone.now())


class TicketDetailSerializer(TicketSerializer):
    comments = serializers.SerializerMethodField()
    events = EventSerializer(many=True, read_only=True)
    letter_template = serializers.IntegerField(source="service_type.letter_template_id", read_only=True)

    def get_comments(self, obj):
        qs = obj.comments.select_related("author", "ticket")
        if not services.is_agent(self.context["request"].user):
            qs = qs.filter(is_internal=False)
        return CommentSerializer(qs, many=True).data


class TicketViewSet(TenantModelViewSet):
    queryset = Ticket.objects.select_related("service_type__category", "requester", "assignee", "employee")
    permission_classes = [IsAuthenticated]
    filterset_fields = ["status", "priority", "service_type", "service_type__category", "assignee", "channel"]
    search_fields = ["reference", "subject", "description", "requester__first_name", "requester__last_name"]
    ordering_fields = ["created_at", "resolution_due", "priority"]
    http_method_names = ["get", "post", "head", "options"]

    def get_serializer_class(self):
        return TicketDetailSerializer if self.action == "retrieve" else TicketSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        view = self.request.query_params.get("view")
        if view == "mine" or not services.is_agent(user):
            return qs.filter(requester=user)
        if view == "assigned":
            qs = qs.filter(assignee=user)
        elif view == "unassigned":
            qs = qs.filter(assignee__isnull=True, status__in=services.OPEN)
        elif view == "overdue":
            from django.utils import timezone

            qs = qs.filter(status__in=["new", "open"], resolution_due__lt=timezone.now())
        elif view == "open":
            qs = qs.filter(status__in=services.OPEN)
        if not (has_perm(user, "servicedesk.manage") and has_perm(user, "servicedesk.view_confidential")):
            qs = qs.filter(Q(is_confidential=False) | Q(assignee=user) | Q(requester=user))
        return qs

    def create(self, request, *args, **kwargs):
        s = self.get_serializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        employee = d.get("employee")
        channel = d.get("channel", "portal")
        requester = request.user
        if employee is not None and employee != getattr(request.user, "employee", None):
            if not services.is_agent(request.user):
                raise PermissionDenied("Only HR staff can log requests on behalf of an employee.")
            if employee.user_id:
                requester = employee.user
        elif not services.is_agent(request.user):
            channel = "portal"
        ticket = services.create_ticket(d["service_type"], requester, d["subject"], d["description"], employee,
                                        d.get("priority") if services.is_agent(request.user) else None,
                                        d.get("form_data"), channel)
        if requester != request.user:
            services._event(ticket, "logged_by", request.user, str(request.user))
        return Response(TicketSerializer(ticket, context=self.get_serializer_context()).data, status=201)

    def _ticket(self):
        return self.get_object()

    @action(detail=True, methods=["post"])
    def comment(self, request, pk=None):
        t = self._ticket()
        from apps.documents.models import Document

        att = Document.objects.filter(pk=request.data.get("attachment")).first() if request.data.get("attachment") else None
        services.add_comment(t, request.user, request.data.get("body", "").strip() or "(no text)",
                             bool(request.data.get("internal")), att)
        return Response(TicketDetailSerializer(t, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["post"])
    def assign(self, request, pk=None):
        t = self._ticket()
        if not services.is_agent(request.user):
            raise PermissionDenied()
        user = User.objects.get(pk=request.data.get("user") or request.user.id, organization=request.user.organization)
        services.assign(t, user, request.user)
        return Response(TicketSerializer(t, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["post"])
    def status(self, request, pk=None):
        t = self._ticket()
        services.set_status(t, request.data.get("status"), request.user, request.data.get("note", ""))
        return Response(TicketSerializer(t, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["post"])
    def resolve(self, request, pk=None):
        t = self._ticket()
        services.resolve(t, request.user, request.data.get("resolution", ""))
        return Response(TicketSerializer(t, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["post"])
    def reopen(self, request, pk=None):
        t = self._ticket()
        services.reopen(t, request.user, request.data.get("reason", ""))
        return Response(TicketSerializer(t, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["post"])
    def rate(self, request, pk=None):
        t = self._ticket()
        services.rate(t, request.user, request.data.get("rating", 0), request.data.get("feedback", ""))
        return Response(TicketSerializer(t, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        t = self._ticket()
        services.cancel(t, request.user, request.data.get("reason", ""))
        return Response(TicketSerializer(t, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["post"], url_path="generate-letter")
    def generate_letter(self, request, pk=None):
        from apps.documents.services import generate_letter

        t = self._ticket()
        if not services.is_agent(request.user) or not has_perm(request.user, "documents.generate"):
            raise PermissionDenied()
        tpl = t.service_type.letter_template
        if tpl is None or t.employee is None:
            raise BusinessRuleError("This service has no letter template or no employee.")
        doc = generate_letter(tpl, t.employee, extra={**t.form_data, "addressed_to": t.form_data.get("addressed_to", ""),
                                                       "purpose": t.form_data.get("purpose", "")},
                              reference=t.reference)
        services.add_comment(t, request.user, f"Your {tpl.name} is ready. Download it from My documents.",
                             attachment=doc)
        return Response({"document": doc.id})

    @action(detail=False)
    def metrics(self, request):
        if not has_perm(request.user, "servicedesk.manage") and not has_perm(request.user, "reports.view"):
            raise PermissionDenied()
        return Response(services.metrics(Ticket.objects.all()))

    @action(detail=False)
    def agents(self, request):
        users = [u for u in User.objects.filter(organization=request.user.organization, is_active=True)
                 if services.is_agent(u)]
        return Response([{"id": u.id, "name": str(u)} for u in users])
