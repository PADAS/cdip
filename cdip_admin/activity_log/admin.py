from django.contrib import admin

from core.admin import EstimatedCountPaginator

from .models import ActivityLog


def revert_selected(modeladmin, request, queryset):
    for log in queryset:
        log.revert()


revert_selected.short_description = "Revert selected"


class ActivityLogPaginator(EstimatedCountPaginator):
    """Paginator for the partitioned ActivityLog admin.

    ActivityLogManager.get_queryset() always injects
    ``filter(created_at__lte=now)`` to skip empty future partitions, so
    the queryset reaching this paginator always has a non-empty WHERE
    clause. Without this opt-in flag, the base class would treat that as
    "user-filtered" and fall back to the exact COUNT(*) — exactly the
    behaviour this PR exists to prevent. The baseline filter excludes
    only data that doesn't exist yet, so the table-wide estimate from
    pg_class is still the right number to report.

    User-applied filters (log_level, integration, etc.) ride through the
    same WHERE clause and aren't distinguishable here, so filtered
    drill-down counts will overcount. That's an accepted trade-off — the
    incident this PR fixes is the unfiltered changelist locking workers.
    """

    estimate_through_baseline_filter = True


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    # ActivityLog is the largest (partitioned) table in the portal. The
    # default admin paginator runs COUNT(*) on every changelist render,
    # which on this table can lock up a worker for minutes — that's the
    # incident this PR was opened to fix. ActivityLogPaginator sums
    # pg_class.reltuples across leaf partitions (cheap planner read) and
    # the ``estimate_through_baseline_filter`` flag tells it to ignore
    # the manager's ``created_at <= now`` baseline filter.
    paginator = ActivityLogPaginator
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
