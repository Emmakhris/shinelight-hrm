from django.apps import AppConfig


class OnboardingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.onboarding"
    label = "onboarding"

    def ready(self):
        from . import signals  # noqa: F401
