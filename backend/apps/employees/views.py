from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from apps.audit import services as audit
from apps.core.exceptions import BusinessRuleError
from apps.core.exports import file_response, tabular_response
from apps.core.views import TenantModelViewSet
from apps.rbac.models import Role, RoleAssignment
from apps.rbac.services import can_access_employee, has_perm

from . import importer, services
from .models import (
    BankAccount,
    Beneficiary,
    ChangeRequest,
    ConcurrentAssignment,
    Contract,
    DataConsent,
    EmergencyContact,
    Employee,
    EmployeeCategory,
    Qualification,
)
from .serializers import (
    BankAccountSerializer,
    BeneficiarySerializer,
    CategorySerializer,
    ChangeRequestSerializer,
    ConcurrentAssignmentSerializer,
    ContractSerializer,
    DataConsentSerializer,
    EmergencyContactSerializer,
    EmployeeCreateSerializer,
    EmployeeListSerializer,
    EmployeeSerializer,
    EmployeeUpdateSerializer,
    EmploymentRecordSerializer,
    PersonnelActionSerializer,
    QualificationSerializer,
    SeparationSerializer,
)


class EmployeeViewSet(TenantModelViewSet):
    queryset = Employee.objects.select_related("department", "job_title", "grade", "branch", "supervisor",
                                               "location", "position", "category")
    perm_module = "employees"
    scope_prefix = ""
    search_fields = ["first_name", "last_name", "middle_name", "staff_number", "work_email", "phone",
                     "job_title__name", "department__name"]
    filterset_fields = ["department", "branch", "location", "grade", "job_title", "status", "employment_type",
                        "category", "supervisor", "gender"]
    ordering_fields = ["last_name", "staff_number", "hire_date", "department__name"]
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    perm_map = {
        "personnel_action": "employees.change", "separate": "employees.change", "rehire": "employees.create",
        "confirm": "employees.change", "extend_probation": "employees.change", "create_account": "admin.users",
        "import_employees": "employees.import", "import_template": "employees.import",
        "export": "employees.export", "data_quality": "employees.view", "check_duplicates": "employees.create",
        "history": "employees.view", "as_of": "employees.view",
    }

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get("include_exited") != "1" and self.action == "list" and \
                "status" not in self.request.query_params:
            qs = qs.exclude(status="exited")
        return qs

    def get_serializer_class(self):
        if self.action == "list":
            return EmployeeListSerializer
        if self.action == "create":
            return EmployeeCreateSerializer
        if self.action in ("update", "partial_update"):
            return EmployeeUpdateSerializer
        return EmployeeSerializer

    def retrieve(self, request, *args, **kwargs):
        emp = self.get_object()
        if has_perm(request.user, "employees.view_personal") and getattr(request.user, "employee", None) != emp:
            audit.log("view", emp, {"record": "employee profile"})
        return Response(self.get_serializer(emp).data)

    def create(self, request, *args, **kwargs):
        s = self.get_serializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = dict(s.validated_data)
        allow = data.pop("allow_duplicate", False)
        emp = services.hire(data, user=request.user, allow_duplicate=allow)
        return Response(EmployeeSerializer(emp, context=self.get_serializer_context()).data, status=201)

    def perform_destroy(self, instance):
        if instance.payslips.exists() or instance.employment_records.count() > 1:
            raise BusinessRuleError("Employees with history cannot be deleted. Record a separation instead.")
        instance.delete()

    # ---------------------------------------------------------------- lifecycle
    @action(detail=True, methods=["get"])
    def history(self, request, pk=None):
        emp = self.get_object()
        records = emp.employment_records.select_related("department", "job_title", "grade", "supervisor",
                                                        "approved_by").order_by("-effective_from", "-id")
        return Response(EmploymentRecordSerializer(records, many=True, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["get"])
    def as_of(self, request, pk=None):
        import datetime as dt

        emp = self.get_object()
        date = dt.date.fromisoformat(request.query_params.get("date", dt.date.today().isoformat()))
        rec = services.as_of(emp, date)
        return Response(EmploymentRecordSerializer(rec, context=self.get_serializer_context()).data if rec else None)

    @action(detail=True, methods=["post"])
    def personnel_action(self, request, pk=None):
        emp = self.get_object()
        s = PersonnelActionSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = dict(s.validated_data)
        event, eff = d.pop("event_type"), d.pop("effective_from")
        reason, ref = d.pop("reason", ""), d.pop("reference", "")
        if "basic_salary" in d and not has_perm(request.user, "employees.view_salary"):
            raise PermissionDenied("You are not authorised to change salaries.")
        record = services.apply_change(emp, event, eff, d, reason=reason, reference=ref, user=request.user)
        return Response(EmploymentRecordSerializer(record, context=self.get_serializer_context()).data, status=201)

    @action(detail=True, methods=["post"])
    def confirm(self, request, pk=None):
        import datetime as dt

        emp = self.get_object()
        eff = dt.date.fromisoformat(request.data.get("effective_from") or dt.date.today().isoformat())
        services.confirm_appointment(emp, eff, user=request.user, reason=request.data.get("reason") or
                                     "Confirmed after satisfactory probation")
        return Response({"detail": "Appointment confirmed."})

    @action(detail=True, methods=["post"])
    def extend_probation(self, request, pk=None):
        import datetime as dt

        emp = self.get_object()
        new_end = dt.date.fromisoformat(request.data["new_end_date"])
        services.extend_probation(emp, new_end, request.user, request.data.get("reason", ""))
        return Response({"detail": "Probation extended."})

    @action(detail=True, methods=["post"])
    def separate(self, request, pk=None):
        emp = self.get_object()
        s = SeparationSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        services.separate(emp, user=request.user, **s.validated_data)
        return Response({"detail": "Separation recorded."})

    @action(detail=True, methods=["post"])
    def rehire(self, request, pk=None):
        import datetime as dt

        prev = Employee.objects.get(pk=pk)
        if not can_access_employee(request.user, "employees.create", prev):
            raise PermissionDenied("Not permitted.")
        data = {}
        fk_fields = {"department": "organization.Department", "job_title": "organization.JobTitle",
                     "grade": "organization.Grade", "position": "organization.Position",
                     "supervisor": "employees.Employee", "branch": "organization.Branch"}
        from django.apps import apps

        for f, label in fk_fields.items():
            if request.data.get(f):
                data[f] = apps.get_model(label).objects.get(pk=request.data[f])
        for f in ("employment_type", "basic_salary", "work_email"):
            if request.data.get(f):
                data[f] = request.data[f]
        new = services.rehire(prev, dt.date.fromisoformat(request.data["hire_date"]), data, user=request.user)
        return Response(EmployeeSerializer(new, context=self.get_serializer_context()).data, status=201)

    @action(detail=True, methods=["post"])
    def create_account(self, request, pk=None):
        from apps.accounts.admin_views import create_user_account

        emp = self.get_object()
        if emp.user_id:
            raise BusinessRuleError("This employee already has a user account.")
        email = emp.work_email or emp.personal_email
        username = request.data.get("username") or (email.split("@")[0] if email else emp.staff_number.lower())
        user, _ = create_user_account(username, email, emp.first_name, emp.last_name, emp.phone)
        emp.user = user
        emp.save(update_fields=["user"])
        role = Role.objects.filter(code="employee").first()
        if role:
            RoleAssignment.objects.create(user=user, role=role, approved_by=request.user)
        if emp.direct_reports.exists():
            mgr = Role.objects.filter(code="line_manager").first()
            if mgr:
                RoleAssignment.objects.create(user=user, role=mgr, approved_by=request.user)
        return Response({"detail": f"Account '{username}' created and credentials sent.", "user_id": user.id})

    # ---------------------------------------------------------------- data management
    @action(detail=False, methods=["post"], url_path="check-duplicates")
    def check_duplicates(self, request):
        import datetime as dt

        dob = request.data.get("date_of_birth")
        dups = services.find_duplicates(request.data.get("first_name", ""), request.data.get("last_name", ""),
                                        dt.date.fromisoformat(dob) if dob else None,
                                        request.data.get("ghana_card_no", ""), request.data.get("ssnit_number", ""),
                                        request.data.get("exclude_id"))
        return Response(EmployeeListSerializer(dups[:10], many=True, context=self.get_serializer_context()).data)

    @action(detail=False, methods=["get"], url_path="import-template")
    def import_template(self, request):
        return file_response(importer.template_bytes(), "employee-import-template.xlsx",
                             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    @action(detail=False, methods=["post"], url_path="import")
    def import_employees(self, request):
        f = request.FILES.get("file")
        if not f:
            raise BusinessRuleError("Upload an .xlsx file.")
        dry_run = str(request.data.get("dry_run", "true")).lower() != "false"
        result = importer.run_import(f, request.user, dry_run=dry_run)
        if not dry_run and result.get("created"):
            audit.log("create", None, {"bulk_import": result["created"]}, object_repr="Employee bulk import")
        return Response(result, status=200 if result["ok"] else 400)

    @action(detail=False, methods=["get"])
    def export(self, request):
        qs = self.filter_queryset(self.get_queryset())
        show_personal = has_perm(request.user, "employees.view_personal", "organization")
        show_salary = has_perm(request.user, "employees.view_salary", "organization")
        headers = ["Staff No", "Title", "First name", "Middle name", "Last name", "Gender", "Department", "Job title",
                   "Grade", "Branch", "Employment type", "Status", "Hire date", "Supervisor", "Work email", "Phone"]
        if show_personal:
            headers += ["Date of birth", "Ghana Card", "SSNIT No", "TIN"]
        if show_salary:
            headers += ["Basic salary"]
        rows = []
        for e in qs:
            row = [e.staff_number, e.get_title_display(), e.first_name, e.middle_name, e.last_name, e.gender,
                   e.department.name if e.department_id else "", e.job_title.name if e.job_title_id else "",
                   e.grade.code if e.grade_id else "", e.branch.name if e.branch_id else "", e.employment_type,
                   e.status, e.hire_date.strftime("%d/%m/%Y"), e.supervisor.full_name if e.supervisor_id else "",
                   e.work_email, e.phone]
            if show_personal:
                row += [e.date_of_birth.strftime("%d/%m/%Y") if e.date_of_birth else "", e.ghana_card_no,
                        e.ssnit_number, e.tin]
            if show_salary:
                row += [e.basic_salary]
            rows.append(row)
        audit.log("export", None, {"rows": len(rows), "personal": show_personal, "salary": show_salary},
                  object_repr="Employee export")
        return tabular_response(headers, rows, "employees", request.query_params.get("format", "xlsx"), "Employees")

    @action(detail=False, methods=["get"], url_path="data-quality")
    def data_quality(self, request):
        if not has_perm(request.user, "employees.view", "organization"):
            raise PermissionDenied("Organization-wide access is required.")
        return Response(services.data_quality_report())


class EmployeeChildViewSet(TenantModelViewSet):
    """Base for records belonging to an employee: scoped by the employee's data scope."""

    perm_module = "employees"
    perm_write = "employees.change"
    scope_prefix = "employee__"
    filterset_fields = ["employee"]

    def perform_create(self, serializer):
        emp = serializer.validated_data.get("employee")
        if emp and not can_access_employee(self.request.user, "employees.change", emp):
            raise PermissionDenied("You cannot modify records for this employee.")
        serializer.save()


class CategoryViewSet(TenantModelViewSet):
    queryset = EmployeeCategory.objects.all()
    serializer_class = CategorySerializer
    perm_module = "organization"
    perm_write = "organization.manage"
    pagination_class = None


class ContractViewSet(EmployeeChildViewSet):
    queryset = Contract.objects.select_related("employee")
    serializer_class = ContractSerializer
    filterset_fields = ["employee", "status", "contract_type"]

    def perform_create(self, serializer):
        super().perform_create(serializer)
        c = serializer.instance
        if c.end_date and c.status == "active":
            Employee.objects.filter(pk=c.employee_id).update(contract_end_date=c.end_date)


class EmergencyContactViewSet(EmployeeChildViewSet):
    queryset = EmergencyContact.objects.all()
    serializer_class = EmergencyContactSerializer
    pagination_class = None


class BeneficiaryViewSet(EmployeeChildViewSet):
    queryset = Beneficiary.objects.all()
    serializer_class = BeneficiarySerializer
    pagination_class = None


class BankAccountViewSet(EmployeeChildViewSet):
    queryset = BankAccount.objects.all()
    serializer_class = BankAccountSerializer
    perm_read = "employees.view"
    perm_write = "employees.view_bank"
    pagination_class = None

    def get_queryset(self):
        # bank details: only for users with view_bank in scope
        from apps.rbac.services import scope_queryset

        return scope_queryset(self.request.user, super().get_queryset(), "employees.view_bank", "employee__")

    def perform_create(self, serializer):
        emp = serializer.validated_data["employee"]
        if not can_access_employee(self.request.user, "employees.view_bank", emp) or \
                not has_perm(self.request.user, "payroll.prepare") and not has_perm(self.request.user, "employees.change"):
            raise PermissionDenied("You cannot change bank details for this employee.")
        if serializer.validated_data.get("is_primary", True):
            BankAccount.objects.filter(employee=emp, is_primary=True).update(is_primary=False)
        serializer.save()


class QualificationViewSet(EmployeeChildViewSet):
    queryset = Qualification.objects.all()
    serializer_class = QualificationSerializer
    pagination_class = None


class ConcurrentAssignmentViewSet(EmployeeChildViewSet):
    queryset = ConcurrentAssignment.objects.select_related("position__job_title")
    serializer_class = ConcurrentAssignmentSerializer
    pagination_class = None


class ChangeRequestViewSet(TenantModelViewSet):
    """HR view of change requests (approval happens in the workflow inbox)."""

    queryset = ChangeRequest.objects.select_related("employee")
    serializer_class = ChangeRequestSerializer
    perm_module = "employees"
    scope_prefix = "employee__"
    http_method_names = ["get"]
    filterset_fields = ["status", "employee"]


class DataConsentViewSet(EmployeeChildViewSet):
    queryset = DataConsent.objects.all()
    serializer_class = DataConsentSerializer
    pagination_class = None

    @action(detail=True, methods=["post"])
    def withdraw(self, request, pk=None):
        from django.utils import timezone

        c = self.get_object()
        c.granted = False
        c.withdrawn_at = timezone.now()
        c.save(update_fields=["granted", "withdrawn_at", "updated_at"])
        return Response({"detail": "Consent withdrawn."})


class DirectorySerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)
    department_name = serializers.CharField(source="department.name", read_only=True, default=None)
    job_title_name = serializers.CharField(source="job_title.name", read_only=True, default=None)
    location_name = serializers.CharField(source="location.name", read_only=True, default=None)

    class Meta:
        model = Employee
        fields = ["id", "staff_number", "full_name", "job_title_name", "department_name", "location_name",
                  "work_email", "photo"]


class DirectoryViewSet(TenantModelViewSet):
    """Staff directory visible to every employee: only non-sensitive contact fields."""

    queryset = Employee.objects.exclude(status="exited").select_related("department", "job_title", "location")
    serializer_class = DirectorySerializer
    http_method_names = ["get"]
    search_fields = ["first_name", "last_name", "staff_number", "job_title__name", "department__name"]
    filterset_fields = ["department", "location", "branch"]

    def get_permissions(self):
        from rest_framework.permissions import IsAuthenticated

        return [IsAuthenticated()]


