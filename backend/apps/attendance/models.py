from decimal import Decimal

from django.db import models

from apps.core.models import TenantModel


class Shift(TenantModel):
    code = models.SlugField(max_length=20)
    name = models.CharField(max_length=80)
    start_time = models.TimeField()
    end_time = models.TimeField(help_text="If earlier than start time the shift crosses midnight.")
    break_minutes = models.PositiveSmallIntegerField(default=60)
    grace_in_minutes = models.PositiveSmallIntegerField(default=15)
    grace_out_minutes = models.PositiveSmallIntegerField(default=10)
    is_night = models.BooleanField(default=False, help_text="Night duty (night allowance / OT category).")
    is_on_call = models.BooleanField(default=False)
    color = models.CharField(max_length=7, default="#0ea5e9")
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = [("organization", "code")]
        ordering = ["start_time"]

    def __str__(self):
        times = f"{self.start_time:%H:%M}-{self.end_time:%H:%M}"
        return self.name if times in self.name else f"{self.name} ({times})"

    @property
    def crosses_midnight(self):
        return self.end_time <= self.start_time

    @property
    def scheduled_minutes(self):
        start = self.start_time.hour * 60 + self.start_time.minute
        end = self.end_time.hour * 60 + self.end_time.minute
        if end <= start:
            end += 24 * 60
        return end - start - self.break_minutes


class AttendancePolicy(TenantModel):
    """Attendance rules by department / category / location. Most specific (lowest priority) wins."""

    name = models.CharField(max_length=120)
    department = models.ForeignKey("organization.Department", null=True, blank=True, on_delete=models.CASCADE)
    category = models.ForeignKey("employees.EmployeeCategory", null=True, blank=True, on_delete=models.CASCADE)
    location = models.ForeignKey("organization.Location", null=True, blank=True, on_delete=models.CASCADE)
    default_shift = models.ForeignKey(Shift, null=True, blank=True, on_delete=models.SET_NULL)
    weekend_days = models.JSONField(default=list, blank=True, help_text="Weekday numbers, Mon=0 ... Sun=6.")
    overtime_after_minutes = models.PositiveSmallIntegerField(default=30, help_text="Minimum extra minutes counted as OT.")
    overtime_requires_approval = models.BooleanField(default=True)
    max_overtime_hours_month = models.PositiveSmallIntegerField(default=0, help_text="0 = no cap.")
    rounding_minutes = models.PositiveSmallIntegerField(default=15, help_text="Round OT down to this block.")
    half_day_minutes = models.PositiveSmallIntegerField(default=240, help_text="Worked minutes below = half day.")
    require_geofence = models.BooleanField(default=False)
    allow_web_clock = models.BooleanField(default=True)
    absent_deduction = models.BooleanField(default=False, help_text="Unexcused absences deducted in payroll.")
    priority = models.PositiveSmallIntegerField(default=100)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["priority"]
        verbose_name_plural = "attendance policies"

    def __str__(self):
        return self.name

    def matches(self, employee):
        if self.department_id and employee.department_id != self.department_id:
            return False
        if self.category_id and employee.category_id != self.category_id:
            return False
        if self.location_id and employee.location_id != self.location_id:
            return False
        return True


class ShiftPattern(TenantModel):
    """Rotating pattern, e.g. Day, Day, Night, Night, Off, Off (sequence of shift ids / null = off)."""

    name = models.CharField(max_length=120)
    sequence = models.JSONField(help_text="List of shift ids or null for an off day.")

    def __str__(self):
        return self.name


class RosterEntry(TenantModel):
    employee = models.ForeignKey("employees.Employee", on_delete=models.CASCADE, related_name="roster")
    date = models.DateField()
    shift = models.ForeignKey(Shift, null=True, blank=True, on_delete=models.PROTECT, help_text="Blank = day off.")
    department = models.ForeignKey("organization.Department", null=True, blank=True, on_delete=models.SET_NULL,
                                   help_text="Unit/ward of deployment if different from home department.")
    is_on_call = models.BooleanField(default=False)
    is_published = models.BooleanField(default=False)
    source = models.CharField(max_length=10, default="manual", choices=[("manual", "Manual"), ("pattern", "Pattern"),
                                                                        ("swap", "Shift swap"),
                                                                        ("emergency", "Emergency")])
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        unique_together = [("employee", "date")]
        ordering = ["date", "employee"]
        verbose_name_plural = "roster entries"


class BiometricDevice(TenantModel):
    name = models.CharField(max_length=100)
    vendor = models.CharField(max_length=20, default="zkteco")
    ip_address = models.GenericIPAddressField()
    port = models.PositiveIntegerField(default=4370)
    comm_key = models.PositiveIntegerField(default=0)
    serial_number = models.CharField(max_length=60, blank=True)
    location = models.ForeignKey("organization.Location", null=True, blank=True, on_delete=models.SET_NULL)
    direction = models.CharField(max_length=5, default="auto", choices=[("auto", "Auto"), ("in", "In"), ("out", "Out")])
    is_active = models.BooleanField(default=True)
    last_sync_at = models.DateTimeField(null=True, blank=True)
    last_sync_status = models.CharField(max_length=255, blank=True)
    last_record_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.name} ({self.ip_address})"


class BiometricEnrollment(TenantModel):
    """Maps the user id stored on the biometric terminal to an employee."""

    employee = models.ForeignKey("employees.Employee", on_delete=models.CASCADE, related_name="biometric_ids")
    device_user_id = models.CharField(max_length=30)

    class Meta:
        unique_together = [("organization", "device_user_id")]


class ClockEvent(TenantModel):
    SOURCES = [("web", "Web"), ("mobile", "Mobile"), ("biometric", "Biometric"), ("manual", "Manual (HR)"),
               ("correction", "Approved correction")]
    employee = models.ForeignKey("employees.Employee", on_delete=models.CASCADE, related_name="clock_events")
    timestamp = models.DateTimeField(db_index=True)
    direction = models.CharField(max_length=5, default="auto", choices=[("in", "In"), ("out", "Out"), ("auto", "Auto")])
    source = models.CharField(max_length=12, choices=SOURCES)
    device = models.ForeignKey(BiometricDevice, null=True, blank=True, on_delete=models.SET_NULL)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    within_geofence = models.BooleanField(null=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    is_void = models.BooleanField(default=False)

    class Meta:
        ordering = ["timestamp"]
        unique_together = [("employee", "timestamp", "source")]


class AttendanceDay(TenantModel):
    STATUS = [
        ("present", "Present"),
        ("late", "Late"),
        ("half_day", "Half day"),
        ("absent", "Absent"),
        ("incomplete", "Missing clock-in/out"),
        ("on_leave", "On leave"),
        ("holiday", "Public holiday"),
        ("off", "Day off"),
    ]
    OT_CATEGORIES = [("normal", "Weekday"), ("weekend", "Weekend / rest day"), ("holiday", "Public holiday"),
                     ("night", "Night")]
    employee = models.ForeignKey("employees.Employee", on_delete=models.CASCADE, related_name="attendance_days")
    date = models.DateField(db_index=True)
    shift = models.ForeignKey(Shift, null=True, blank=True, on_delete=models.SET_NULL)
    scheduled_start = models.DateTimeField(null=True, blank=True)
    scheduled_end = models.DateTimeField(null=True, blank=True)
    first_in = models.DateTimeField(null=True, blank=True)
    last_out = models.DateTimeField(null=True, blank=True)
    worked_minutes = models.PositiveIntegerField(default=0)
    late_minutes = models.PositiveIntegerField(default=0)
    early_leave_minutes = models.PositiveIntegerField(default=0)
    overtime_minutes = models.PositiveIntegerField(default=0)
    overtime_category = models.CharField(max_length=10, choices=OT_CATEGORIES, blank=True)
    approved_overtime_minutes = models.PositiveIntegerField(default=0)
    overtime_status = models.CharField(max_length=10, default="none", choices=[
        ("none", "None"), ("pending", "Pending"), ("approved", "Approved"), ("rejected", "Rejected")])
    status = models.CharField(max_length=12, choices=STATUS, default="absent")
    is_exception = models.BooleanField(default=False, db_index=True)
    exception_resolved = models.BooleanField(default=False)
    locked = models.BooleanField(default=False, help_text="Locked after payroll period close.")
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        unique_together = [("employee", "date")]
        ordering = ["-date"]


class AttendanceCorrection(TenantModel):
    STATUS = [("pending", "Pending"), ("approved", "Approved"), ("rejected", "Rejected"), ("returned", "Returned"),
              ("cancelled", "Cancelled")]
    employee = models.ForeignKey("employees.Employee", on_delete=models.CASCADE, related_name="attendance_corrections")
    date = models.DateField()
    clock_in = models.DateTimeField(null=True, blank=True)
    clock_out = models.DateTimeField(null=True, blank=True)
    reason = models.TextField()
    status = models.CharField(max_length=10, choices=STATUS, default="pending")

    class Meta:
        ordering = ["-date"]


class AttendancePeriodSummary(TenantModel):
    """Monthly totals handed to payroll once locked."""

    employee = models.ForeignKey("employees.Employee", on_delete=models.CASCADE, related_name="attendance_summaries")
    period_start = models.DateField()
    period_end = models.DateField()
    scheduled_days = models.PositiveSmallIntegerField(default=0)
    days_present = models.DecimalField(max_digits=5, decimal_places=1, default=Decimal("0"))
    days_absent = models.DecimalField(max_digits=5, decimal_places=1, default=Decimal("0"))
    days_on_leave = models.DecimalField(max_digits=5, decimal_places=1, default=Decimal("0"))
    late_count = models.PositiveSmallIntegerField(default=0)
    late_minutes = models.PositiveIntegerField(default=0)
    incomplete_days = models.PositiveSmallIntegerField(default=0)
    ot_normal_hours = models.DecimalField(max_digits=7, decimal_places=2, default=Decimal("0"))
    ot_weekend_hours = models.DecimalField(max_digits=7, decimal_places=2, default=Decimal("0"))
    ot_holiday_hours = models.DecimalField(max_digits=7, decimal_places=2, default=Decimal("0"))
    night_shifts = models.PositiveSmallIntegerField(default=0)
    on_call_days = models.PositiveSmallIntegerField(default=0)
    unexcused_absence_days = models.DecimalField(max_digits=5, decimal_places=1, default=Decimal("0"))
    locked = models.BooleanField(default=False)

    class Meta:
        unique_together = [("employee", "period_start", "period_end")]
        ordering = ["-period_start", "employee"]
