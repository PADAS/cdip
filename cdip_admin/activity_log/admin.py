from django.contrib import admin
from .models import ActivityLog


def revert_selected(modeladmin, request, queryset):
    for log in queryset:
        log.revert()


revert_selected.short_description = "Revert selected"


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "log_level",
        "value",
        "title",
        "origin",
        "log_type",
        "details",
        "is_reversible",
        "revert_data",
        "integration",
        "created_by",
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
    actions = [revert_selected]
