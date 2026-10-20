from django.utils import timezone
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit import services as audit
from apps.core.exceptions import BusinessRuleError
from apps.core.exports import tabular_response
from apps.core.serializers import DisplayField, TenantSerializer
from apps.core.views import TenantModelViewSet
from apps.rbac.permissions import require
from apps.rbac.services import has_perm

from . import services
from .models import ExportRequest, ScheduledReport


class DashboardView(APIView):
    permission_classes = [IsAuthenticated, require("reports.view")]

    def get(self, request):
        return Response(services.dashboard(request.user))


class AnalyticsView(APIView):
    permission_classes = [IsAuthenticated, require("reports.view")]

    def get(self, request):
        return Response(services.strategic(request.user))


class ReportCatalogView(APIView):
    permission_classes = [IsAuthenticated, require("reports.view")]

    def get(self, request):
        return Response([{"code": c, "name": n} for c, (n, _) in services.REPORTS.items()])


class RunReportView(APIView):
    permission_classes = [IsAuthenticated, require("reports.view")]

    def get(self, request, code):
        if code not in services.REPORTS:
            raise BusinessRuleError("Unknown report.")
        name, fn = services.REPORTS[code]
        params = request.query_params.dict()
        headers, rows = fn(request.user, params)
        fmt = params.get("format")
        if fmt in ("xlsx", "csv"):
            approved = ExportRequest.objects.filter(pk=params.get("export_request"), status="approved",
                                                    created_by=request.user, report_code=code).first()
            if not has_perm(request.user, "reports.export") and approved is None:
                raise BusinessRuleError("Export requires approval. Submit an export request.", code="export_approval")
            if approved:
                approved.status = "downloaded"
                approved.save(update_fields=["status"])
            audit.log("export", None, {"report": code, "rows": len(rows)}, object_repr=name)
            return tabular_response(headers, rows, code, fmt, name[:31])
        return Response({"name": name, "headers": headers, "rows": rows})


class ExportRequestSerializer(TenantSerializer):
    requested_by = DisplayField("created_by")

    class Meta(TenantSerializer.Meta):
        model = ExportRequest
        read_only_fields = TenantSerializer.Meta.read_only_fields + ["status", "decided_by", "decided_at"]


class ExportRequestViewSet(TenantModelViewSet):
    queryset = ExportRequest.objects.all()
    serializer_class = ExportRequestSerializer
    permission_classes = [IsAuthenticated, require("reports.view")]
    http_method_names = ["get", "post"]

    def get_queryset(self):
        qs = super().get_queryset()
        if has_perm(self.request.user, "reports.export"):
            return qs
        return qs.filter(created_by=self.request.user)

    @action(detail=True, methods=["post"])
    def decide(self, request, pk=None):
        req = self.get_object()
        if not has_perm(request.user, "reports.export"):
            raise PermissionDenied("Not permitted.")
        if req.created_by_id == request.user.id:
            raise BusinessRuleError("You cannot approve your own export request.")
        req.status = "approved" if request.data.get("approve") else "rejected"
        req.decided_by = request.user
        req.decided_at = timezone.now()
        req.save()
        return Response(self.get_serializer(req).data)


class ScheduledReportSerializer(TenantSerializer):
    class Meta(TenantSerializer.Meta):
        model = ScheduledReport
        read_only_fields = TenantSerializer.Meta.read_only_fields + ["last_sent_at"]


class ScheduledReportViewSet(TenantModelViewSet):
    queryset = ScheduledReport.objects.prefetch_related("recipients")
    serializer_class = ScheduledReportSerializer
    perm_module = "reports"
    perm_read = "reports.export"
    perm_write = "reports.export"
    pagination_class = None
