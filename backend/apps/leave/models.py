from decimal import Decimal

from django.db import models

from apps.core.models import TenantModel


class LeaveType(TenantModel):
    code = models.SlugField(max_length=30)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    is_paid = models.BooleanField(default=True)
    tracks_balance = models.BooleanField(default=True, help_text="Limited by an entitlement balance.")
    count_working_days = models.BooleanField(default=True, help_text="Exclude weekends/holidays (else calendar days).")
    allow_half_day = models.BooleanField(default=True)
    allow_negative_balance = models.BooleanField(default=False)
    requires_attachment = models.BooleanField(default=False)
    attachment_after_days = models.PositiveSmallIntegerField(default=0, help_text="Require attachment if days exceed.")
    is_confidential = models.BooleanField(default=False, help_text="Reason/attachments visible only to HR (e.g. sick).")
    gender = models.CharField(max_length=10, blank=True, choices=[("male", "Male only"), ("female", "Female only")])
    min_service_months = models.PositiveSmallIntegerField(default=0)
    notice_days = models.PositiveSmallIntegerField(default=0)
    max_days_per_request = models.PositiveSmallIntegerField(default=0, help_text="0 = no limit.")
    allow_during_probation = models.BooleanField(default=True)
    color = models.CharField(max_length=7, default="#2563eb")
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = [("organization", "code")]
        ordering = ["name"]

    def __str__(self):
        return self.name


class LeavePolicy(TenantModel):
    """Entitlement rules. The most specific matching policy (lowest priority number) applies."""

    ACCRUAL = [("upfront", "Full entitlement at start of year"), ("monthly", "Monthly accrual"),
               ("none", "No entitlement (event-based)")]
    leave_type = models.ForeignKey(LeaveType, on_delete=models.CASCADE, related_name="policies")
    name = models.CharField(max_length=120)
    category = models.ForeignKey("employees.EmployeeCategory", null=True, blank=True, on_delete=models.CASCADE)
    min_grade_level = models.PositiveSmallIntegerField(null=True, blank=True)
    max_grade_level = models.PositiveSmallIntegerField(null=True, blank=True)
    employment_type = models.CharField(max_length=20, blank=True)
    entitlement_days = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0"))
    accrual_method = models.CharField(max_length=10, choices=ACCRUAL, default="upfront")
    prorate_first_year = models.BooleanField(default=True)
    carryover_max_days = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0"))
    carryover_expiry_months = models.PositiveSmallIntegerField(default=3, help_text="0 = carried days never expire.")
    service_bonus = models.JSONField(default=list, blank=True,
                                     help_text='Extra days by years of service, e.g. [{"years": 5, "days": 3}]')
    priority = models.PositiveSmallIntegerField(default=100)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["leave_type", "priority"]
        verbose_name_plural = "leave policies"

    def __str__(self):
        return self.name

    def matches(self, employee) -> bool:
        if self.category_id and employee.category_id != self.category_id:
            return False
        level = employee.grade.level if employee.grade_id else None
        if self.min_grade_level is not None and (level is None or level < self.min_grade_level):
            return False
        if self.max_grade_level is not None and (level is None or level > self.max_grade_level):
            return False
        if self.employment_type and employee.employment_type != self.employment_type:
            return False
        return True


class LeaveLedgerEntry(TenantModel):
    """Leave balance ledger. Balance = sum(days) per employee/type/year. Never edited; corrections are new rows."""

    TYPES = [
        ("entitlement", "Entitlement"),
        ("accrual", "Monthly accrual"),
        ("carryover", "Carried over"),
        ("taken", "Leave taken"),
        ("reversal", "Reversal (cancel/recall)"),
        ("adjustment", "Manual adjustment"),
        ("expiry", "Expired"),
        ("opening", "Opening balance (migration)"),
    ]
    employee = models.ForeignKey("employees.Employee", on_delete=models.CASCADE, related_name="leave_ledger")
    leave_type = models.ForeignKey(LeaveType, on_delete=models.PROTECT, related_name="ledger")
    year = models.PositiveSmallIntegerField(db_index=True)
    entry_type = models.CharField(max_length=12, choices=TYPES)
    days = models.DecimalField(max_digits=6, decimal_places=2)
    date = models.DateField()
    request = models.ForeignKey("LeaveRequest", null=True, blank=True, on_delete=models.SET_NULL, related_name="ledger")
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["employee", "year", "date", "id"]
        indexes = [models.Index(fields=["employee", "leave_type", "year"])]


class LeaveRequest(TenantModel):
    STATUS = [
        ("draft", "Draft"),
        ("pending", "Pending approval"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("returned", "Returned for correction"),
        ("cancelled", "Cancelled"),
        ("recalled", "Recalled"),
    ]
    employee = models.ForeignKey("employees.Employee", on_delete=models.CASCADE, related_name="leave_requests")
    leave_type = models.ForeignKey(LeaveType, on_delete=models.PROTECT, related_name="requests")
    start_date = models.DateField()
    end_date = models.DateField()
    start_half = models.BooleanField(default=False, help_text="Start in the afternoon (half day).")
    end_half = models.BooleanField(default=False, help_text="End at midday (half day).")
    days = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0"))
    reason = models.TextField(blank=True)
    attachment = models.ForeignKey("documents.Document", null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    contact_while_away = models.CharField(max_length=100, blank=True)
    relief_officer = models.ForeignKey("employees.Employee", null=True, blank=True, on_delete=models.SET_NULL,
                                       related_name="relief_for")
    status = models.CharField(max_length=10, choices=STATUS, default="draft", db_index=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    recall_date = models.DateField(null=True, blank=True)
    recall_reason = models.TextField(blank=True)
    expected_return_date = models.DateField(null=True, blank=True)
    actual_return_date = models.DateField(null=True, blank=True)
    return_notes = models.TextField(blank=True)
    warnings = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["-start_date"]
        indexes = [models.Index(fields=["employee", "start_date", "end_date"])]

    def __str__(self):
        return f"{self.employee.full_name} {self.leave_type.name} {self.start_date:%d/%m/%Y}-{self.end_date:%d/%m/%Y}"
