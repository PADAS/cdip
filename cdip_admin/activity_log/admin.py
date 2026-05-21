from django.contrib import admin

from core.admin import EstimatedCountPaginator

from .models import ActivityLog


def revert_selected(modeladmin, request, queryset):
    for log in queryset:
        log.revert()


revert_selected.short_description = "Revert selected"


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    # ActivityLog is the largest table in the portal. The default admin
    # paginator runs COUNT(*) on every changelist render, which on this
    # table can lock up a worker for minutes — that's the incident this
    # PR was opened to fix. EstimatedCountPaginator uses pg_class.reltuples
    # for the unfiltered changelist (cheap planner read) and falls back
    # to the exact count when filters are applied.
    paginator = EstimatedCountPaginator
    # Suppresses the *secondary* full-table total shown next to a filtered
    # count. Doesn't replace the paginator's primary count — that's the
    # job of ``paginator`` above.
    show_full_result_count = False
    list_select_related = True
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
