from decimal import Decimal

from django.conf import settings
from django.db import models

from apps.core.models import TenantModel

MONEY = {"max_digits": 14, "decimal_places": 2, "default": Decimal("0")}
PCT = {"max_digits": 7, "decimal_places": 3, "default": Decimal("0")}


class SalaryReviewCycle(TenantModel):
    """Annual (or ad-hoc) salary review: budget, guidelines, proposals, approval, and application as
    effective-dated salary changes (back-dated cycles produce arrears automatically in payroll)."""

    STATUS = [("draft", "Draft"), ("open", "Open for proposals"), ("pending", "Pending approval"),
              ("approved", "Approved"), ("rejected", "Rejected"), ("returned", "Returned"), ("applied", "Applied"),
              ("cancelled", "Cancelled")]
    name = models.CharField(max_length=150)
    effective_date = models.DateField()
    budget_percent = models.DecimalField(**PCT, help_text="Overall increase budget as % of the payroll in scope.")
    default_increase_percent = models.DecimalField(**PCT)
    guidelines = models.JSONField(default=list, blank=True,
                                  help_text='Per-grade ranges, e.g. [{"min_level": 1, "max_level": 3, "min": 5, "max": 10}]')
    departments = models.ManyToManyField("organization.Department", blank=True,
                                         help_text="Blank = whole organization.")
    status = models.CharField(max_length=12, choices=STATUS, default="draft")
    applied_at = models.DateTimeField(null=True, blank=True)
    applied_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-effective_date"]

    def __str__(self):
        return self.name


class SalaryReviewLine(TenantModel):
    cycle = models.ForeignKey(SalaryReviewCycle, on_delete=models.CASCADE, related_name="lines")
    employee = models.ForeignKey("employees.Employee", on_delete=models.CASCADE, related_name="salary_reviews")
    current_basic = models.DecimalField(**MONEY)
    increase_percent = models.DecimalField(**PCT)
    proposed_basic = models.DecimalField(**MONEY)
    proposed_grade_step = models.ForeignKey("organization.GradeStep", null=True, blank=True, on_delete=models.SET_NULL)
    justification = models.CharField(max_length=255, blank=True)
    outside_guideline = models.BooleanField(default=False)
    excluded = models.BooleanField(default=False)
    applied = models.BooleanField(default=False)

    class Meta:
        unique_together = [("cycle", "employee")]
        ordering = ["employee__last_name"]


class BonusScheme(TenantModel):
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    basis = models.CharField(max_length=15, default="fixed", choices=[
        ("fixed", "Fixed amount"), ("percent_basic", "% of monthly basic"), ("months_basic", "Months of basic")])
    default_value = models.DecimalField(max_digits=12, decimal_places=3, default=Decimal("0"))
    pay_period = models.ForeignKey("payroll.PayrollPeriod", null=True, blank=True, on_delete=models.SET_NULL,
                                   help_text="Payroll period in which approved awards are paid.")
    status = models.CharField(max_length=12, choices=SalaryReviewCycle.STATUS, default="draft")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name


class BonusAward(TenantModel):
    scheme = models.ForeignKey(BonusScheme, on_delete=models.CASCADE, related_name="awards")
    employee = models.ForeignKey("employees.Employee", on_delete=models.CASCADE, related_name="bonus_awards")
    amount = models.DecimalField(**MONEY)
    justification = models.CharField(max_length=255, blank=True)
    payroll_adjustment = models.ForeignKey("payroll.PayrollAdjustment", null=True, blank=True,
                                           on_delete=models.SET_NULL, related_name="+")

    class Meta:
        unique_together = [("scheme", "employee")]


class BenefitPlan(TenantModel):
    TYPES = [("health", "Health insurance"), ("life", "Life / group insurance"), ("pension", "Provident fund / pension"),
             ("vehicle", "Vehicle scheme"), ("housing", "Housing"), ("wellness", "Wellness"), ("education", "Education"),
             ("other", "Other")]
    code = models.SlugField(max_length=30)
    name = models.CharField(max_length=150)
    plan_type = models.CharField(max_length=12, choices=TYPES)
    provider = models.CharField(max_length=150, blank=True)
    description = models.TextField(blank=True)
    employer_monthly_cost = models.DecimalField(**MONEY)
    employee_monthly_cost = models.DecimalField(**MONEY)
    cost_per_dependant = models.DecimalField(**MONEY, help_text="Added to the employee cost per dependant.")
    max_dependants = models.PositiveSmallIntegerField(default=0)
    # eligibility
    categories = models.ManyToManyField("employees.EmployeeCategory", blank=True)
    min_grade_level = models.PositiveSmallIntegerField(null=True, blank=True)
    min_service_months = models.PositiveSmallIntegerField(default=0)
    employment_types = models.JSONField(default=list, blank=True, help_text="Blank = all types.")
    auto_enroll = models.BooleanField(default=False, help_text="Enrol every eligible employee automatically.")
    requires_approval = models.BooleanField(default=True)
    deduction_element = models.ForeignKey("payroll.PayElement", null=True, blank=True, on_delete=models.SET_NULL,
                                          related_name="+", help_text="Payroll deduction for the employee share.")
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = [("organization", "code")]
        ordering = ["plan_type", "name"]

    def __str__(self):
        return self.name


class BenefitEnrollment(TenantModel):
    STATUS = [("pending", "Pending approval"), ("active", "Active"), ("rejected", "Rejected"),
              ("returned", "Returned"), ("cancelled", "Cancelled"), ("ended", "Ended")]
    plan = models.ForeignKey(BenefitPlan, on_delete=models.PROTECT, related_name="enrollments")
    employee = models.ForeignKey("employees.Employee", on_delete=models.CASCADE, related_name="benefit_enrollments")
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    dependants = models.JSONField(default=list, blank=True,
                                  help_text='[{"name": "...", "relationship": "child", "date_of_birth": "2018-01-01"}]')
    member_number = models.CharField(max_length=60, blank=True)
    status = models.CharField(max_length=10, choices=STATUS, default="pending")
    pay_element = models.ForeignKey("payroll.EmployeePayElement", null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="+")

    class Meta:
        ordering = ["-start_date"]

    def __str__(self):
        return f"{self.employee.full_name} — {self.plan.name}"

    @property
    def employee_cost(self):
        return self.plan.employee_monthly_cost + self.plan.cost_per_dependant * len(self.dependants or [])
