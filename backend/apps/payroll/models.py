from decimal import Decimal

from django.conf import settings
from django.db import models

from apps.core.models import TenantModel

D = Decimal
MONEY = {"max_digits": 14, "decimal_places": 2, "default": D("0")}
RATE = {"max_digits": 7, "decimal_places": 4, "default": D("0")}


class PayGroup(TenantModel):
    FREQUENCY = [("monthly", "Monthly"), ("biweekly", "Bi-weekly"), ("weekly", "Weekly")]
    PRORATION = [("calendar", "Calendar days"), ("working", "Working days"), ("fixed30", "Fixed 30-day month")]
    code = models.SlugField(max_length=30)
    name = models.CharField(max_length=100)
    frequency = models.CharField(max_length=10, choices=FREQUENCY, default="monthly")
    currency = models.CharField(max_length=3, default="GHS")
    proration_method = models.CharField(max_length=10, choices=PRORATION, default="working")
    hours_per_month = models.DecimalField(max_digits=6, decimal_places=2, default=D("176"),
                                          help_text="Used to derive the hourly rate for overtime.")
    ot_weekday_multiplier = models.DecimalField(max_digits=4, decimal_places=2, default=D("1.50"))
    ot_weekend_multiplier = models.DecimalField(max_digits=4, decimal_places=2, default=D("2.00"))
    ot_holiday_multiplier = models.DecimalField(max_digits=4, decimal_places=2, default=D("2.00"))
    min_net_pay_percent = models.DecimalField(max_digits=5, decimal_places=2, default=D("25"),
                                              help_text="Flag payslips where net pay < this % of gross.")
    variance_threshold_percent = models.DecimalField(max_digits=5, decimal_places=2, default=D("10"))
    payslip_password = models.CharField(max_length=15, default="none", choices=[
        ("none", "No password"), ("staff_number", "Staff number"), ("dob", "Date of birth DDMMYYYY")])
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = [("organization", "code")]

    def __str__(self):
        return self.name


class StatutoryRateSet(TenantModel):
    """Ghana statutory payroll parameters, versioned by effective date. Seeded values MUST be verified
    against current GRA / SSNIT / NPRA publications before go-live."""

    name = models.CharField(max_length=100)
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    ssnit_employee_rate = models.DecimalField(**{**RATE, "default": D("5.5")})
    ssnit_employer_rate = models.DecimalField(**{**RATE, "default": D("13")})
    tier1_rate = models.DecimalField(**{**RATE, "default": D("13.5")}, help_text="Remitted to SSNIT.")
    tier2_rate = models.DecimalField(**{**RATE, "default": D("5")}, help_text="Remitted to the Tier 2 trustee.")
    ssnit_max_insurable_monthly = models.DecimalField(**MONEY)
    tier3_tax_exempt_max_percent = models.DecimalField(**{**RATE, "default": D("16.5")})
    bonus_tax_rate = models.DecimalField(**{**RATE, "default": D("5")})
    bonus_exempt_percent_annual_basic = models.DecimalField(**{**RATE, "default": D("15")})
    overtime_qualifying_annual_income = models.DecimalField(**MONEY, help_text="Junior staff threshold for OT tax.")
    overtime_rate_low = models.DecimalField(**{**RATE, "default": D("5")})
    overtime_rate_high = models.DecimalField(**{**RATE, "default": D("10")})
    overtime_threshold_percent_basic = models.DecimalField(**{**RATE, "default": D("50")})
    non_resident_rate = models.DecimalField(**{**RATE, "default": D("25")})
    verified = models.BooleanField(default=False, help_text="Confirmed by a payroll professional.")
    source_note = models.TextField(blank=True)

    class Meta:
        ordering = ["-effective_from"]

    def __str__(self):
        return f"{self.name} (from {self.effective_from:%d/%m/%Y})"


class TaxTable(TenantModel):
    """Monthly PAYE graduated bands (resident individuals)."""

    name = models.CharField(max_length=100)
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    verified = models.BooleanField(default=False)
    source_note = models.TextField(blank=True)

    class Meta:
        ordering = ["-effective_from"]

    def __str__(self):
        return self.name


class TaxBand(TenantModel):
    table = models.ForeignKey(TaxTable, on_delete=models.CASCADE, related_name="bands")
    order = models.PositiveSmallIntegerField()
    width = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True,
                                help_text="Chargeable amount in this band; blank = the remainder.")
    rate = models.DecimalField(max_digits=6, decimal_places=3)

    class Meta:
        ordering = ["table", "order"]


class TaxRelief(TenantModel):
    """Personal reliefs (annual amounts) e.g. marriage/responsibility, child education, aged dependant."""

    code = models.SlugField(max_length=30)
    name = models.CharField(max_length=100)
    annual_amount = models.DecimalField(**MONEY)
    percent_of_income = models.DecimalField(**RATE, help_text="If set, relief = % of assessable income.")
    max_quantity = models.PositiveSmallIntegerField(default=1)
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    verified = models.BooleanField(default=False)

    class Meta:
        ordering = ["code", "-effective_from"]

    def __str__(self):
        return self.name


class EmployeePayProfile(TenantModel):
    employee = models.OneToOneField("employees.Employee", on_delete=models.CASCADE, related_name="pay_profile")
    pay_group = models.ForeignKey(PayGroup, on_delete=models.PROTECT, related_name="profiles")
    is_tax_resident = models.BooleanField(default=True)
    paye_exempt = models.BooleanField(default=False)
    ssnit_applicable = models.BooleanField(default=True, help_text="Off for national service, retirees re-engaged etc.")
    tier3_employee_percent = models.DecimalField(**RATE, help_text="Voluntary provident fund % of basic.")
    tier3_employer_percent = models.DecimalField(**RATE)
    payment_hold = models.BooleanField(default=False, help_text="Exclude from bank file until released.")
    hold_reason = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return f"Pay profile: {self.employee}"


class EmployeeTaxRelief(TenantModel):
    employee = models.ForeignKey("employees.Employee", on_delete=models.CASCADE, related_name="tax_reliefs")
    relief = models.ForeignKey(TaxRelief, on_delete=models.PROTECT)
    quantity = models.PositiveSmallIntegerField(default=1)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    approved = models.BooleanField(default=False)


class PayElement(TenantModel):
    TYPES = [("earning", "Earning"), ("deduction", "Deduction"), ("employer", "Employer contribution"),
             ("info", "Information only")]
    CATEGORIES = [
        ("basic", "Basic salary"), ("allowance", "Allowance"), ("overtime", "Overtime"), ("bonus", "Bonus"),
        ("commission", "Commission"), ("arrears", "Arrears / back pay"), ("benefit", "Benefit in kind"),
        ("leave_pay", "Leave encashment"), ("statutory", "Statutory"), ("loan", "Loan repayment"),
        ("advance", "Salary advance recovery"), ("pension", "Pension / provident fund"), ("union", "Union dues"),
        ("welfare", "Welfare / association"), ("insurance", "Insurance"), ("other", "Other"),
    ]
    CALCULATION = [("fixed", "Fixed amount"), ("percent_basic", "% of basic"), ("percent_gross", "% of gross"),
                   ("hourly", "Hours x hourly rate"), ("daily", "Days x daily rate"), ("formula", "Formula")]
    TAX = [("normal", "Taxable (PAYE)"), ("bonus", "Bonus tax treatment"), ("overtime", "Overtime tax treatment"),
           ("exempt", "Tax exempt"), ("pre_tax", "Pre-tax deduction")]
    code = models.SlugField(max_length=30)
    name = models.CharField(max_length=100)
    element_type = models.CharField(max_length=10, choices=TYPES)
    category = models.CharField(max_length=12, choices=CATEGORIES, default="other")
    calculation = models.CharField(max_length=15, choices=CALCULATION, default="fixed")
    default_amount = models.DecimalField(**MONEY)
    default_percent = models.DecimalField(**RATE)
    multiplier = models.DecimalField(max_digits=5, decimal_places=2, default=D("1"))
    formula = models.CharField(max_length=255, blank=True, help_text="e.g. min(basic * 0.1, 500)")
    tax_treatment = models.CharField(max_length=10, choices=TAX, default="normal")
    prorate = models.BooleanField(default=True, help_text="Pro-rate for partial periods.")
    is_recurring = models.BooleanField(default=True)
    applies_to_all = models.BooleanField(default=False, help_text="Automatically applies to every employee.")
    gl_account = models.CharField(max_length=30, blank=True)
    gl_liability_account = models.CharField(max_length=30, blank=True, help_text="For deductions/employer costs.")
    show_on_payslip = models.BooleanField(default=True)
    order = models.PositiveSmallIntegerField(default=100)
    is_system = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = [("organization", "code")]
        ordering = ["element_type", "order", "code"]

    def __str__(self):
        return f"{self.code} - {self.name}"


class EmployeePayElement(TenantModel):
    """Recurring or one-off element assigned to an employee (overrides element defaults)."""

    employee = models.ForeignKey("employees.Employee", on_delete=models.CASCADE, related_name="pay_elements")
    element = models.ForeignKey(PayElement, on_delete=models.PROTECT, related_name="assignments")
    amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    percent = models.DecimalField(max_digits=7, decimal_places=4, null=True, blank=True)
    quantity = models.DecimalField(max_digits=9, decimal_places=2, null=True, blank=True)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    reference = models.CharField(max_length=100, blank=True)
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["employee", "element__order"]


class PayrollPeriod(TenantModel):
    STATUS = [("open", "Open"), ("closed", "Closed")]
    pay_group = models.ForeignKey(PayGroup, on_delete=models.PROTECT, related_name="periods")
    name = models.CharField(max_length=50)
    start_date = models.DateField()
    end_date = models.DateField()
    pay_date = models.DateField()
    status = models.CharField(max_length=10, choices=STATUS, default="open")

    class Meta:
        unique_together = [("pay_group", "start_date", "end_date")]
        ordering = ["-start_date"]

    def __str__(self):
        return f"{self.pay_group.code} {self.name}"


class PayrollRun(TenantModel):
    TYPES = [("regular", "Regular"), ("supplementary", "Supplementary"), ("final", "Final settlement"),
             ("reversal", "Reversal")]
    STATUS = [
        ("draft", "Draft"),
        ("calculated", "Calculated"),
        ("submitted", "Submitted for approval"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("paid", "Released / paid"),
        ("reversed", "Reversed"),
    ]
    period = models.ForeignKey(PayrollPeriod, on_delete=models.PROTECT, related_name="runs")
    run_type = models.CharField(max_length=15, choices=TYPES, default="regular")
    number = models.PositiveSmallIntegerField(default=1)
    status = models.CharField(max_length=12, choices=STATUS, default="draft", db_index=True)
    description = models.CharField(max_length=255, blank=True)
    employees = models.ManyToManyField("employees.Employee", blank=True, related_name="+",
                                       help_text="Limit run to these employees (supplementary/final runs).")
    rate_set = models.ForeignKey(StatutoryRateSet, null=True, blank=True, on_delete=models.PROTECT)
    tax_table = models.ForeignKey(TaxTable, null=True, blank=True, on_delete=models.PROTECT)
    calculated_at = models.DateTimeField(null=True, blank=True)
    calculated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                      related_name="+")
    calculation_count = models.PositiveSmallIntegerField(default=0)
    submitted_at = models.DateTimeField(null=True, blank=True)
    submitted_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                     related_name="+")
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="+")
    released_at = models.DateTimeField(null=True, blank=True)
    released_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="+")
    reversal_of = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="reversals")
    totals = models.JSONField(default=dict, blank=True)
    payslips_published = models.BooleanField(default=False)

    class Meta:
        ordering = ["-period__start_date", "-number"]

    def __str__(self):
        return f"{self.period} #{self.number} ({self.get_run_type_display()})"

    @property
    def is_locked(self):
        return self.status in ("submitted", "approved", "paid", "reversed")


class Payslip(TenantModel):
    STATUS = [("ok", "OK"), ("warning", "Warning"), ("error", "Error"), ("hold", "On hold")]
    run = models.ForeignKey(PayrollRun, on_delete=models.CASCADE, related_name="payslips")
    employee = models.ForeignKey("employees.Employee", on_delete=models.PROTECT, related_name="payslips")
    # snapshot at calculation time
    staff_number = models.CharField(max_length=30)
    employee_name = models.CharField(max_length=200)
    department = models.CharField(max_length=120, blank=True)
    job_title = models.CharField(max_length=150, blank=True)
    grade = models.CharField(max_length=50, blank=True)
    cost_center = models.CharField(max_length=60, blank=True)
    ssnit_number = models.CharField(max_length=20, blank=True)
    tin = models.CharField(max_length=20, blank=True)
    payment_method = models.CharField(max_length=10, blank=True)
    bank_name = models.CharField(max_length=100, blank=True)
    bank_branch_code = models.CharField(max_length=20, blank=True)
    account_last4 = models.CharField(max_length=4, blank=True)
    days_in_period = models.DecimalField(max_digits=5, decimal_places=2, default=D("0"))
    days_payable = models.DecimalField(max_digits=5, decimal_places=2, default=D("0"))
    monthly_basic = models.DecimalField(**MONEY)
    basic_pay = models.DecimalField(**MONEY)
    gross_pay = models.DecimalField(**MONEY)
    taxable_income = models.DecimalField(**MONEY)
    paye = models.DecimalField(**MONEY)
    bonus_tax = models.DecimalField(**MONEY)
    overtime_tax = models.DecimalField(**MONEY)
    ssnit_employee = models.DecimalField(**MONEY)
    ssnit_employer = models.DecimalField(**MONEY)
    tier1 = models.DecimalField(**MONEY)
    tier2 = models.DecimalField(**MONEY)
    tier3_employee = models.DecimalField(**MONEY)
    tier3_employer = models.DecimalField(**MONEY)
    reliefs = models.DecimalField(**MONEY)
    total_deductions = models.DecimalField(**MONEY)
    net_pay = models.DecimalField(**MONEY)
    employer_cost = models.DecimalField(**MONEY)
    status = models.CharField(max_length=10, choices=STATUS, default="ok")
    messages = models.JSONField(default=list, blank=True)
    ytd = models.JSONField(default=dict, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    first_viewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = [("run", "employee")]
        ordering = ["run", "staff_number"]

    def __str__(self):
        return f"Payslip {self.staff_number} {self.run.period.name}"


class PayslipLine(TenantModel):
    payslip = models.ForeignKey(Payslip, on_delete=models.CASCADE, related_name="lines")
    element = models.ForeignKey(PayElement, null=True, blank=True, on_delete=models.PROTECT)
    code = models.CharField(max_length=30)
    name = models.CharField(max_length=100)
    line_type = models.CharField(max_length=10, choices=PayElement.TYPES)
    category = models.CharField(max_length=12, blank=True)
    quantity = models.DecimalField(max_digits=9, decimal_places=2, null=True, blank=True)
    rate = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    amount = models.DecimalField(**MONEY)
    taxable = models.BooleanField(default=True)
    gl_account = models.CharField(max_length=30, blank=True)
    reference = models.CharField(max_length=100, blank=True)
    show_on_payslip = models.BooleanField(default=True)
    order = models.PositiveSmallIntegerField(default=100)

    class Meta:
        ordering = ["payslip", "line_type", "order"]


class Loan(TenantModel):
    TYPES = [("staff_loan", "Staff loan"), ("salary_advance", "Salary advance"), ("car_loan", "Vehicle loan"),
             ("housing", "Housing / rent advance"), ("other", "Other")]
    STATUS = [("pending", "Pending approval"), ("approved", "Approved"), ("active", "Active (repaying)"),
              ("completed", "Completed"), ("rejected", "Rejected"), ("cancelled", "Cancelled"),
              ("written_off", "Written off"), ("returned", "Returned")]
    employee = models.ForeignKey("employees.Employee", on_delete=models.PROTECT, related_name="loans")
    loan_type = models.CharField(max_length=20, choices=TYPES)
    principal = models.DecimalField(**MONEY)
    interest_rate = models.DecimalField(**RATE, help_text="Flat annual % on principal.")
    installments = models.PositiveSmallIntegerField(default=1)
    installment_amount = models.DecimalField(**MONEY)
    total_repayable = models.DecimalField(**MONEY)
    balance = models.DecimalField(**MONEY)
    start_date = models.DateField(help_text="First deduction from the period containing this date.")
    purpose = models.TextField(blank=True)
    status = models.CharField(max_length=12, choices=STATUS, default="pending")
    disbursed_at = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_loan_type_display()} {self.employee.full_name} {self.principal}"


class LoanRepayment(TenantModel):
    loan = models.ForeignKey(Loan, on_delete=models.CASCADE, related_name="repayments")
    payslip = models.ForeignKey(Payslip, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    date = models.DateField()
    amount = models.DecimalField(**MONEY)
    balance_after = models.DecimalField(**MONEY)
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["date", "id"]


class PayrollAdjustment(TenantModel):
    """One-off adjustments for a period: arrears/back pay, bonus, recoveries, corrections."""

    employee = models.ForeignKey("employees.Employee", on_delete=models.CASCADE, related_name="payroll_adjustments")
    period = models.ForeignKey(PayrollPeriod, on_delete=models.CASCADE, related_name="adjustments")
    element = models.ForeignKey(PayElement, on_delete=models.PROTECT)
    amount = models.DecimalField(**MONEY)
    quantity = models.DecimalField(max_digits=9, decimal_places=2, null=True, blank=True)
    reason = models.CharField(max_length=255)
    is_system = models.BooleanField(default=False, help_text="Generated (e.g. retro arrears).")

    class Meta:
        ordering = ["period", "employee"]
