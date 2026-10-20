import datetime as dt

from django.db.models import Q
from django.http import FileResponse
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.audit import services as audit
from apps.core.exceptions import BusinessRuleError
from apps.core.serializers import DisplayField, TenantSerializer
from apps.core.views import TenantModelViewSet
from apps.employees.models import Employee
from apps.rbac.services import can_access_employee, has_perm

from . import services
from .models import (
    Document,
    DocumentAcknowledgment,
    DocumentCategory,
    DocumentVersion,
    LetterRequest,
    LetterTemplate,
    SignatureRequest,
    Signer,
)


class CategorySerializer(TenantSerializer):
    class Meta(TenantSerializer.Meta):
        model = DocumentCategory


class VersionSerializer(TenantSerializer):
    uploaded_by = DisplayField("created_by")

    class Meta(TenantSerializer.Meta):
        model = DocumentVersion
        exclude = ["organization", "file"]


class DocumentSerializer(TenantSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    employee_name = serializers.CharField(source="employee.full_name", read_only=True, default=None)
    versions = VersionSerializer(many=True, read_only=True)
    file = serializers.FileField(write_only=True, required=False)
    is_expired = serializers.SerializerMethodField()
    acknowledged = serializers.SerializerMethodField()

    class Meta(TenantSerializer.Meta):
        model = Document
        read_only_fields = TenantSerializer.Meta.read_only_fields + ["current_version", "retention_until",
                                                                     "is_archived", "legal_hold", "legal_hold_reason"]

    def get_is_expired(self, obj):
        return bool(obj.expiry_date and obj.expiry_date < dt.date.today())

    def get_acknowledged(self, obj):
        user = self.context["request"].user
        return obj.acknowledgments.filter(user=user, version=obj.current_version).exists()


class CategoryViewSet(TenantModelViewSet):
    queryset = DocumentCategory.objects.all()
    serializer_class = CategorySerializer
    perm_module = "documents"
    perm_write = "documents.manage"
    pagination_class = None


class DocumentViewSet(TenantModelViewSet):
    queryset = Document.objects.select_related("category", "employee").prefetch_related("versions")
    serializer_class = DocumentSerializer
    perm_module = "documents"
    perm_map = {"create": None, "update": "documents.upload", "partial_update": "documents.upload",
                "destroy": "documents.manage", "new_version": "documents.upload", "legal_hold": "documents.manage",
                "archive": "documents.manage", "dispose": "documents.manage", "disposal_queue": "documents.manage",
                "download": "documents.view", "acknowledge": None, "policies": None, "expiring": "documents.view"}
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    search_fields = ["title", "description", "reference_no", "tags", "employee__first_name", "employee__last_name",
                     "employee__staff_number"]
    filterset_fields = ["employee", "category", "confidentiality", "is_policy", "is_archived", "status"]

    def get_permissions(self):
        if self.action in ("acknowledge", "policies"):
            from rest_framework.permissions import IsAuthenticated

            return [IsAuthenticated()]
        return super().get_permissions()

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if self.action == "policies":
            return qs.filter(is_policy=True, is_archived=False)
        if user.is_superuser:
            return qs
        from apps.rbac.services import employee_scope_q

        q = employee_scope_q(user, "documents.view", "employee__")
        if q is None:
            return qs.none()
        qs = qs.filter(q | Q(employee__isnull=True))
        if not has_perm(user, "documents.view_confidential"):
            qs = qs.exclude(confidentiality="restricted")
        own = getattr(user, "employee", None)
        if own is not None:
            qs = qs.exclude(employee=own, visible_to_employee=False)
        return qs

    def perform_create(self, serializer):
        f = serializer.validated_data.pop("file", None)
        emp = serializer.validated_data.get("employee")
        own = getattr(self.request.user, "employee", None)
        if not has_perm(self.request.user, "documents.upload"):
            # Employees may upload supporting evidence (e.g. medical certificate) to their own file only.
            if own is None or (emp is not None and emp != own):
                raise PermissionDenied("You can only upload documents to your own file.")
            if not f:
                raise BusinessRuleError("Attach a file.")
            serializer.validated_data.update({"employee": own, "visible_to_employee": True, "is_policy": False,
                                              "requires_acknowledgment": False})
            emp = own
        elif emp and not can_access_employee(self.request.user, "documents.upload", emp):
            raise PermissionDenied("You cannot upload documents for this employee.")
        cat = serializer.validated_data["category"]
        if "confidentiality" not in self.request.data:
            serializer.validated_data["confidentiality"] = cat.default_confidentiality
        if cat.requires_expiry and not serializer.validated_data.get("expiry_date"):
            raise BusinessRuleError(f"{cat.name} documents need an expiry date.")
        doc = serializer.save()
        if f:
            services.add_version(doc, f)

    def perform_update(self, serializer):
        if serializer.instance.legal_hold:
            raise BusinessRuleError("Document is under legal hold.")
        serializer.validated_data.pop("file", None)
        serializer.save()

    def perform_destroy(self, instance):
        if instance.legal_hold:
            raise BusinessRuleError("Document is under legal hold and cannot be deleted.")
        instance.is_archived = True
        instance.save(update_fields=["is_archived"])
        audit.log("update", instance, {"archived": True})

    @action(detail=True, methods=["post"], url_path="versions")
    def new_version(self, request, pk=None):
        doc = self.get_object()
        f = request.FILES.get("file")
        if not f:
            raise BusinessRuleError("Attach a file.")
        v = services.add_version(doc, f, request.data.get("note", ""))
        return Response(VersionSerializer(v).data, status=201)

    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        doc = self.get_object()
        if not services.can_view_document(request.user, doc):
            raise PermissionDenied("You are not authorised to open this document.")
        if not doc.allow_download and not has_perm(request.user, "documents.manage"):
            raise BusinessRuleError("Download is restricted for this document.")
        version_no = request.query_params.get("version")
        version = doc.versions.filter(version=version_no).first() if version_no else doc.latest
        if version is None:
            raise BusinessRuleError("This document has no file.")
        audit.log("download", doc, {"version": version.version})
        inline = request.query_params.get("inline") == "1"
        return FileResponse(version.file.open("rb"), as_attachment=not inline, filename=version.file_name,
                            content_type=version.content_type or "application/octet-stream")

    @action(detail=True, methods=["post"])
    def acknowledge(self, request, pk=None):
        doc = Document.objects.get(pk=pk)
        if not (doc.is_policy or services.can_view_document(request.user, doc)):
            raise PermissionDenied("Not permitted.")
        DocumentAcknowledgment.objects.get_or_create(document=doc, user=request.user, version=doc.current_version)
        return Response({"detail": "Acknowledged."})

    @action(detail=False)
    def policies(self, request):
        qs = self.get_queryset()
        return Response(self.get_serializer(qs, many=True).data)

    @action(detail=True, methods=["post"])
    def legal_hold(self, request, pk=None):
        doc = self.get_object()
        doc.legal_hold = bool(request.data.get("hold", True))
        doc.legal_hold_reason = request.data.get("reason", "")
        doc.save(update_fields=["legal_hold", "legal_hold_reason", "updated_at"])
        audit.log("update", doc, {"legal_hold": doc.legal_hold, "reason": doc.legal_hold_reason})
        return Response({"detail": "Legal hold updated."})

    @action(detail=False)
    def expiring(self, request):
        days = int(request.query_params.get("days", 60))
        today = dt.date.today()
        qs = self.get_queryset().filter(expiry_date__isnull=False, expiry_date__lte=today + dt.timedelta(days=days),
                                        is_archived=False).order_by("expiry_date")
        return Response(self.get_serializer(qs[:200], many=True).data)

    @action(detail=False, url_path="disposal-queue")
    def disposal_queue(self, request):
        qs = self.get_queryset().filter(retention_until__lte=dt.date.today(), legal_hold=False)
        return Response(self.get_serializer(qs, many=True).data)

    @action(detail=True, methods=["post"])
    def dispose(self, request, pk=None):
        """Secure disposal after retention, where lawful: deletes stored files, keeps an audit stub."""
        doc = self.get_object()
        if doc.legal_hold:
            raise BusinessRuleError("Document is under legal hold.")
        if not doc.retention_until or doc.retention_until > dt.date.today():
            raise BusinessRuleError("Retention period has not ended.")
        for v in doc.versions.all():
            v.file.delete(save=False)
            v.delete()
        audit.log("delete", doc, {"disposed": True, "title": doc.title})
        doc.delete()
        return Response({"detail": "Document securely disposed."})


class LetterTemplateSerializer(TenantSerializer):
    class Meta(TenantSerializer.Meta):
        model = LetterTemplate


class LetterTemplateViewSet(TenantModelViewSet):
    queryset = LetterTemplate.objects.all()
    serializer_class = LetterTemplateSerializer
    perm_module = "documents"
    perm_read = "documents.view"
    perm_write = "documents.manage"
    perm_map = {"generate": "documents.generate", "bulk_generate": "documents.generate", "preview": "documents.generate"}
    pagination_class = None

    @action(detail=True, methods=["post"])
    def generate(self, request, pk=None):
        template = self.get_object()
        emp = Employee.objects.get(pk=request.data["employee"])
        if not can_access_employee(request.user, "documents.generate", emp):
            raise PermissionDenied("Not permitted for this employee.")
        doc = services.generate_letter(template, emp, extra=request.data.get("context") or {},
                                       reference=request.data.get("reference", ""))
        return Response(DocumentSerializer(doc, context=self.get_serializer_context()).data, status=201)

    @action(detail=True, methods=["post"])
    def bulk_generate(self, request, pk=None):
        template = self.get_object()
        ids = request.data.get("employees", [])
        docs = []
        for emp in Employee.objects.filter(pk__in=ids):
            if can_access_employee(request.user, "documents.generate", emp):
                docs.append(services.generate_letter(template, emp, extra=request.data.get("context") or {}).id)
        return Response({"generated": len(docs), "documents": docs})

    @action(detail=True, methods=["post"])
    def preview(self, request, pk=None):
        from apps.core.pdf import letter_pdf

        template = self.get_object()
        emp = Employee.objects.get(pk=request.data["employee"])
        pdf = letter_pdf(template.body_html, services.letter_context(emp, request.data.get("context") or {}))
        from django.http import HttpResponse

        return HttpResponse(pdf, content_type="application/pdf")


class LetterRequestSerializer(TenantSerializer):
    template_name = serializers.CharField(source="template.name", read_only=True)
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)

    class Meta(TenantSerializer.Meta):
        model = LetterRequest
        read_only_fields = TenantSerializer.Meta.read_only_fields + ["status", "document", "employee"]


class LetterRequestViewSet(TenantModelViewSet):
    queryset = LetterRequest.objects.select_related("template", "employee")
    serializer_class = LetterRequestSerializer
    perm_module = "documents"
    scope_prefix = "employee__"
    http_method_names = ["get"]
    filterset_fields = ["status", "employee"]


# ---------------------------------------------------------------- e-signature
class SignerSerializer(serializers.ModelSerializer):
    user_name = DisplayField("user")

    class Meta:
        model = Signer
        fields = ["id", "user", "user_name", "order", "role_label", "status", "typed_name", "signed_at",
                  "decline_reason"]


class SignatureRequestSerializer(serializers.ModelSerializer):
    signers = SignerSerializer(many=True, read_only=True)
    document_title = serializers.CharField(source="document.title", read_only=True)
    employee_name = serializers.CharField(source="document.employee.full_name", read_only=True, default=None)
    created_by_name = DisplayField("created_by")

    class Meta:
        model = SignatureRequest
        fields = ["id", "document", "document_title", "employee_name", "message", "status", "sequential", "due_date",
                  "source_version", "source_sha256", "signed_version", "completed_at", "created_at", "created_by_name",
                  "signers"]


class SignatureRequestViewSet(TenantModelViewSet):
    queryset = SignatureRequest.objects.select_related("document__employee", "created_by").prefetch_related("signers__user")
    serializer_class = SignatureRequestSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post"]
    filterset_fields = ["status", "document"]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if self.request.query_params.get("mine") == "1" or not has_perm(user, "documents.upload"):
            return qs.filter(Q(signers__user=user) | Q(created_by=user)).distinct()
        return qs

    def create(self, request, *args, **kwargs):
        from django.contrib.auth import get_user_model

        from . import esign

        if not has_perm(request.user, "documents.upload"):
            raise PermissionDenied("Only HR can send documents for signature.")
        doc = Document.objects.get(pk=request.data["document"])
        if doc.employee_id and not can_access_employee(request.user, "documents.upload", doc.employee):
            raise PermissionDenied()
        User = get_user_model()
        signers = []
        for i, s in enumerate(request.data.get("signers", []), start=1):
            if s.get("employee_self") and doc.employee_id:
                if not doc.employee.user_id:
                    raise BusinessRuleError("The employee has no user account to sign with.")
                user = doc.employee.user
            else:
                user = User.objects.get(pk=s["user"], organization=request.user.organization, is_active=True)
            signers.append({"user": user, "role_label": s.get("role_label", ""), "order": s.get("order") or i})
        req = esign.request_signatures(doc, signers, request.data.get("message", ""),
                                       bool(request.data.get("sequential", True)),
                                       dt.date.fromisoformat(request.data["due_date"]) if request.data.get("due_date") else None)
        return Response(self.get_serializer(req).data, status=201)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        req = self.get_object()
        if req.created_by_id != request.user.id and not has_perm(request.user, "documents.manage"):
            raise PermissionDenied()
        if req.status != "pending":
            raise BusinessRuleError("Only pending requests can be cancelled.")
        req.status = "cancelled"
        req.save(update_fields=["status", "updated_at"])
        audit.log("update", req, {"status": "cancelled"})
        return Response(self.get_serializer(req).data)

    @action(detail=False, url_path="my-tasks")
    def my_tasks(self, request):
        tasks = Signer.objects.filter(user=request.user).select_related("request__document")
        return Response([{"signer_id": s.id, "request": s.request_id, "document": s.request.document_id,
                          "document_title": s.request.document.title, "message": s.request.message,
                          "status": s.status, "request_status": s.request.status, "due_date": s.request.due_date,
                          "role_label": s.role_label, "signed_at": s.signed_at,
                          "signed_version": s.request.signed_version, "source_version": s.request.source_version}
                         for s in tasks.order_by("-created_at")[:100]])

    @action(detail=False, methods=["get"], url_path=r"preview/(?P<signer_id>\d+)")
    def preview(self, request, signer_id=None):
        """Signers may view the exact version they are asked to sign (even without document permissions)."""
        s = Signer.objects.select_related("request__document").get(pk=signer_id, user=request.user)
        version = s.request.document.versions.get(version=s.request.signed_version or s.request.source_version)
        audit.log("download", s.request.document, {"signature_preview": s.request_id})
        return FileResponse(version.file.open("rb"), filename=version.file_name,
                            content_type=version.content_type or "application/pdf")

    @action(detail=False, methods=["post"], url_path=r"sign/(?P<signer_id>\d+)")
    def sign(self, request, signer_id=None):
        from apps.core.middleware import client_ip

        from . import esign
        s = Signer.objects.select_related("request__document").get(pk=signer_id)
        req = esign.sign(s, request.user, request.data.get("typed_name", ""), bool(request.data.get("consent")),
                         client_ip(request), request.META.get("HTTP_USER_AGENT", ""))
        return Response(self.get_serializer(req).data)

    @action(detail=False, methods=["post"], url_path=r"decline/(?P<signer_id>\d+)")
    def decline(self, request, signer_id=None):
        from . import esign
        s = Signer.objects.get(pk=signer_id)
        req = esign.decline(s, request.user, request.data.get("reason", ""))
        return Response(self.get_serializer(req).data)
