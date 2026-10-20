from decimal import Decimal

from django.conf import settings
from django.db import models

from apps.core.fields import EncryptedCharField
from apps.core.models import TenantModel
from apps.core.validators import validate_gh_phone, validate_ghana_card, validate_ssnit
from apps.organization.models import Position

ACTIVE_STATUSES = ["active", "probation", "suspended", "on_leave"]


class EmployeeCategory(TenantModel):
    """Configurable categories (e.g. Management, Senior Staff, Junior Staff, Clinical) used by policies."""

    code = models.SlugField(max_length=30)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    class Meta:
        unique_together = [("organization", "code")]
        ordering = ["name"]
        verbose_name_plural = "employee categories"

    def __str__(self):
        return self.name


class Employee(TenantModel):
    """Single source of truth for an employee. Current-state fields are a denormalised snapshot
    of the latest effective EmploymentRecord (history lives in EmploymentRecord)."""

    TITLES = [("mr", "Mr"), ("mrs", "Mrs"), ("ms", "Ms"), ("miss", "Miss"), ("dr", "Dr"), ("prof", "Prof"),
              ("rev", "Rev"), ("hon", "Hon")]
    GENDERS = [("male", "Male"), ("female", "Female")]
    MARITAL = [("single", "Single"), ("married", "Married"), ("divorced", "Divorced"), ("widowed", "Widowed"),
               ("separated", "Separated")]
    STATUS = [
        ("active", "Active"),
        ("probation", "On probation"),
        ("suspended", "Suspended"),
        ("on_leave", "On extended leave"),
        ("exited", "Exited"),
    ]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                related_name="employee")
    staff_number = models.CharField(max_length=30)
    # personal
    title = models.CharField(max_length=10, choices=TITLES, blank=True)
    first_name = models.CharField(max_length=80)
    middle_name = models.CharField(max_length=80, blank=True)
    last_name = models.CharField(max_length=80)
    preferred_name = models.CharField(max_length=80, blank=True)
    gender = models.CharField(max_length=10, choices=GENDERS, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    marital_status = models.CharField(max_length=12, choices=MARITAL, blank=True)
    nationality = models.CharField(max_length=60, default="Ghanaian")
    ghana_card_no = models.CharField("Ghana Card PIN", max_length=20, blank=True, validators=[validate_ghana_card])
    ssnit_number = models.CharField(max_length=20, blank=True, validators=[validate_ssnit])
    tin = models.CharField("TIN", max_length=20, blank=True)
    passport_no = models.CharField(max_length=30, blank=True)
    hometown = models.CharField(max_length=80, blank=True)
    region_of_origin = models.CharField(max_length=60, blank=True)
    # contact
    work_email = models.EmailField(blank=True)
    personal_email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True, validators=[validate_gh_phone])
    alt_phone = models.CharField(max_length=20, blank=True)
    residential_address = models.TextField(blank=True)
    digital_address = models.CharField("Ghana Post GPS address", max_length=20, blank=True)
    photo = models.ImageField(upload_to="employees/photos/", null=True, blank=True)
    # current employment snapshot
    department = models.ForeignKey("organization.Department", null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="employees")
    branch = models.ForeignKey("organization.Branch", null=True, blank=True, on_delete=models.SET_NULL,
                               related_name="employees")
    location = models.ForeignKey("organization.Location", null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name="employees")
    position = models.ForeignKey(Position, null=True, blank=True, on_delete=models.SET_NULL, related_name="employees")
    job_title = models.ForeignKey("organization.JobTitle", null=True, blank=True, on_delete=models.SET_NULL,
                                  related_name="employees")
    grade = models.ForeignKey("organization.Grade", null=True, blank=True, on_delete=models.SET_NULL,
                              related_name="employees")
    grade_step = models.ForeignKey("organization.GradeStep", null=True, blank=True, on_delete=models.SET_NULL)
    cost_center = models.ForeignKey("organization.CostCenter", null=True, blank=True, on_delete=models.SET_NULL)
    supervisor = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="direct_reports")
    category = models.ForeignKey(EmployeeCategory, null=True, blank=True, on_delete=models.SET_NULL)
    employment_type = models.CharField(max_length=20, choices=Position.EMPLOYMENT_TYPES, default="permanent")
    status = models.CharField(max_length=12, choices=STATUS, default="active", db_index=True)
    basic_salary = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    # dates
    hire_date = models.DateField()
    original_hire_date = models.DateField(null=True, blank=True, help_text="First ever hire (kept on rehire).")
    probation_end_date = models.DateField(null=True, blank=True)
    confirmation_date = models.DateField(null=True, blank=True)
    contract_end_date = models.DateField(null=True, blank=True)
    retirement_date = models.DateField(null=True, blank=True)
    exit_date = models.DateField(null=True, blank=True)
    exit_reason = models.CharField(max_length=50, blank=True)
    rehire_eligible = models.BooleanField(default=True)
    previous_record = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL,
                                        related_name="rehires", help_text="Earlier employment record (rehire).")
    custom_fields = models.JSONField(default=dict, blank=True)

    class Meta:
        unique_together = [("organization", "staff_number")]
        ordering = ["last_name", "first_name"]
        indexes = [models.Index(fields=["organization", "last_name"]),
                   models.Index(fields=["organization", "ghana_card_no"])]

    def __str__(self):
        return f"{self.full_name} ({self.staff_number})"

    @property
    def full_name(self):
        parts = [self.first_name, self.middle_name, self.last_name]
        return " ".join(p for p in parts if p)

    @property
    def is_active(self):
        return self.status in ACTIVE_STATUSES

    def current_record(self):
        return self.employment_records.filter(is_current=True).first()


class EmploymentRecord(TenantModel):
    """Effective-dated employment history. Changes never overwrite: a new row is inserted and the
    previous row's effective_to is closed."""

    EVENTS = [
        ("hire", "Appointment / hire"),
        ("rehire", "Rehire"),
        ("confirmation", "Confirmation"),
        ("probation_extension", "Probation extension"),
        ("promotion", "Promotion"),
        ("demotion", "Demotion"),
        ("transfer", "Transfer"),
        ("secondment", "Secondment"),
        ("redesignation", "Redesignation"),
        ("salary_change", "Salary change / increment"),
        ("contract_renewal", "Contract renewal"),
        ("status_change", "Status change"),
        ("suspension", "Suspension"),
        ("reinstatement", "Reinstatement"),
        ("exit", "Exit / separation"),
        ("correction", "Data correction"),
    ]
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="employment_records")
    event_type = models.CharField(max_length=30, choices=EVENTS)
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    is_current = models.BooleanField(default=False, help_text="The record currently in force (as of today).")
    is_applied = models.BooleanField(default=False, help_text="Snapshot applied to the employee record.")
    department = models.ForeignKey("organization.Department", null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    branch = models.ForeignKey("organization.Branch", null=True, blank=True, on_delete=models.SET_NULL,
                               related_name="+")
    location = models.ForeignKey("organization.Location", null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name="+")
    position = models.ForeignKey(Position, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    job_title = models.ForeignKey("organization.JobTitle", null=True, blank=True, on_delete=models.SET_NULL,
                                  related_name="+")
    grade = models.ForeignKey("organization.Grade", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    grade_step = models.ForeignKey("organization.GradeStep", null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    cost_center = models.ForeignKey("organization.CostCenter", null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="+")
    supervisor = models.ForeignKey(Employee, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    category = models.ForeignKey(EmployeeCategory, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    employment_type = models.CharField(max_length=20, choices=Position.EMPLOYMENT_TYPES, default="permanent")
    status = models.CharField(max_length=12, choices=Employee.STATUS, default="active")
    basic_salary = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    reason = models.TextField(blank=True)
    reference = models.CharField(max_length=60, blank=True, help_text="Memo / letter reference number.")
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="+")

    SNAPSHOT_FIELDS = ["department", "branch", "location", "position", "job_title", "grade", "grade_step",
                       "cost_center", "supervisor", "category", "employment_type", "status", "basic_salary"]

    class Meta:
        ordering = ["employee", "-effective_from", "-id"]
        indexes = [models.Index(fields=["employee", "effective_from"])]

    def __str__(self):
        return f"{self.employee} {self.get_event_type_display()} from {self.effective_from:%d/%m/%Y}"


class ConcurrentAssignment(TenantModel):
    """Additional positions held concurrently (acting roles, joint appointments) where policy allows."""

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="concurrent_assignments")
    position = models.ForeignKey(Position, on_delete=models.PROTECT, related_name="concurrent_assignments")
    assignment_type = models.CharField(max_length=20, choices=[("acting", "Acting"), ("joint", "Joint"),
                                                               ("secondary", "Secondary")], default="acting")
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    allocation_percent = models.PositiveSmallIntegerField(default=0)
    allowance_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))

    class Meta:
        ordering = ["-start_date"]


class Contract(TenantModel):
    TYPES = [
        ("permanent", "Permanent"),
        ("probation", "Probationary"),
        ("fixed_term", "Fixed-term"),
        ("temporary", "Temporary"),
        ("consultancy", "Consultancy"),
        ("national_service", "National Service"),
        ("internship", "Internship"),
    ]
    STATUS = [("active", "Active"), ("expired", "Expired"), ("renewed", "Renewed"), ("terminated", "Terminated")]
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="contracts")
    contract_type = models.CharField(max_length=20, choices=TYPES)
    reference = models.CharField(max_length=60, blank=True)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    notice_period_days = models.PositiveSmallIntegerField(default=30)
    status = models.CharField(max_length=12, choices=STATUS, default="active")
    renewal_of = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="renewals")
    document = models.ForeignKey("documents.Document", null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name="+")
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-start_date"]

    def __str__(self):
        return f"{self.employee} {self.get_contract_type_display()} {self.start_date}"


class EmergencyContact(TenantModel):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="emergency_contacts")
    name = models.CharField(max_length=150)
    relationship = models.CharField(max_length=50)
    phone = models.CharField(max_length=20)
    alt_phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    is_primary = models.BooleanField(default=False)

    class Meta:
        ordering = ["-is_primary", "name"]


class Beneficiary(TenantModel):
    """Next of kin / pension and benefit beneficiaries."""

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="beneficiaries")
    name = models.CharField(max_length=150)
    relationship = models.CharField(max_length=50)
    phone = models.CharField(max_length=20, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    percentage = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("100"))
    is_next_of_kin = models.BooleanField(default=False)

    class Meta:
        ordering = ["-is_next_of_kin", "name"]
        verbose_name_plural = "beneficiaries"


class BankAccount(TenantModel):
    METHODS = [("bank", "Bank transfer"), ("momo", "Mobile money"), ("cash", "Cash / cheque")]
    MOMO_NETWORKS = [("mtn", "MTN MoMo"), ("telecel", "Telecel Cash"), ("at", "AT Money")]
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="bank_accounts")
    payment_method = models.CharField(max_length=10, choices=METHODS, default="bank")
    bank_name = models.CharField(max_length=100, blank=True)
    bank_code = models.CharField(max_length=20, blank=True)
    branch_name = models.CharField(max_length=100, blank=True)
    branch_code = models.CharField("Sort code", max_length=20, blank=True)
    account_name = models.CharField(max_length=150, blank=True)
    account_number = EncryptedCharField(blank=True)
    account_last4 = models.CharField(max_length=4, blank=True, editable=False)
    momo_network = models.CharField(max_length=10, choices=MOMO_NETWORKS, blank=True)
    momo_number = models.CharField(max_length=20, blank=True)
    is_primary = models.BooleanField(default=True)
    split_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("100"))
    verified = models.BooleanField(default=False)

    class Meta:
        ordering = ["-is_primary"]

    def save(self, *args, **kwargs):
        self.account_last4 = (self.account_number or "")[-4:]
        super().save(*args, **kwargs)


class Qualification(TenantModel):
    LEVELS = [
        ("shs", "SHS / WASSCE"), ("certificate", "Certificate"), ("diploma", "Diploma / HND"),
        ("bachelor", "Bachelor's"), ("master", "Master's"), ("doctorate", "Doctorate"),
        ("professional", "Professional"), ("other", "Other"),
    ]
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="qualifications")
    level = models.CharField(max_length=20, choices=LEVELS)
    title = models.CharField(max_length=150)
    institution = models.CharField(max_length=150)
    field_of_study = models.CharField(max_length=150, blank=True)
    year_obtained = models.PositiveSmallIntegerField(null=True, blank=True)
    grade = models.CharField(max_length=50, blank=True)
    verified = models.BooleanField(default=False)
    document = models.ForeignKey("documents.Document", null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name="+")

    class Meta:
        ordering = ["-year_obtained"]


class ChangeRequest(TenantModel):
    """Employee-submitted correction to their personal information; applied only after approval."""

    STATUS = [("pending", "Pending"), ("approved", "Approved"), ("rejected", "Rejected"),
              ("returned", "Returned for correction"), ("cancelled", "Cancelled")]
    ALLOWED_FIELDS = ["title", "first_name", "middle_name", "last_name", "preferred_name", "marital_status",
                      "personal_email", "phone", "alt_phone", "residential_address", "digital_address",
                      "ghana_card_no", "ssnit_number", "tin", "passport_no", "hometown", "date_of_birth"]
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="change_requests")
    changes = models.JSONField(help_text="{field: new_value}")
    previous = models.JSONField(default=dict, blank=True)
    reason = models.TextField(blank=True)
    status = models.CharField(max_length=12, choices=STATUS, default="pending")
    applied_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Change request #{self.pk} for {self.employee}"


class DataConsent(TenantModel):
    """Data Protection Act 2012 (Act 843): record of consent / lawful basis per processing purpose."""

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="consents")
    purpose = models.CharField(max_length=150)
    lawful_basis = models.CharField(max_length=30, choices=[
        ("consent", "Consent"), ("contract", "Contract"), ("legal", "Legal obligation"),
        ("vital", "Vital interest"), ("legitimate", "Legitimate interest")], default="consent")
    granted = models.BooleanField(default=True)
    granted_at = models.DateTimeField(auto_now_add=True)
    withdrawn_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-granted_at"]
