from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers
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

from . import builder, predictive, services
from .models import ExportRequest, ReportDefinition, ScheduledReport


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


def export_or_respond(request, code, name, headers, rows, extra=None):
    """Return rows as JSON, or as a file when ?format=xlsx|csv (which needs reports.export or an approved request)."""
    params = request.query_params
    fmt = params.get("format")
    if fmt in ("xlsx", "csv"):
        approved = ExportRequest.objects.filter(pk=params.get("export_request") or None, status="approved",
                                                created_by=request.user, report_code=code).first()
        if not has_perm(request.user, "reports.export") and approved is None:
            raise BusinessRuleError("Export requires approval. Submit an export request.", code="export_approval")
        if approved:
            approved.status = "downloaded"
            approved.save(update_fields=["status"])
        audit.log("export", None, {"report": code, "rows": len(rows)}, object_repr=name)
        return tabular_response(headers, rows, code.replace(":", "-"), fmt, name[:31])
    return Response({"name": name, "headers": headers, "rows": rows, **(extra or {})})


class RunReportView(APIView):
    permission_classes = [IsAuthenticated, require("reports.view")]

    def get(self, request, code):
        report = services.get_report(code, request.user)
        if report is None:
            raise BusinessRuleError("Unknown report.")
        name, fn = report
        headers, rows = fn(request.user, request.query_params.dict())
        return export_or_respond(request, code, name, headers, rows)


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


# ---------------------------------------------------------------- report builder
class ReportDefinitionSerializer(TenantSerializer):
    owner = DisplayField("created_by")
    code = serializers.CharField(read_only=True)
    can_edit = serializers.SerializerMethodField()

    class Meta(TenantSerializer.Meta):
        model = ReportDefinition

    def get_can_edit(self, obj):
        user = self.context["request"].user
        return obj.created_by_id == user.id and has_perm(user, "reports.build")

    def validate(self, attrs):
        keys = ("dataset", "columns", "filters", "group_by", "aggregates", "sort", "limit")
        merged = {k: attrs.get(k, getattr(self.instance, k, None)) for k in keys}
        normalised = builder.validate(merged, self.context["request"].user)
        attrs.update({k: normalised[k] for k in keys[1:]})
        return attrs


class ReportDefinitionViewSet(TenantModelViewSet):
    """Saved custom reports: own and shared ones are listed; only the owner (with reports.build) may change them."""

    queryset = ReportDefinition.objects.select_related("created_by")
    serializer_class = ReportDefinitionSerializer
    perm_module = "reports"
    perm_read = "reports.view"
    perm_write = "reports.build"
    perm_map = {"run": "reports.view", "preview": "reports.build", "datasets": "reports.build"}
    pagination_class = None

    def get_queryset(self):
        return super().get_queryset().filter(Q(created_by=self.request.user) | Q(visibility="shared"))

    def perform_update(self, serializer):
        if serializer.instance.created_by_id != self.request.user.id:
            raise PermissionDenied("Only the owner can change this report. Save a copy instead.")
        serializer.save()

    def perform_destroy(self, instance):
        if instance.created_by_id != self.request.user.id:
            raise PermissionDenied("Only the owner can delete this report.")
        instance.delete()

    @action(detail=False, methods=["get"])
    def datasets(self, request):
        return Response(builder.catalog(request.user))

    @action(detail=False, methods=["post"])
    def preview(self, request):
        spec = {**request.data, "limit": min(int(request.data.get("limit") or 200), 200)}
        headers, rows, meta = builder.run(spec, request.user)
        return Response({"headers": headers, "rows": rows, **meta})

    @action(detail=True, methods=["get"])
    def run(self, request, pk=None):
        d = self.get_object()
        headers, rows, meta = builder.run(d.spec(), request.user)
        return export_or_respond(request, d.code, d.name, headers, rows,
                                 {**meta, "chart": d.chart, "group_by": d.group_by})


# ---------------------------------------------------------------- predictive analytics
class TurnoverForecastView(APIView):
    permission_classes = [IsAuthenticated, require("reports.view")]

    def get(self, request):
        return Response(predictive.turnover_forecast(request.user))


class RetirementForecastView(APIView):
    permission_classes = [IsAuthenticated, require("reports.view")]

    def get(self, request):
        years = max(1, min(int(request.query_params.get("years") or 5), 10))
        return Response(predictive.retirement_forecast(request.user, years))


class AttritionRiskView(APIView):
    """Individual attrition-risk indicators. Restricted, audit-logged, and never about the viewer themselves."""

    permission_classes = [IsAuthenticated, require("analytics.predictive")]

    def get(self, request):
        rows = predictive.risk_scores(request.user, department=request.query_params.get("department") or None)
        band = request.query_params.get("band")
        if band:
            rows = [r for r in rows if r["band"] == band]
        audit.log("view", None, {"report": "attrition_risk", "rows": len(rows)},
                  object_repr="Attrition risk indicators")
        if request.query_params.get("format") in ("xlsx", "csv"):
            headers = ["Staff No", "Name", "Department", "Job title", "Score", "Band", "Factors"]
            data = [[r["staff_number"], r["name"], r["department"], r["job_title"], r["score"], r["band"],
                     "; ".join(f"{f['label']} ({f['detail']})" for f in r["factors"])] for r in rows]
            return export_or_respond(request, "attrition_risk", "Attrition risk indicators", headers, data)
        return Response({"rows": rows, "weights": predictive.weights(request.user.organization),
                         "labels": predictive.FACTOR_LABELS,
                         "thresholds": {"high": predictive.HIGH, "medium": predictive.MEDIUM}})
