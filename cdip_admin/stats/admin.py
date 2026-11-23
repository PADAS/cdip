from django.contrib import admin

from .models import ErrorRollup, RollupRunState, ThroughputRollup


class ReadOnlyAdmin(admin.ModelAdmin):
    """The rollup job owns these tables; admin is for inspection only."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ThroughputRollup)
class ThroughputRollupAdmin(ReadOnlyAdmin):
    list_display = ("bucket", "metric", "object_type", "data_provider_id", "destination_id", "count")
    list_filter = ("metric", "object_type")
    date_hierarchy = "bucket"
    show_full_result_count = False


@admin.register(ErrorRollup)
class ErrorRollupAdmin(ReadOnlyAdmin):
    list_display = ("bucket", "value", "origin", "log_level", "integration_id", "count")
    list_filter = ("log_level", "origin", "value")
    date_hierarchy = "bucket"
    show_full_result_count = False


@admin.register(RollupRunState)
class RollupRunStateAdmin(ReadOnlyAdmin):
    list_display = ("__str__", "frequent_run_completed_at", "daily_run_completed_at")
