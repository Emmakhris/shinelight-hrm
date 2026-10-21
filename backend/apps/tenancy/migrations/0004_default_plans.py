from django.db import migrations

ALL = ["payroll", "hospital", "sms", "biometric", "geofence", "ai_assistant"]
PLANS = [
    # code, name, max_employees, features, trial_days, public. Prices are left at 0 for the operator to set.
    ("trial", "Free trial", 25, ["payroll", "sms", "geofence"], 30, True),
    ("standard", "Standard", 0, ["payroll", "sms", "geofence", "biometric", "ai_assistant"], 0, True),
    ("healthcare", "Healthcare", 0, ALL, 0, True),
]


def create(apps, schema_editor):
    Plan = apps.get_model("tenancy", "Plan")
    for code, name, cap, features, trial, public in PLANS:
        Plan.objects.get_or_create(code=code, defaults={"name": name, "max_employees": cap, "features": features,
                                                        "trial_days": trial, "is_public": public})


class Migration(migrations.Migration):
    dependencies = [("tenancy", "0003_plan_organization_created_via_organization_status_and_more")]
    operations = [migrations.RunPython(create, migrations.RunPython.noop)]
