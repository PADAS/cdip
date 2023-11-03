from django.contrib import admin
from .models import ActivityLog


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "title",
        "integration",
        "log_level",
        "log_type",
        "origin",
        "value",
        "created_by",
        "details",
        "is_reversible",
        "revert_data",
    )
    search_fields = (
        "title",
        "value",
        "details",
    )
    date_hierarchy = 'created_at'
    list_filter = (
        "log_level",
        "log_type",
        "origin",
        "is_reversible",
        "integration",
    )

