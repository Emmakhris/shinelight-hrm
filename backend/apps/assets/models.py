from decimal import Decimal

from django.conf import settings
from django.db import models

from apps.core.models import TenantModel

MONEY = {"max_digits": 14, "decimal_places": 2, "default": Decimal("0")}
CONDITIONS = [("new", "New"), ("good", "Good"), ("fair", "Fair / worn"), ("damaged", "Damaged"), ("lost", "Lost")]


class AssetCategory(TenantModel):
    name = models.CharField(max_length=100)
    code = models.SlugField(max_length=30)
    owner = models.CharField(max_length=10, choices=[("it", "IT"), ("admin", "Administration / facilities")],
                             default="admin", help_text="Team that issues and receives these items.")
    is_returnable = models.BooleanField(default=True, help_text="Uncheck for consumable PPE / uniforms.")
    is_tracked = models.BooleanField(default=True, help_text="Individually tagged (serial / inventory ID).")

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "asset categories"

    def __str__(self):
        return self.name


class Asset(TenantModel):
    STATUS = [("available", "Available"), ("assigned", "Assigned"), ("in_repair", "In repair"), ("lost", "Lost"),
              ("damaged", "Damaged / unusable"), ("retired", "Retired / disposed")]
    tag = models.CharField("Inventory ID", max_length=40)
    category = models.ForeignKey(AssetCategory, on_delete=models.PROTECT, related_name="assets")
    description = models.CharField(max_length=200, help_text="Make and model.")
    serial_number = models.CharField(max_length=80, blank=True)
    purchase_date = models.DateField(null=True, blank=True)
    cost = models.DecimalField(**MONEY)
    replacement_value = models.DecimalField(**MONEY, help_text="Used for recovery if lost or damaged.")
    location = models.ForeignKey("organization.Location", null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name="+")
    status = models.CharField(max_length=10, choices=STATUS, default="available", db_index=True)
    holder = models.ForeignKey("employees.Employee", null=True, blank=True, on_delete=models.SET_NULL,
                               related_name="assets_held")
    external_ref = models.CharField(max_length=80, blank=True, help_text="ID in the IT asset / procurement system.")
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["tag"]
        constraints = [models.UniqueConstraint(fields=["organization", "tag"], name="uniq_asset_tag")]

    def __str__(self):
        return f"{self.tag} {self.description}"


class Assignment(TenantModel):
    """Issue of a tagged asset, or of consumable items (uniforms, PPE) by quantity."""

    asset = models.ForeignKey(Asset, null=True, blank=True, on_delete=models.PROTECT, related_name="assignments")
    category = models.ForeignKey(AssetCategory, on_delete=models.PROTECT, related_name="+")
    item = models.CharField(max_length=150, blank=True, help_text="For untagged items, e.g. 'Scrubs (blue), size M'.")
    quantity = models.PositiveSmallIntegerField(default=1)
    employee = models.ForeignKey("employees.Employee", on_delete=models.CASCADE, related_name="asset_assignments")
    issued_on = models.DateField()
    issued_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                  related_name="+")
    condition_out = models.CharField(max_length=10, choices=CONDITIONS, default="good")
    due_back = models.DateField(null=True, blank=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    returned_on = models.DateField(null=True, blank=True)
    condition_in = models.CharField(max_length=10, choices=CONDITIONS, blank=True)
    received_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="+")
    incident_report = models.TextField(blank=True, help_text="Employee's report of loss or damage.")
    recovery_amount = models.DecimalField(**MONEY)
    recovery_status = models.CharField(max_length=10, choices=[("none", "None"), ("pending", "To recover"),
                                                               ("payroll", "Through payroll"), ("paid", "Paid"),
                                                               ("waived", "Waived")], default="none")
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-issued_on", "-id"]

    @property
    def outstanding(self):
        return self.returned_on is None and self.category.is_returnable
