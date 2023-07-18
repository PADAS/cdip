from django.contrib import admin
from .models import DispatcherDeployment


@admin.register(DispatcherDeployment)
class DispatcherDeploymentAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "status",
        "integration",
        "legacy_integration",
        "created_at",
        "updated_at",
    )
    list_filter = (
        "status",
    )
    # readonly_fields = (
    #     "status",
    # )
