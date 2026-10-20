"""Employee and manager self-service endpoints (/api/me/...). Everything is limited to the caller's
own record (or their reporting line for manager views)."""

import datetime as dt
import json

from django.http import HttpResponse
from django.utils import timezone
from rest_framework import serializers, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit import services as audit
from apps.core.exceptions import BusinessRuleError
from apps.documents.models import Document, LetterRequest, LetterTemplate
from apps.documents.views import DocumentSerializer, LetterRequestSerializer
from apps.employees import services as emp_services
from apps.employees.models import ACTIVE_STATUSES, Beneficiary, ChangeRequest, EmergencyContact, Employee
from apps.employees.serializers import (
    BeneficiarySerializer,
    ChangeRequestSerializer,
    EmergencyContactSerializer,
    EmployeeSerializer,
)
from apps.leave.services import all_balances, on_leave_on


def me(request):
    emp = getattr(request.user, "employee", None)
    if emp is None:
        raise BusinessRuleError("Your account is not linked to an employee record. Contact HR.")
    return emp


class ProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        emp = me(request)
        data = EmployeeSerializer(emp, context={"request": request}).data
        data["emergency_contacts"] = EmergencyContactSerializer(emp.emergency_contacts.all(), many=True).data
        data["beneficiaries"] = BeneficiarySerializer(emp.beneficiaries.all(), many=True).data
        data["bank_accounts"] = [{"payment_method": b.payment_method, "bank_name": b.bank_name or b.momo_network,
                                  "account": "****" + (b.account_last4 or b.momo_number[-4:]),
                                  "is_primary": b.is_primary} for b in emp.bank_accounts.all()]
        data["qualifications"] = list(emp.qualifications.values("level", "title", "institution", "year_obtained"))
        data["editable_fields"] = ChangeRequest.ALLOWED_FIELDS
        return Response(data)


class SummaryView(APIView):
    """Landing-page summary for the employee portal."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.attendance.services import scheduled_shift
        from apps.notifications.models import Announcement
        from apps.payroll.models import Payslip
        from apps.workflow.models import WorkflowInstance, WorkflowTask

        emp = getattr(request.user, "employee", None)
        out = {"pending_tasks": WorkflowTask.objects.filter(assignee=request.user, status="pending",
                                                            instance__status="in_progress").count()}
        if emp is None:
            return Response(out)
        today = dt.date.today()
        shift, _, _ = scheduled_shift(emp, today)
        last_slip = (Payslip.objects.filter(employee=emp, published_at__isnull=False)
                     .exclude(run__run_type="reversal").order_by("-run__period__end_date").first())
        open_requests = WorkflowInstance.objects.filter(initiator=request.user, status__in=["in_progress", "returned"])
        out.update({
            "employee": {"id": emp.id, "name": emp.full_name, "staff_number": emp.staff_number,
                         "job_title": emp.job_title.name if emp.job_title_id else None,
                         "department": emp.department.name if emp.department_id else None,
                         "supervisor": emp.supervisor.full_name if emp.supervisor_id else None,
                         "hire_date": emp.hire_date, "status": emp.status},
            "leave_balances": [b for b in all_balances(emp, today.year) if b["tracks_balance"]],
            "today_shift": str(shift) if shift else None,
            "last_payslip": {"id": last_slip.id, "period": last_slip.run.period.name, "net_pay": last_slip.net_pay}
            if last_slip else None,
            "open_requests": [{"id": i.id, "title": i.title, "status": i.status,
                               "waiting_on": [str(t.assignee) for t in i.tasks.filter(status="pending")]}
                              for i in open_requests[:10]],
            "unacknowledged_policies": Document.objects.filter(is_policy=True, requires_acknowledgment=True,
                                                               is_archived=False)
            .exclude(acknowledgments__user=request.user).count(),
            "announcements": Announcement.objects.filter(publish_at__lte=timezone.now()).count(),
            "is_manager": emp.direct_reports.exists(),
        })
        return Response(out)


class ChangeRequestViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def list(self, request):
        qs = ChangeRequest.objects.filter(employee=me(request))
        return Response(ChangeRequestSerializer(qs, many=True).data)

    def create(self, request):
        emp = me(request)
        changes = request.data.get("changes") or {}
        cr = emp_services.submit_change_request(emp, changes, request.data.get("reason", ""), request.user)
        return Response(ChangeRequestSerializer(cr).data, status=201)


class OwnRecordViewSet(viewsets.ModelViewSet):
    """Employees maintain their own emergency contacts / beneficiaries directly where policy permits."""

    permission_classes = [IsAuthenticated]
    model = None

    def get_queryset(self):
        return self.model.objects.filter(employee=me(self.request))

    def _allowed(self):
        org = self.request.user.organization
        if not org.settings.get("ess_direct_contact_updates", True):
            raise BusinessRuleError("Submit a change request to HR to update these details.")

    def perform_create(self, serializer):
        self._allowed()
        serializer.save(employee=me(self.request))

    def perform_update(self, serializer):
        self._allowed()
        serializer.save(employee=me(self.request))

    def perform_destroy(self, instance):
        self._allowed()
        instance.delete()


class OwnEmergencyContactSerializer(EmergencyContactSerializer):
    class Meta(EmergencyContactSerializer.Meta):
        read_only_fields = EmergencyContactSerializer.Meta.read_only_fields + ["employee"]


class OwnBeneficiarySerializer(BeneficiarySerializer):
    class Meta(BeneficiarySerializer.Meta):
        read_only_fields = BeneficiarySerializer.Meta.read_only_fields + ["employee"]


class EmergencyContactViewSet(OwnRecordViewSet):
    model = EmergencyContact
    serializer_class = OwnEmergencyContactSerializer


class BeneficiaryViewSet(OwnRecordViewSet):
    model = Beneficiary
    serializer_class = OwnBeneficiarySerializer


class MyDocumentsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        emp = me(request)
        docs = Document.objects.filter(employee=emp, visible_to_employee=True, is_archived=False).exclude(
            confidentiality="restricted").select_related("category").prefetch_related("versions")
        return Response(DocumentSerializer(docs, many=True, context={"request": request}).data)


class LetterRequestCreateSerializer(serializers.Serializer):
    template = serializers.PrimaryKeyRelatedField(queryset=LetterTemplate.objects)
    addressed_to = serializers.CharField(required=False, allow_blank=True, default="")
    purpose = serializers.CharField(required=False, allow_blank=True, default="")


class MyLettersView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        emp = me(request)
        return Response({
            "templates": list(LetterTemplate.objects.filter(self_service=True, is_active=True)
                              .values("id", "name", "letter_type")),
            "requests": LetterRequestSerializer(LetterRequest.objects.filter(employee=emp).select_related("template"),
                                                many=True).data})

    def post(self, request):
        from apps.documents.services import generate_letter
        from apps.workflow import engine

        emp = me(request)
        s = LetterRequestCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        tpl = s.validated_data["template"]
        if not tpl.self_service or not tpl.is_active:
            raise BusinessRuleError("This letter cannot be requested through self-service.")
        req = LetterRequest.objects.create(employee=emp, template=tpl, addressed_to=s.validated_data["addressed_to"],
                                           purpose=s.validated_data["purpose"])
        if tpl.requires_approval:
            engine.start(req, "letter_request", request.user, subject_employee=emp)
        else:
            doc = generate_letter(tpl, emp, extra={"addressed_to": req.addressed_to, "purpose": req.purpose},
                                  reference=f"HR/LTR/{req.pk:05d}")
            req.document, req.status = doc, "issued"
            req.save(update_fields=["document", "status"])
        return Response(LetterRequestSerializer(req).data, status=201)


class MyTeamView(APIView):
    """Manager self-service: team list with today's status and pending approvals."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.rbac.services import team_member_ids
        from apps.workflow.models import WorkflowTask

        emp = me(request)
        direct_only = request.query_params.get("direct") == "1"
        ids = list(emp.direct_reports.values_list("id", flat=True)) if direct_only else team_member_ids(emp)
        team = Employee.objects.filter(id__in=ids, status__in=ACTIVE_STATUSES).select_related("job_title", "department")
        today = dt.date.today()
        away = {r.employee_id: r for r in on_leave_on(today).filter(employee__in=team).select_related("leave_type")}
        return Response({
            "members": [{"id": e.id, "name": e.full_name, "staff_number": e.staff_number,
                         "job_title": e.job_title.name if e.job_title_id else None,
                         "is_direct": e.supervisor_id == emp.id, "status": e.status,
                         "on_leave": away[e.id].leave_type.name if e.id in away else None,
                         "probation_end_date": e.probation_end_date if e.status == "probation" else None,
                         "contract_end_date": e.contract_end_date} for e in team],
            "pending_approvals": WorkflowTask.objects.filter(assignee=request.user, status="pending",
                                                             instance__status="in_progress").count(),
        })


class MyDataExportView(APIView):
    """Data Protection Act 843: data subject access - download a copy of my personal data."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        emp = me(request)
        data = EmployeeSerializer(emp, context={"request": request}).data
        data["employment_history"] = list(emp.employment_records.values(
            "event_type", "effective_from", "effective_to", "department__name", "job_title__name", "grade__code"))
        data["emergency_contacts"] = list(emp.emergency_contacts.values("name", "relationship", "phone"))
        data["beneficiaries"] = list(emp.beneficiaries.values("name", "relationship", "percentage"))
        data["qualifications"] = list(emp.qualifications.values("title", "institution", "year_obtained"))
        data["leave_requests"] = list(emp.leave_requests.values("leave_type__name", "start_date", "end_date", "days",
                                                                "status"))
        data["consents"] = list(emp.consents.values("purpose", "lawful_basis", "granted", "granted_at", "withdrawn_at"))
        audit.log("export", emp, {"subject_access_request": True})
        resp = HttpResponse(json.dumps(data, default=str, indent=2), content_type="application/json")
        resp["Content-Disposition"] = f'attachment; filename="my-data-{emp.staff_number}.json"'
        return resp
