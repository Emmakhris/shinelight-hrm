from rest_framework import serializers

from apps.core.serializers import DisplayField, SensitiveFieldsMixin, TenantSerializer

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
    EmploymentRecord,
    Qualification,
)

PERSONAL = "employees.view_personal"
SALARY = "employees.view_salary"
BANK = "employees.view_bank"


class EmployeeListSerializer(SensitiveFieldsMixin, serializers.ModelSerializer):
    employee_attr = ""
    full_name = serializers.CharField(read_only=True)
    department_name = serializers.CharField(source="department.name", read_only=True, default=None)
    job_title_name = serializers.CharField(source="job_title.name", read_only=True, default=None)
    grade_code = serializers.CharField(source="grade.code", read_only=True, default=None)
    branch_name = serializers.CharField(source="branch.name", read_only=True, default=None)
    supervisor_name = serializers.CharField(source="supervisor.full_name", read_only=True, default=None)

    class Meta:
        model = Employee
        fields = ["id", "staff_number", "full_name", "first_name", "last_name", "work_email", "phone", "photo",
                  "department", "department_name", "job_title", "job_title_name", "grade", "grade_code", "branch",
                  "branch_name", "supervisor", "supervisor_name", "employment_type", "status", "hire_date",
                  "contract_end_date", "probation_end_date"]


class EmployeeSerializer(SensitiveFieldsMixin, TenantSerializer):
    employee_attr = ""
    sensitive_fields = {
        "ghana_card_no": (PERSONAL, "mask"), "ssnit_number": (PERSONAL, "mask"), "tin": (PERSONAL, "mask"),
        "passport_no": (PERSONAL, "mask"), "date_of_birth": PERSONAL, "residential_address": PERSONAL,
        "basic_salary": SALARY, "custom_fields": PERSONAL, "marital_status": PERSONAL,
    }
    full_name = serializers.CharField(read_only=True)
    department_name = serializers.CharField(source="department.name", read_only=True, default=None)
    job_title_name = serializers.CharField(source="job_title.name", read_only=True, default=None)
    grade_code = serializers.CharField(source="grade.code", read_only=True, default=None)
    branch_name = serializers.CharField(source="branch.name", read_only=True, default=None)
    location_name = serializers.CharField(source="location.name", read_only=True, default=None)
    position_code = serializers.CharField(source="position.code", read_only=True, default=None)
    supervisor_name = serializers.CharField(source="supervisor.full_name", read_only=True, default=None)
    category_name = serializers.CharField(source="category.name", read_only=True, default=None)
    has_account = serializers.SerializerMethodField()
    years_of_service = serializers.SerializerMethodField()

    class Meta(TenantSerializer.Meta):
        model = Employee
        exclude = ["organization"]
        read_only_fields = TenantSerializer.Meta.read_only_fields + [
            "user", "status", "exit_date", "exit_reason", "original_hire_date", "previous_record",
            "confirmation_date", "retirement_date"]

    def get_has_account(self, obj):
        return bool(obj.user_id)

    def get_years_of_service(self, obj):
        import datetime as dt

        start = obj.original_hire_date or obj.hire_date
        end = obj.exit_date or dt.date.today()
        return round((end - start).days / 365.25, 1)


class EmployeeCreateSerializer(EmployeeSerializer):
    allow_duplicate = serializers.BooleanField(write_only=True, default=False)
    staff_number = serializers.CharField(required=False, allow_blank=True)

    class Meta(EmployeeSerializer.Meta):
        pass


# Snapshot fields change only through personnel actions (effective-dated history).
EMPLOYMENT_FIELDS = ["department", "branch", "location", "position", "job_title", "grade", "grade_step",
                     "cost_center", "supervisor", "category", "employment_type", "basic_salary", "hire_date"]


class EmployeeUpdateSerializer(EmployeeSerializer):
    class Meta(EmployeeSerializer.Meta):
        read_only_fields = EmployeeSerializer.Meta.read_only_fields + EMPLOYMENT_FIELDS


class EmploymentRecordSerializer(SensitiveFieldsMixin, TenantSerializer):
    sensitive_fields = {"basic_salary": SALARY}
    event_label = serializers.CharField(source="get_event_type_display", read_only=True)
    department_name = serializers.CharField(source="department.name", read_only=True, default=None)
    job_title_name = serializers.CharField(source="job_title.name", read_only=True, default=None)
    grade_code = serializers.CharField(source="grade.code", read_only=True, default=None)
    supervisor_name = serializers.CharField(source="supervisor.full_name", read_only=True, default=None)
    approved_by_name = DisplayField("approved_by")

    class Meta(TenantSerializer.Meta):
        model = EmploymentRecord


class PersonnelActionSerializer(serializers.Serializer):
    event_type = serializers.ChoiceField(choices=[c for c, _ in EmploymentRecord.EVENTS
                                                  if c not in ("hire", "rehire", "exit")])
    effective_from = serializers.DateField()
    reason = serializers.CharField(allow_blank=True, required=False, default="")
    reference = serializers.CharField(allow_blank=True, required=False, default="")
    department = serializers.PrimaryKeyRelatedField(queryset=EmploymentRecord._meta.get_field("department")
                                                    .related_model.objects, required=False, allow_null=True)
    branch = serializers.PrimaryKeyRelatedField(queryset=EmploymentRecord._meta.get_field("branch")
                                                .related_model.objects, required=False, allow_null=True)
    location = serializers.PrimaryKeyRelatedField(queryset=EmploymentRecord._meta.get_field("location")
                                                  .related_model.objects, required=False, allow_null=True)
    position = serializers.PrimaryKeyRelatedField(queryset=EmploymentRecord._meta.get_field("position")
                                                  .related_model.objects, required=False, allow_null=True)
    job_title = serializers.PrimaryKeyRelatedField(queryset=EmploymentRecord._meta.get_field("job_title")
                                                   .related_model.objects, required=False, allow_null=True)
    grade = serializers.PrimaryKeyRelatedField(queryset=EmploymentRecord._meta.get_field("grade")
                                               .related_model.objects, required=False, allow_null=True)
    grade_step = serializers.PrimaryKeyRelatedField(queryset=EmploymentRecord._meta.get_field("grade_step")
                                                    .related_model.objects, required=False, allow_null=True)
    cost_center = serializers.PrimaryKeyRelatedField(queryset=EmploymentRecord._meta.get_field("cost_center")
                                                     .related_model.objects, required=False, allow_null=True)
    supervisor = serializers.PrimaryKeyRelatedField(queryset=Employee.objects, required=False, allow_null=True)
    category = serializers.PrimaryKeyRelatedField(queryset=EmployeeCategory.objects, required=False,
                                                  allow_null=True)
    employment_type = serializers.CharField(required=False)
    status = serializers.ChoiceField(choices=[c for c, _ in Employee.STATUS if c != "exited"], required=False)
    basic_salary = serializers.DecimalField(max_digits=14, decimal_places=2, required=False)


class SeparationSerializer(serializers.Serializer):
    REASONS = [("resignation", "Resignation"), ("retirement", "Retirement"), ("contract_end", "End of contract"),
               ("termination", "Termination"), ("dismissal", "Dismissal"), ("redundancy", "Redundancy"),
               ("death", "Death"), ("abandonment", "Vacation of post"), ("other", "Other")]
    exit_date = serializers.DateField()
    reason = serializers.ChoiceField(choices=REASONS)
    notes = serializers.CharField(allow_blank=True, required=False, default="")
    rehire_eligible = serializers.BooleanField(default=True)


class CategorySerializer(TenantSerializer):
    class Meta(TenantSerializer.Meta):
        model = EmployeeCategory


class ContractSerializer(TenantSerializer):
    contract_type_label = serializers.CharField(source="get_contract_type_display", read_only=True)

    class Meta(TenantSerializer.Meta):
        model = Contract


class EmergencyContactSerializer(TenantSerializer):
    class Meta(TenantSerializer.Meta):
        model = EmergencyContact


class BeneficiarySerializer(TenantSerializer):
    class Meta(TenantSerializer.Meta):
        model = Beneficiary


class BankAccountSerializer(SensitiveFieldsMixin, TenantSerializer):
    sensitive_fields = {"account_number": (BANK, "mask"), "momo_number": (BANK, "mask")}

    class Meta(TenantSerializer.Meta):
        model = BankAccount
        read_only_fields = TenantSerializer.Meta.read_only_fields + ["account_last4", "verified"]

    def validate(self, attrs):
        method = attrs.get("payment_method", getattr(self.instance, "payment_method", "bank"))
        if method == "bank" and not (attrs.get("account_number") or getattr(self.instance, "account_number", "")):
            raise serializers.ValidationError({"account_number": "Account number is required for bank transfers."})
        if method == "momo" and not (attrs.get("momo_number") or getattr(self.instance, "momo_number", "")):
            raise serializers.ValidationError({"momo_number": "Mobile money number is required."})
        return attrs


class QualificationSerializer(TenantSerializer):
    class Meta(TenantSerializer.Meta):
        model = Qualification


class ConcurrentAssignmentSerializer(SensitiveFieldsMixin, TenantSerializer):
    sensitive_fields = {"allowance_amount": SALARY}
    position_label = DisplayField("position")

    class Meta(TenantSerializer.Meta):
        model = ConcurrentAssignment


class ChangeRequestSerializer(TenantSerializer):
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)

    class Meta(TenantSerializer.Meta):
        model = ChangeRequest
        read_only_fields = TenantSerializer.Meta.read_only_fields + ["status", "previous", "applied_at", "employee"]


class DataConsentSerializer(TenantSerializer):
    class Meta(TenantSerializer.Meta):
        model = DataConsent
        read_only_fields = TenantSerializer.Meta.read_only_fields + ["granted_at"]
