from django.contrib import admin
from .models import DispatcherDeployment


def restart_deployments(modeladmin, request, queryset):
    for deployment in queryset:
        deployment.status = DispatcherDeployment.Status.SCHEDULED
        deployment.save()


restart_deployments.short_description = "Restart selected deployments"


@admin.register(DispatcherDeployment)
class DispatcherDeploymentAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "status",
        "status_details",
        "integration",
        "legacy_integration",
        "created_at",
        "updated_at",
    )
    list_filter = (
        "status",
    )
    readonly_fields = (
        "status", "status_details",
    )
    actions = [restart_deployments]
