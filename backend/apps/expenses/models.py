from decimal import Decimal

from django.conf import settings
from django.db import models

from apps.core.models import TenantModel

MONEY = {"max_digits": 14, "decimal_places": 2, "default": Decimal("0")}
EXPENSE_CATEGORIES = [
    ("transport", "Transport / fares"), ("fuel", "Fuel & mileage"), ("accommodation", "Accommodation"),
    ("meals", "Meals"), ("per_diem", "Per diem"), ("communication", "Airtime / data"), ("medical", "Medical"),
    ("training", "Training / conference fees"), ("supplies", "Office supplies"), ("other", "Other"),
]


class PerDiemRate(TenantModel):
    """Approved daily rates by destination class and grade band."""

    DESTINATIONS = [("local", "Within region"), ("national", "Other region in Ghana"), ("africa", "Africa"),
                    ("international", "Outside Africa")]
    destination_class = models.CharField(max_length=15, choices=DESTINATIONS)
    location = models.CharField(max_length=100, blank=True, help_text="Optional specific city (e.g. Accra, Lagos).")
    min_grade_level = models.PositiveSmallIntegerField(default=0)
    max_grade_level = models.PositiveSmallIntegerField(default=99)
    currency = models.CharField(max_length=3, default="GHS")
    daily_allowance = models.DecimalField(**MONEY)
    accommodation_cap = models.DecimalField(**MONEY)
    effective_from = models.DateField()
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["destination_class", "min_grade_level"]


class ExpenseBudget(TenantModel):
    department = models.ForeignKey("organization.Department", on_delete=models.CASCADE, related_name="expense_budgets")
    year = models.PositiveSmallIntegerField()
    category = models.CharField(max_length=20, choices=EXPENSE_CATEGORIES + [("travel", "Travel (all)")], default="travel")
    amount = models.DecimalField(**MONEY)

    class Meta:
        unique_together = [("department", "year", "category")]


class TravelRequest(TenantModel):
    STATUS = [("draft", "Draft"), ("pending", "Pending approval"), ("approved", "Approved"), ("rejected", "Rejected"),
              ("returned", "Returned"), ("cancelled", "Cancelled"), ("completed", "Trip completed"),
              ("retired", "Advance retired / closed")]
    MODES = [("road_official", "Official vehicle"), ("road_public", "Public transport"), ("road_private", "Own vehicle"),
             ("air", "Air"), ("other", "Other")]
    reference = models.CharField(max_length=30, blank=True)
    employee = models.ForeignKey("employees.Employee", on_delete=models.CASCADE, related_name="travel_requests")
    purpose = models.TextField()
    destination = models.CharField(max_length=150)
    destination_class = models.CharField(max_length=15, choices=PerDiemRate.DESTINATIONS, default="national")
    departure_date = models.DateField()
    return_date = models.DateField()
    transport_mode = models.CharField(max_length=15, choices=MODES, default="road_public")
    currency = models.CharField(max_length=3, default="GHS")
    per_diem_days = models.DecimalField(max_digits=5, decimal_places=1, default=Decimal("0"))
    per_diem_rate = models.DecimalField(**MONEY)
    accommodation_estimate = models.DecimalField(**MONEY)
    transport_estimate = models.DecimalField(**MONEY)
    other_estimate = models.DecimalField(**MONEY)
    total_estimate = models.DecimalField(**MONEY)
    advance_requested = models.DecimalField(**MONEY)
    advance_paid = models.DecimalField(**MONEY)
    advance_paid_on = models.DateField(null=True, blank=True)
    advance_reference = models.CharField(max_length=60, blank=True)
    retirement_due = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=12, choices=STATUS, default="draft", db_index=True)
    warnings = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["-departure_date"]

    def __str__(self):
        return f"{self.reference or 'Travel'} {self.employee.full_name} → {self.destination}"


class ExpenseClaim(TenantModel):
    STATUS = [("draft", "Draft"), ("pending", "Pending approval"), ("approved", "Approved"), ("rejected", "Rejected"),
              ("returned", "Returned"), ("cancelled", "Cancelled"), ("paid", "Paid / settled")]
    PAYMENT = [("payroll", "With next salary"), ("bank", "Bank / MoMo transfer"), ("cash", "Petty cash")]
    reference = models.CharField(max_length=30, blank=True)
    employee = models.ForeignKey("employees.Employee", on_delete=models.CASCADE, related_name="expense_claims")
    travel_request = models.ForeignKey(TravelRequest, null=True, blank=True, on_delete=models.SET_NULL,
                                       related_name="claims", help_text="Link to retire a travel advance.")
    title = models.CharField(max_length=200)
    currency = models.CharField(max_length=3, default="GHS")
    total = models.DecimalField(**MONEY)
    advance_offset = models.DecimalField(**MONEY, help_text="Advance already paid against this trip.")
    net_payable = models.DecimalField(**MONEY, help_text="Positive = owed to employee; negative = to recover.")
    payment_method = models.CharField(max_length=10, choices=PAYMENT, default="payroll")
    status = models.CharField(max_length=12, choices=STATUS, default="draft", db_index=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    paid_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                related_name="+")
    payment_reference = models.CharField(max_length=60, blank=True)
    payroll_adjustment = models.ForeignKey("payroll.PayrollAdjustment", null=True, blank=True,
                                           on_delete=models.SET_NULL, related_name="+")
    warnings = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.reference or 'Claim'} {self.title}"


class ExpenseItem(TenantModel):
    claim = models.ForeignKey(ExpenseClaim, on_delete=models.CASCADE, related_name="items")
    date = models.DateField()
    category = models.CharField(max_length=20, choices=EXPENSE_CATEGORIES)
    description = models.CharField(max_length=255)
    amount = models.DecimalField(**MONEY)
    receipt = models.ForeignKey("documents.Document", null=True, blank=True, on_delete=models.SET_NULL,
                                related_name="+")
    receipt_missing_reason = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["date", "id"]
