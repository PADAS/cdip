from django.contrib import admin
from .models import DispatcherDeployment
from .tasks import deploy_serverless_dispatcher


def restart_deployments(modeladmin, request, queryset):
    for deployment in queryset:
        deployment.status = DispatcherDeployment.Status.SCHEDULED
        deployment.save()


restart_deployments.short_description = "Restart selected deployments"


def recreate_dispatchers(modeladmin, request, queryset):
    for deployment in queryset:
        deploy_serverless_dispatcher.delay(
            deployment_id=deployment.id,
            force_recreate=True        )


recreate_dispatchers.short_description = "Recreate selected dispatchers"


@admin.register(DispatcherDeployment)
class DispatcherDeploymentAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "status",
        "status_details",
        "integration",
        "topic_name",
        "legacy_integration",
        "created_at",
        "updated_at",
    )
    list_filter = (
        "status",
        "integration__type",
        "legacy_integration__type",
    )
    actions = [restart_deployments, recreate_dispatchers]
    search_fields = (
        "id",
        "name",
        "integration__name",
        "legacy_integration__name",
    )

    def delete_queryset(self, request, queryset):
        for deployment in queryset:
            deployment.delete()
