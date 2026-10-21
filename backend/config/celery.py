import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("shinelight")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

app.conf.beat_schedule = {
    "workflow-sla-escalations": {
        "task": "apps.workflow.tasks.process_sla_escalations",
        "schedule": crontab(minute="*/15"),
    },
    "leave-monthly-accrual": {
        "task": "apps.leave.tasks.run_monthly_accrual",
        "schedule": crontab(hour=1, minute=0, day_of_month=1),
    },
    "attendance-device-sync": {
        "task": "apps.attendance.tasks.sync_all_devices",
        "schedule": crontab(minute="*/10"),
    },
    "attendance-daily-processing": {
        "task": "apps.attendance.tasks.process_previous_day",
        "schedule": crontab(hour=2, minute=0),
    },
    "expiry-reminders": {
        "task": "apps.notifications.tasks.send_expiry_reminders",
        "schedule": crontab(hour=7, minute=0),
    },
    "webhook-retries": {
        "task": "apps.integrations.tasks.retry_failed_deliveries",
        "schedule": crontab(minute="*/5"),
    },
    "servicedesk-sla": {
        "task": "apps.servicedesk.tasks.process_ticket_sla",
        "schedule": crontab(minute="*/15"),
    },
    "travel-housekeeping": {
        "task": "apps.expenses.tasks.travel_housekeeping",
        "schedule": crontab(hour=7, minute=30),
    },
    "recruitment-housekeeping": {
        "task": "apps.recruitment.tasks.recruitment_housekeeping",
        "schedule": crontab(hour=0, minute=30),
    },
    "onboarding-housekeeping": {
        "task": "apps.onboarding.tasks.onboarding_housekeeping",
        "schedule": crontab(hour=7, minute=15),
    },
    "performance-reminders": {
        "task": "apps.performance.tasks.performance_reminders",
        "schedule": crontab(hour=7, minute=45),
    },
    "learning-housekeeping": {
        "task": "apps.learning.tasks.learning_housekeeping",
        "schedule": crontab(hour=6, minute=30),
    },
    "relations-escalation": {
        "task": "apps.relations.tasks.relations_escalation",
        "schedule": crontab(hour=7, minute=5),
    },
    "offboarding-housekeeping": {
        "task": "apps.offboarding.tasks.offboarding_housekeeping",
        "schedule": crontab(hour=2, minute=30),
    },
    "expire-trials": {
        "task": "apps.tenancy.tasks.expire_trials",
        "schedule": crontab(hour=6, minute=5),
    },
    "purge-assistant-conversations": {
        "task": "apps.assistant.tasks.purge_assistant_conversations",
        "schedule": crontab(hour=3, minute=40),
    },
    "safety-housekeeping": {
        "task": "apps.safety.tasks.safety_housekeeping",
        "schedule": crontab(hour=7, minute=20),
    },
    "close-due-surveys": {
        "task": "apps.engagement.tasks.close_due_surveys",
        "schedule": crontab(hour=0, minute=15),
    },
    "scheduled-reports": {
        "task": "apps.reports.tasks.send_scheduled_reports",
        "schedule": crontab(hour=6, minute=0),
    },
}
