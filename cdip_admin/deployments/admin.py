from django import forms
from django.contrib import admin
from django_json_widget.widgets import JSONEditorWidget
from .models import DispatcherDeployment
from .tasks import deploy_serverless_dispatcher


class DispatcherDeploymentForm(forms.ModelForm):
    configuration = forms.JSONField(
        required=False,
        label="JSON Configuration",
        widget=JSONEditorWidget(width="60em", height="30em"),
    )

    class Meta:
        model = DispatcherDeployment
        fields = "__all__"

    def clean_configuration(self):
        # The model field is NOT NULL with default=dict; an emptied editor
        # must save as {} rather than None. Coerce only None — falsy JSON
        # values like [], 0, or false are valid and must be preserved.
        value = self.cleaned_data.get("configuration")
        return {} if value is None else value


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


def delete_orphaned_dispatchers(modeladmin, request, queryset):
    safe_statuses = [DispatcherDeployment.Status.COMPLETE, DispatcherDeployment.Status.ERROR]
    orphans = queryset.filter(
        integration__isnull=True,
        legacy_integration__isnull=True,
        status__in=safe_statuses,
    )
    for deployment in orphans:
        deployment.delete()


delete_orphaned_dispatchers.short_description = "Delete orphaned dispatchers (no integration, stable status)"


class OrphanedFilter(admin.SimpleListFilter):
    title = "orphaned"
    parameter_name = "orphaned"

    def lookups(self, request, model_admin):
        return [
            ("yes", "Yes (no integration)"),
            ("no", "No"),
        ]

    def queryset(self, request, queryset):
        if self.value() == "yes":
            return queryset.filter(integration__isnull=True, legacy_integration__isnull=True)
        if self.value() == "no":
            return queryset.exclude(integration__isnull=True, legacy_integration__isnull=True)
        return queryset


@admin.register(DispatcherDeployment)
class DispatcherDeploymentAdmin(admin.ModelAdmin):
    form = DispatcherDeploymentForm
    # Both FKs appear in list_display and their __str__ dereferences
    # owner/type, so join them up front to avoid per-row queries.
    list_select_related = (
        "integration__owner",
        "integration__type",
        "legacy_integration__owner",
        "legacy_integration__type",
    )
    list_display = (
        "name",
        "status",
        "failure_reason",
        "attempt_count",
        "last_attempt_at",
        "status_details",
        "integration",
        "topic_name",
        "legacy_integration",
        "created_at",
        "updated_at",
    )
    list_filter = (
        "status",
        "failure_reason",
        OrphanedFilter,
        "integration__type",
        "legacy_integration__type",
    )
    readonly_fields = (
        "attempt_count",
        "last_attempt_at",
        "last_error",
    )
    # Render the integration FKs as AJAX search boxes. Plain selects load
    # every Integration/OutboundIntegrationConfiguration, and their __str__
    # dereferences owner/type per row, making the change page unusably slow.
    autocomplete_fields = (
        "integration",
        "legacy_integration",
    )
    actions = [restart_deployments, recreate_dispatchers, delete_orphaned_dispatchers]
    search_fields = (
        "id",
        "name",
        "integration__name",
        "legacy_integration__name",
    )

    def delete_queryset(self, request, queryset):
        for deployment in queryset:
            deployment.delete()
