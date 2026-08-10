from django.contrib import admin
from django.contrib.admin.widgets import AutocompleteSelect

from core.admin import (
    AutocompleteFieldListFilter,
    CustomDateFilter,
    EstimatedCountPaginator,
)

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
    # These relations must be named explicitly. A bare ``select_related()`` --
    # which is what ``list_select_related = True`` produces -- follows only
    # *non-nullable* FKs, and both ``integration`` and ``created_by`` are
    # nullable, so it followed neither. Every displayed row then dereferenced
    # them lazily, and ``Integration.__str__`` walked owner and type on top of
    # that: ~4 queries per row.
    list_select_related = (
        "integration",
        "integration__owner",
        "integration__type",
        "created_by",
    )
    list_display = (
        "created_at",
        "log_level",
        "value",
        "title",
        "origin",
        "log_type",
        "is_reversible",
        "integration",
        "created_by",
    )
    search_fields = (
        "title",
        "value",
    )
    # No ``date_hierarchy``: it issues ``SELECT DISTINCT DATE_TRUNC(...)`` over
    # the whole filtered queryset on every render. Postgres has no skip scan in
    # any version, so that is a sequential scan of every partition -- measured
    # at 3,677 buffers / 131ms per 500k rows, and linear in table size.
    # ``CustomDateFilter`` covers the same need by building its links from the
    # clock instead of from the table.
    list_filter = (
        ("created_at", CustomDateFilter),
        "log_level",
        "log_type",
        "origin",
        "is_reversible",
        ("integration", AutocompleteFieldListFilter),
    )
    actions = [revert_selected]

    @property
    def media(self):
        # Django collects media from the admin and its forms, but not from
        # list filters, so the select2 assets AutocompleteFieldListFilter
        # depends on have to be contributed here or the widget renders as an
        # inert <select>.
        return super().media + AutocompleteSelect(
            self.opts.get_field("integration"), self.admin_site
        ).media
