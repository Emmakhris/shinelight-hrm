from decimal import Decimal

from django.db import models

from apps.core.models import TenantModel


class Branch(TenantModel):
    code = models.CharField(max_length=20)
    name = models.CharField(max_length=120)
    region = models.CharField(max_length=60, blank=True)
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    is_head_office = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = [("organization", "code")]
        ordering = ["name"]
        verbose_name_plural = "branches"

    def __str__(self):
        return self.name


class Location(TenantModel):
    """Physical work location; can carry a geofence for web clock-in."""

    name = models.CharField(max_length=120)
    branch = models.ForeignKey(Branch, null=True, blank=True, on_delete=models.SET_NULL, related_name="locations")
    gps_address = models.CharField("Ghana Post GPS", max_length=20, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    geofence_radius_m = models.PositiveIntegerField(default=200)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class CostCenter(TenantModel):
    code = models.CharField(max_length=30)
    name = models.CharField(max_length=120)
    gl_code = models.CharField(max_length=30, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = [("organization", "code")]
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} - {self.name}"


class Department(TenantModel):
    """Hierarchical org unit: directorate > department > unit > team (or ward for hospitals)."""

    TYPES = [
        ("directorate", "Directorate / Division"),
        ("department", "Department"),
        ("unit", "Unit"),
        ("team", "Team"),
        ("ward", "Ward / Clinical unit"),
    ]
    code = models.CharField(max_length=20)
    name = models.CharField(max_length=120)
    unit_type = models.CharField(max_length=20, choices=TYPES, default="department")
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="children")
    branch = models.ForeignKey(Branch, null=True, blank=True, on_delete=models.SET_NULL, related_name="departments")
    cost_center = models.ForeignKey(CostCenter, null=True, blank=True, on_delete=models.SET_NULL)
    head = models.ForeignKey(
        "employees.Employee", null=True, blank=True, on_delete=models.SET_NULL, related_name="headed_departments"
    )
    min_staffing = models.PositiveSmallIntegerField(
        default=0, help_text="Minimum staff on duty; used for leave conflict warnings."
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = [("organization", "code")]
        ordering = ["name"]

    def __str__(self):
        return self.name

    def ancestors(self):
        node, chain = self.parent, []
        while node is not None and node not in chain:
            chain.append(node)
            node = node.parent
        return chain


class JobFamily(TenantModel):
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "job families"

    def __str__(self):
        return self.name


class Grade(TenantModel):
    """Salary grade / band with optional steps (salary scale)."""

    code = models.CharField(max_length=20)
    name = models.CharField(max_length=100)
    level = models.PositiveSmallIntegerField(default=1, help_text="Higher = more senior.")
    min_salary = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    max_salary = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    currency = models.CharField(max_length=3, default="GHS")
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = [("organization", "code")]
        ordering = ["level", "code"]

    def __str__(self):
        return f"{self.code} - {self.name}"


class GradeStep(TenantModel):
    grade = models.ForeignKey(Grade, on_delete=models.CASCADE, related_name="steps")
    step = models.PositiveSmallIntegerField()
    basic_salary = models.DecimalField(max_digits=14, decimal_places=2)
    effective_from = models.DateField(null=True, blank=True)

    class Meta:
        unique_together = [("grade", "step")]
        ordering = ["grade", "step"]

    def __str__(self):
        return f"{self.grade.code} step {self.step}: {self.basic_salary}"


class JobTitle(TenantModel):
    name = models.CharField(max_length=150)
    code = models.CharField(max_length=30, blank=True)
    family = models.ForeignKey(JobFamily, null=True, blank=True, on_delete=models.SET_NULL, related_name="titles")
    default_grade = models.ForeignKey(Grade, null=True, blank=True, on_delete=models.SET_NULL)
    description = models.TextField(blank=True, help_text="Job description / responsibilities.")
    requirements = models.TextField(blank=True)
    is_clinical = models.BooleanField(default=False, help_text="Requires professional licence (hospital module).")
    required_license_type = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Position(TenantModel):
    """An approved post in the establishment, distinct from the person occupying it."""

    STATUS = [
        ("proposed", "Proposed"),
        ("approved", "Approved"),
        ("frozen", "Frozen"),
        ("abolished", "Abolished"),
    ]
    EMPLOYMENT_TYPES = [
        ("permanent", "Permanent"),
        ("contract", "Fixed-term contract"),
        ("temporary", "Temporary"),
        ("national_service", "National Service"),
        ("intern", "Intern"),
        ("casual", "Casual"),
    ]
    code = models.CharField(max_length=30)
    job_title = models.ForeignKey(JobTitle, on_delete=models.PROTECT, related_name="positions")
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name="positions")
    branch = models.ForeignKey(Branch, null=True, blank=True, on_delete=models.SET_NULL)
    location = models.ForeignKey(Location, null=True, blank=True, on_delete=models.SET_NULL)
    grade = models.ForeignKey(Grade, null=True, blank=True, on_delete=models.SET_NULL)
    reports_to = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="subordinates")
    status = models.CharField(max_length=20, choices=STATUS, default="approved")
    employment_type = models.CharField(max_length=20, choices=EMPLOYMENT_TYPES, default="permanent")
    headcount = models.PositiveSmallIntegerField(default=1, help_text="Number of approved incumbents.")
    budgeted_annual_cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    is_critical = models.BooleanField(default=False, help_text="Critical role for succession planning.")
    effective_from = models.DateField(null=True, blank=True)
    effective_to = models.DateField(null=True, blank=True)

    class Meta:
        unique_together = [("organization", "code")]
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} {self.job_title.name}"

    @property
    def occupied_count(self):
        primary = self.employees.filter(status__in=["active", "probation", "suspended", "on_leave"]).count()
        concurrent = self.concurrent_assignments.filter(end_date__isnull=True).count()
        return primary + concurrent

    @property
    def vacancies(self):
        if self.status != "approved":
            return 0
        return max(self.headcount - self.occupied_count, 0)
