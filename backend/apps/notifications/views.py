from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.core.serializers import TenantSerializer
from apps.core.views import TenantModelViewSet
from apps.rbac.permissions import require
from apps.rbac.services import has_perm

from .defaults import DEFAULTS
from .models import Acknowledgment, Announcement, DeliveryLog, Notification, NotificationTemplate
from .services import notify


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ["id", "event_code", "title", "body", "link", "is_read", "read_at", "created_at"]


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["is_read"]

    def get_queryset(self):
        return Notification.objects.filter(recipient=self.request.user)

    @action(detail=False, url_path="unread-count")
    def unread_count(self, request):
        return Response({"unread": self.get_queryset().filter(is_read=False).count()})

    @action(detail=True, methods=["post"], url_path="read")
    def mark_read(self, request, pk=None):
        n = self.get_object()
        n.is_read = True
        n.read_at = timezone.now()
        n.save(update_fields=["is_read", "read_at"])
        return Response({"detail": "ok"})

    @action(detail=False, methods=["post"], url_path="read-all")
    def mark_all_read(self, request):
        self.get_queryset().filter(is_read=False).update(is_read=True, read_at=timezone.now())
        return Response({"detail": "ok"})


class TemplateSerializer(TenantSerializer):
    class Meta(TenantSerializer.Meta):
        model = NotificationTemplate


class TemplateViewSet(TenantModelViewSet):
    queryset = NotificationTemplate.objects.all()
    serializer_class = TemplateSerializer
    perm_module = "notifications"
    perm_read = "notifications.manage"
    perm_write = "notifications.manage"
    pagination_class = None

    @action(detail=False)
    def defaults(self, request):
        return Response(DEFAULTS)


class AnnouncementSerializer(TenantSerializer):
    acknowledged = serializers.SerializerMethodField()
    ack_count = serializers.IntegerField(source="acknowledgments.count", read_only=True)

    class Meta(TenantSerializer.Meta):
        model = Announcement

    def get_acknowledged(self, obj):
        return obj.acknowledgments.filter(user=self.context["request"].user).exists()


class AnnouncementViewSet(TenantModelViewSet):
    queryset = Announcement.objects.prefetch_related("departments", "branches")
    serializer_class = AnnouncementSerializer
    perm_module = "notifications"
    perm_read = None
    perm_write = "notifications.manage"
    perm_map = {"acknowledge": None, "list": None, "retrieve": None}

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if has_perm(user, "notifications.manage") and self.request.query_params.get("manage") == "1":
            return qs
        now = timezone.now()
        qs = qs.filter(publish_at__lte=now).filter(Q(expires_at__isnull=True) | Q(expires_at__gte=now))
        emp = getattr(user, "employee", None)
        audience = Q(audience="all")
        if emp is not None:
            audience |= Q(audience="department", departments=emp.department_id) | Q(audience="branch",
                                                                                     branches=emp.branch_id)
        return qs.filter(audience).distinct()

    def perform_create(self, serializer):
        ann = serializer.save()
        from django.contrib.auth import get_user_model

        users = get_user_model().objects.filter(organization=self.request.user.organization, is_active=True)
        if ann.audience == "department":
            users = users.filter(employee__department__in=ann.departments.all())
        elif ann.audience == "branch":
            users = users.filter(employee__branch__in=ann.branches.all())
        if ann.publish_at <= timezone.now():
            notify("announcement.published", list(users), {"title": ann.title, "summary": ann.body[:200],
                                                           "link": "/announcements"}, channels=("in_app",))

    @action(detail=True, methods=["post"])
    def acknowledge(self, request, pk=None):
        ann = self.get_object()
        Acknowledgment.objects.get_or_create(announcement=ann, user=request.user)
        return Response({"detail": "Acknowledged."})

    @action(detail=True, methods=["get"], permission_classes=[IsAuthenticated, require("notifications.manage")])
    def acknowledgments(self, request, pk=None):
        ann = self.get_object()
        return Response([{"user": str(a.user), "at": a.acknowledged_at} for a in ann.acknowledgments.select_related("user")])


class DeliveryLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeliveryLog
        fields = ["id", "channel", "recipient", "event_code", "status", "error", "created_at"]


class DeliveryLogViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = DeliveryLogSerializer
    permission_classes = [IsAuthenticated, require("notifications.manage")]
    filterset_fields = ["channel", "status"]

    def get_queryset(self):
        return DeliveryLog.objects.all()
