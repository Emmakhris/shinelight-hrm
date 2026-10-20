from django.contrib import admin

from .models import Organization, OrganizationFeature


class FeatureInline(admin.TabularInline):
    model = OrganizationFeature
    extra = 0


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ["name", "code", "currency", "is_active"]
    inlines = [FeatureInline]
