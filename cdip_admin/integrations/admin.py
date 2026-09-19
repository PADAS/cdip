import django_celery_beat
import psycopg2
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from collections import defaultdict
from django.db.models import F, Prefetch
from django.forms import ModelForm
from django.forms.models import BaseInlineFormSet
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.html import format_html, format_html_join
from django_celery_beat.admin import PeriodicTaskAdmin
from django_celery_beat.models import PeriodicTask
from simple_history.admin import SimpleHistoryAdmin
from django.contrib import messages
from core.admin import CustomDateFilter, EstimatedCountPaginator, titled_filter
import deployments.models
from .models import (
    OutboundIntegrationType,
    InboundIntegrationType,
    OutboundIntegrationConfiguration,
    InboundIntegrationConfiguration,
    Device,
    DeviceGroup,
    DeviceState,
    BridgeIntegrationType,
    BridgeIntegration,
    SubjectType,
    IntegrationType,
    IntegrationAction,
    Integration,
    IntegrationStatus,
    IntegrationConfiguration,
    Route,
    RouteConfiguration,
    RouteProvider,
    RouteDestination,
    SourceFilter, Source, SourceState, SourceConfiguration,
    GundiTrace,
    IntegrationWebhook,
    WebhookConfiguration,
    AmbiguousDefaultRouteError,
    decide_default_route,
    DefaultRouteState,
    filter_by_default_route_state,
)

from .forms import (
    InboundIntegrationConfigurationForm,
    OutboundIntegrationConfigurationForm,
    BridgeIntegrationForm
)
from .models.v2.models import HealthCheckSettings, IntegrationMetrics

# Register your models here.
admin.site.register(InboundIntegrationType, SimpleHistoryAdmin)
admin.site.register(OutboundIntegrationType, SimpleHistoryAdmin)


@admin.register(DeviceState)
class DeviceStateAdmin(admin.ModelAdmin):
    list_display = (
        "device",
        "_external_id",
        "_owner",
        "created_at",
    )
    list_filter = (
        "device__inbound_configuration__name",
        "device__inbound_configuration__owner",
    )
    search_fields = (
        "device__external_id",
        "device__inbound_configuration__name",
    )

    date_hierarchy = "created_at"

    def _external_id(self, obj):
        return obj.device.external_id

    _external_id.short_description = "Device ID"

    def _owner(self, obj):
        return obj.device.inbound_configuration.owner

    _owner.short_description = "Owner"


@admin.register(Device)
class DeviceAdmin(SimpleHistoryAdmin):
    list_display = (
        "external_id",
        "_owner",
        "created_at",
    )
    list_filter = (
        "inbound_configuration__name",
        "inbound_configuration__owner",
    )

    search_fields = (
        "external_id",
        "inbound_configuration__name",
        "inbound_configuration__owner__name",
    )

    date_hierarchy = "created_at"

    def _owner(self, obj):
        return obj.inbound_configuration.owner

    _owner.short_description = "Owner"


@admin.register(SubjectType)
class SubjectTypeAdmin(SimpleHistoryAdmin):
    list_display = ("value", "display_name", "created_at")


@admin.register(DeviceGroup)
class DeviceGroupAdmin(SimpleHistoryAdmin):
    list_display = ("name", "owner", "created_at")
    list_filter = ("owner",)

    search_fields = ("id", "name", "owner__name", "devices__external_id")


@admin.register(InboundIntegrationConfiguration)
class InboundIntegrationConfigurationAdmin(SimpleHistoryAdmin):
    readonly_fields = [
        "id",
    ]
    form = InboundIntegrationConfigurationForm

    list_display = (
        "name",
        "type",
        "owner",
        "enabled",
    )

    list_filter = (
        "type",
        "owner",
        "enabled",
    )

    list_editable = ("enabled",)

    search_fields = (
        "id",
        "name",
        "type__name",
        "owner__name",
    )


class DispatcherDeploymentInline(admin.StackedInline):
    model = deployments.models.DispatcherDeployment
    fields = (
        "name",
        "configuration",
        "status",
        "status_details"
    )
    readonly_fields = (
        "status", "status_details",
    )


@admin.register(OutboundIntegrationConfiguration)
class OutboundIntegrationConfigurationAdmin(SimpleHistoryAdmin):
    readonly_fields = [
        "id",
    ]
    form = OutboundIntegrationConfigurationForm

    list_filter = (
        "type",
        "owner",
        "enabled",
    )

    search_fields = (
        "id",
        "name",
        "type__name",
        "owner__name",
    )

    def _name(self, obj):
        return obj.name or "-no-name-"

    list_display = ("type", "_name", "owner", "created_at", "updated_at")
    list_display_links = (
        "_name",
        "owner",
    )

    inlines = [
        DispatcherDeploymentInline,
    ]

    def delete_model(self, request, obj):
        try:  # Is there a deployment?
            deployment = obj.dispatcher_by_outbound
        except OutboundIntegrationConfiguration.dispatcher_by_outbound.RelatedObjectDoesNotExist:
            pass  # No deployment to delete
        else:  # Delete deployment
            if deployment.status not in [  # Check if it's in a safe state to delete
                deployments.models.DispatcherDeployment.Status.COMPLETE,
                deployments.models.DispatcherDeployment.Status.ERROR
            ]:
                msg = f"Warning: related dispatcher cannot be deleted in the current status. You can delete it later from the deployments page."
                messages.add_message(request, messages.WARNING, message=msg)
            elif OutboundIntegrationConfiguration.objects.filter(
                    additional__topic=deployment.topic_name).count() > 1:  # Check if the topic is being used by other integrations
                msg = f"Warning: related dispatcher won't be deleted as it's being used by other integrations."
                messages.add_message(request, messages.WARNING, message=msg)
            else:  # It's safe to delete it
                deployment.delete()
        # Then delete the integration
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        # Overwritten to call deployment.delete() in bulk deletion
        for obj in queryset:
            self.delete_model(request, obj)


@admin.register(BridgeIntegrationType)
class BridgeIntegrationTypeAdmin(SimpleHistoryAdmin):

    list_display = ("name",)


@admin.register(BridgeIntegration)
class BridgeIntegrationAdmin(SimpleHistoryAdmin):
    form = BridgeIntegrationForm
    list_display = ("name", "owner", "type")
    list_filter = (
        "type",
        "owner",
        "enabled",
    )

    search_fields = (
        "id",
        "name",
        "type__name",
        "owner__name",
    )


@admin.register(IntegrationType)
class IntegrationTypeAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "value",
        "description",
        "service_url",
        "help_center_url",
    )


@admin.register(IntegrationAction)
class IntegrationActionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "integration_type",
        "type",
        "name",
        "value",
        "is_periodic_action",
        "description",
    )
    list_filter = (
        "integration_type",
        "type",
    )


@admin.register(IntegrationWebhook)
class IntegrationActionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "integration_type",
        "name",
        "value",
        "description",
    )
    list_filter = (
        "integration_type",
    )



class IntegrationAdminForm(ModelForm):
    """Refuse (as a form error, before anything is saved) setting a
    ``default_route`` that ``decide_default_route`` would refuse as ambiguous
    (spec §5.1). Raising from a post_save receiver instead would surface as a
    500 from the admin's change form."""

    class Meta:
        model = Integration
        fields = "__all__"

    def clean_default_route(self):
        route = self.cleaned_data.get("default_route")
        if route is not None and self.instance.pk is not None:
            try:
                decide_default_route(self.instance, joining_route=route)
            except AmbiguousDefaultRouteError as error:
                raise ValidationError(str(error))
        return route


def _integration_labels_by_route(through_model, route_ids):
    """{route_id: "Name (Type), Name (Type)"} for the given routes, in one query.

    Reads the through table with .values_list() so neither Route nor Integration
    is instantiated: Route.__init__ runs ChangeLogMixin, which queries
    first_provider per instance (see GundiTraceAdmin.get_queryset).
    """
    labels = defaultdict(list)
    rows = (
        through_model.objects.filter(route_id__in=route_ids)
        .order_by("integration__name")
        .values_list("route_id", "integration__name", "integration__type__name")
    )
    for route_id, name, type_name in rows:
        labels[route_id].append(f"{name} ({type_name})")
    return {route_id: ", ".join(names) for route_id, names in labels.items()}


class DefaultRouteStateFilter(admin.SimpleListFilter):
    """One click to the providers violating the default-route invariant (spec §5.3).
    Choices map one-to-one onto the clauses of providers_without_valid_default_route()."""
    title = "Default route"
    parameter_name = "default_route_state"

    def lookups(self, request, model_admin):
        return (
            (DefaultRouteState.VALID.value, "Valid"),
            (DefaultRouteState.MISSING.value, "Missing (NULL)"),
            (DefaultRouteState.NOT_MEMBER.value, "Not one of its routes"),
            (DefaultRouteState.EMPTY_DEFAULT.value, "Empty while another route delivers"),
        )

    def queryset(self, request, queryset):
        try:
            state = DefaultRouteState(self.value())
        except ValueError:
            return queryset
        return filter_by_default_route_state(queryset, state)


@admin.register(Integration)
class IntegrationAdmin(admin.ModelAdmin):
    form = IntegrationAdminForm
    list_display = (
        "id",
        "type",
        "owner",
        "name",
        "enabled",
        "default_route_link",
        "api_key",  # ToDo: Add an endpoint to manage API Keys to manage them through the Portal UI?
        "created_at",
    )
    list_select_related = ("type", "owner")
    list_filter = (
        "owner",
        "type",
        DefaultRouteStateFilter,
        "created_at",
    )
    search_fields = (
        "id",
        "name",
        "owner__name",
        "type__name",
        "type__value",
    )
    # AJAX search box instead of a <select> of every Route (needs RouteAdmin.search_fields).
    autocomplete_fields = ("default_route",)
    readonly_fields = ("routes_as_provider_panel", "routes_as_destination_panel")
    inlines = [
        DispatcherDeploymentInline,
    ]

    def get_queryset(self, request):
        # Pull the default route's name in via the join rather than via
        # ``list_select_related``. Constructing a ``Route`` instance runs
        # ``ChangeLogMixin.__init__``, which resolves the route's first
        # provider (a query) before Django populates the FK cache -- so it
        # costs a query per row that select_related cannot prevent (see
        # GundiTraceAdmin.get_queryset for the same issue with Source).
        # Annotating avoids building the instances at all.
        return super().get_queryset(request).annotate(
            _default_route_name=F("default_route__name")
        )

    @admin.display(description="Default route", ordering="default_route__name")
    def default_route_link(self, obj):
        if obj.default_route_id is None:
            return "—"
        url = reverse("admin:integrations_route_change", args=[obj.default_route_id])
        return format_html('<a href="{}">{}</a>', url, obj._default_route_name)

    @admin.display(description="Routes as provider")
    def routes_as_provider_panel(self, obj):
        """provider → route → destinations, default marked ★ (spec §5.3)."""
        if obj.pk is None:
            return "—"
        routes = list(obj.routing_rules_by_provider.order_by("name").values("pk", "name"))
        if not routes:
            return "Not a provider on any route (default route not required)."
        destinations = _integration_labels_by_route(RouteDestination, [r["pk"] for r in routes])
        rows = [
            (
                "★ " if route["pk"] == obj.default_route_id else "",
                reverse("admin:integrations_route_change", args=[route["pk"]]),
                route["name"],
                destinations.get(route["pk"], "no destinations"),
            )
            for route in routes
        ]
        return format_html("<ul>{}</ul>", format_html_join("", '<li>{}<a href="{}">{}</a> → {}</li>', rows))

    @admin.display(description="Routes as destination")
    def routes_as_destination_panel(self, obj):
        if obj.pk is None:
            return "—"
        routes = list(obj.routing_rules_by_destination.order_by("name").values("pk", "name"))
        if not routes:
            return "Not a destination on any route."
        providers = _integration_labels_by_route(RouteProvider, [r["pk"] for r in routes])
        rows = [
            (
                providers.get(route["pk"], "no providers"),
                reverse("admin:integrations_route_change", args=[route["pk"]]),
                route["name"],
            )
            for route in routes
        ]
        return format_html("<ul>{}</ul>", format_html_join("", '<li>{} → <a href="{}">{}</a></li>', rows))

    def delete_model(self, request, obj):
        try:  # Is there a deployment?
            deployment = obj.dispatcher_by_integration
        except Integration.dispatcher_by_integration.RelatedObjectDoesNotExist:
            pass  # No deployment to delete
        else:   # Delete deployment
            if deployment.status not in [  # Check if it's in a safe state to delete
                deployments.models.DispatcherDeployment.Status.COMPLETE,
                deployments.models.DispatcherDeployment.Status.ERROR
            ]:
                msg = f"Warning: related dispatcher cannot be deleted in the current status. You can delete it later from the deployments page."
                messages.add_message(request, messages.WARNING, message=msg)
            elif Integration.objects.filter(additional__topic=deployment.topic_name).count() > 1:  # Check if the topic is being used by other integrations
                msg = f"Warning: related dispatcher won't be deleted as it's being used by other integrations."
                messages.add_message(request, messages.WARNING, message=msg)
            else:  # It's safe to delete it
                deployment.delete()

        try:  # Delete the integration
            super().delete_model(request, obj)
        except Exception as e:
            messages.add_message(request, messages.ERROR, message=f"Error deleting integration {obj.pk}: {type(e).__name__}: {e}")

    def delete_queryset(self, request, queryset):
        # Overwritten to call deployment.delete() in bulk deletion
        for obj in queryset:
            self.delete_model(request, obj)


@admin.register(IntegrationStatus)
class IntegrationStatusAdmin(admin.ModelAdmin):
    list_display = (
        "integration",
        "integration_id",
        "status",
        "last_delivery",
        "updated_at",
    )
    list_filter = (
        "status",
        "integration__type",
    )
    search_fields = (
        "integration__id",
        "integration__owner__name",
        "integration__name",
    )


@admin.register(IntegrationMetrics)
class IntegrationMetricsAdmin(admin.ModelAdmin):
    list_display = (
        "integration",
        "integration_id",
        "data_frequency_minutes_min",
        "data_frequency_minutes_max",
        "data_frequency_minutes",
        "created_at",
    )
    list_filter = (
        "integration__type",
    )
    search_fields = (
        "integration__id",
        "integration__owner__name",
        "integration__name",
    )


@admin.register(HealthCheckSettings)
class HealthCheckSettingsAdmin(admin.ModelAdmin):
    list_display = (
        "integration",
        "integration_id",
        "error_count_threshold",
        "time_window_minutes",
        "updated_at",
    )
    search_fields = (
        "integration__id",
        "integration__owner__name",
        "integration__name",
    )


@admin.register(IntegrationConfiguration)
class IntegrationConfigurationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "integration",
        "action",
    )
    list_filter = (
        "integration__owner",
        "integration__type",
        "action__type",
    )
    search_fields = (
        "integration__name",
        "integration__owner__name",
        "action__name",
    )


@admin.register(WebhookConfiguration)
class WebhookConfigurationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "integration",
        "webhook",
    )
    list_filter = (
        "integration__owner",
        "integration__type",
    )
    search_fields = (
        "integration__name",
        "integration__owner__name",
        "webhook__name",
    )


class RouteProviderInlineFormSet(BaseInlineFormSet):
    """Refuse (as a form error, before anything is saved) a provider change on
    a route -- removal or addition -- when that would leave a default route
    ambiguous (spec §5.1). Raising from the pre_delete/post_save receiver
    instead would poison the admin's surrounding transaction (removal) or
    surface as a 500 from the change form (addition)."""

    def clean(self):
        super().clean()
        route = self.instance
        if route.pk is None:
            return
        for form in self.deleted_forms:
            link = form.instance
            if link.pk is None:
                continue
            try:
                decide_default_route(link.integration, leaving_route=route)
            except AmbiguousDefaultRouteError as error:
                raise ValidationError(str(error))
        for form in self.forms:
            if form in self.deleted_forms:
                continue
            link = form.instance
            if link.pk is not None:
                continue  # an existing link, not a new one -- nothing is joining
            integration = form.cleaned_data.get("integration") if form.cleaned_data else None
            if integration is None:
                continue
            try:
                decide_default_route(integration, joining_route=route)
            except AmbiguousDefaultRouteError as error:
                raise ValidationError(str(error))


class RouteProviderInline(admin.TabularInline):
    model = Route.data_providers.through
    formset = RouteProviderInlineFormSet
    # Without this, every inline row renders a <select> of *every* Integration,
    # and Integration.__str__ touches owner.name/type.name (not select_related),
    # making the Route change page an N+1 storm that times out in production.
    autocomplete_fields = ("integration",)


class RouteDestinationInline(admin.TabularInline):
    model = Route.destinations.through
    autocomplete_fields = ("integration",)


@admin.register(Route)
class RouteAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "owner",
        "providers_display",
        "destinations_display",
        "default_for_display",
    )
    list_filter = (
        "owner",
    )
    search_fields = (
        "id",
        "name",
    )
    # Render owner/configuration as AJAX search boxes instead of dropdowns that
    # eagerly load every Organization/RouteConfiguration on the change page.
    autocomplete_fields = (
        "owner",
        "configuration",
    )
    inlines = (
        RouteProviderInline,
        RouteDestinationInline,
    )
    list_select_related = ("owner",)
    readonly_fields = ("default_route_for_panel",)

    def get_queryset(self, request):
        # The three new columns walk M2M/reverse FK relations; prefetch so the
        # changelist stays at a flat query count.
        # Prefetch querysets use Integration.objects.all() rather than
        # .only("id", "name") -- Integration.__init__ does not query, so
        # instantiating full rows is cheap, and .only() here would conflict
        # with default_route_for_panel's select_related("type") on the same
        # cached queryset (deferred fields can't be select_related).
        return super().get_queryset(request).prefetch_related(
            Prefetch("data_providers", queryset=Integration.objects.all()),
            Prefetch("destinations", queryset=Integration.objects.all()),
            Prefetch("integrations_by_rule", queryset=Integration.objects.all()),
        )

    @admin.display(description="Providers")
    def providers_display(self, obj):
        return ", ".join(i.name for i in obj.data_providers.all()) or "—"

    @admin.display(description="Destinations")
    def destinations_display(self, obj):
        return ", ".join(i.name for i in obj.destinations.all()) or "—"

    @admin.display(description="Default for")
    def default_for_display(self, obj):
        return ", ".join(i.name for i in obj.integrations_by_rule.all()) or "—"

    @admin.display(description="Default route for")
    def default_route_for_panel(self, obj):
        """Integrations whose default this route is — the fact that matters before deleting it."""
        if obj.pk is None:
            return "—"
        rows = [
            (reverse("admin:integrations_integration_change", args=[i.pk]), i.name)
            for i in obj.integrations_by_rule.select_related("type").order_by("name")
        ]
        if not rows:
            return "No integration uses this route as its default."
        return format_html("<ul>{}</ul>", format_html_join("", '<li><a href="{}">{}</a></li>', rows))

    # -- default route refusals (spec §5.1) ---------------------------------
    # Deleting a route can be refused when a provider on it would be left with
    # an ambiguous default (AmbiguousDefaultRouteError). Turn that into an
    # admin message instead of a 500. There are two distinct refusal paths,
    # and BOTH are reachable -- this is not dead code:
    #
    # 1. get_deleted_objects() -- reassign_default_route (the FK's on_delete
    #    callable) can raise while Collector.collect() walks the FK from a
    #    provider whose *default_route* is one of the routes being deleted.
    #    Both the single-object delete view and the "Delete selected" action
    #    call get_deleted_objects() (which collects) to render the
    #    confirmation page *before* delete_model/delete_queryset ever run, so
    #    catching it here -- the same way Django itself turns a
    #    ProtectedError from collect() into a "protected" list instead of a
    #    500 -- stops the delete before anything is touched: nothing is
    #    deletable and the admin's own "cannot delete" path renders.
    #
    # 2. delete_model()/delete_queryset() -- a provider whose default_route is
    #    NOT one of the routes being deleted, but who is a provider on ≥2
    #    OTHER delivering routes among them, passes collection cleanly (its FK
    #    isn't touched) and only raises later, from pre_delete(RouteProvider)
    #    fired inside Collector.delete() while candidates are re-decided. The
    #    savepoint here keeps the admin's outer transaction usable after that
    #    aborted delete. IMPORTANT: by the time this refusal is caught, Django
    #    has already called log_deletion() and written a "deleted" LogEntry
    #    for the route -- that history entry is accepted as stale (the route
    #    in fact still exists); it does not affect ActivityLog, which is only
    #    written by a successful resolve_default_route() call.

    def get_deleted_objects(self, objs, request):
        try:
            return super().get_deleted_objects(objs, request)
        except AmbiguousDefaultRouteError as error:
            messages.error(request, str(error))
            return [], {}, set(), [str(error)]

    def delete_model(self, request, obj):
        try:
            with transaction.atomic():
                super().delete_model(request, obj)
        except AmbiguousDefaultRouteError as error:
            messages.error(request, str(error))

    def delete_queryset(self, request, queryset):
        try:
            with transaction.atomic():
                super().delete_queryset(request, queryset)
        except AmbiguousDefaultRouteError as error:
            messages.error(request, str(error))

    def response_delete(self, request, obj_display, obj_id):
        if Route.objects.filter(pk=obj_id).exists():  # refused above: no success message, back to the route
            return HttpResponseRedirect(reverse("admin:integrations_route_change", args=[obj_id]))
        return super().response_delete(request, obj_display, obj_id)


@admin.register(RouteConfiguration)
class RouteConfigAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
    )
    # Required so RouteAdmin can use ``configuration`` in autocomplete_fields.
    search_fields = (
        "id",
        "name",
    )


@admin.register(SourceFilter)
class SourceFilterAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "order_number",
        "type",
        "name",
        "description"
    )
    list_filter = (
        "type",
        "routing_rule",
    )


@admin.register(Source)
class SourceAdmin(SimpleHistoryAdmin):
    list_display = (
        "external_id",
        "integration",
        "created_at",
    )
    list_filter = (
        "integration__name",
        "integration__owner",
        "integration__type",
    )

    search_fields = (
        "external_id",
        "integration__name",
        "integration__owner__name",
        "integration__type__name",
    )

    date_hierarchy = "created_at"


@admin.register(SourceState)
class SourceStateAdmin(SimpleHistoryAdmin):
    list_display = (
        "source",
        "updated_at",
        "data",
    )


@admin.register(SourceConfiguration)
class SourceConfigurationAdmin(SimpleHistoryAdmin):
    list_display = (
        "name",
        "updated_at",
        "data",
    )


@admin.register(GundiTrace)
class GundiTraceAdmin(SimpleHistoryAdmin):
    # GundiTrace grows roughly proportionally to delivered observations.
    # The default admin paginator runs COUNT(*) on every changelist render,
    # which is the incident this PR was opened to fix. EstimatedCountPaginator
    # uses pg_class.reltuples for the unfiltered changelist (cheap planner
    # read) and falls back to the exact count when filters are applied.
    paginator = EstimatedCountPaginator
    # Suppresses the *secondary* full-table total shown next to a filtered
    # count. Doesn't replace the paginator's primary count — that's the
    # job of ``paginator`` above.
    show_full_result_count = False
    # ``list_select_related = True`` followed only ``data_provider`` -- a bare
    # select_related() skips *nullable* FKs, so ``destination``, ``source`` and
    # ``created_by`` were all dereferenced per row, and Integration/Source
    # ``__str__`` walked owner/type/integration on top of that: ~7 queries per
    # row, 356 for a 50-row page. ``source`` is deliberately absent -- see
    # ``source_link`` for why loading Source rows is not made cheaper by
    # select_related.
    list_select_related = (
        "data_provider",
        "data_provider__owner",
        "data_provider__type",
        "destination",
        "destination__owner",
        "destination__type",
        "created_by",
    )
    list_display = (
        "pk",
        "object_id",
        "related_to",
        "object_type",
        "data_provider",
        "source_link",
        "destination",
        "external_id",
        "created_at",
        "delivered_at",
        "object_updated_at",
        "last_update_delivered_at",
        "is_duplicate",
        "has_error",
        "created_by",
    )
    search_fields = (
        "object_id",
        "related_to",
        "external_id",
        "data_provider__id",
        "source__id",
        "data_provider__name",
        "data_provider__owner__name",
        "data_provider__type__name",
        "destination__id",
        "destination__name",
        "destination__owner__name",
        "destination__type__name",
    )
    # No ``date_hierarchy``: it issues ``SELECT DISTINCT DATE_TRUNC(...)`` over
    # the whole filtered queryset on every render, which Postgres can only
    # answer with a sequential scan of this -- the largest -- table. The
    # ``created_at`` filter below covers the same need for free.
    list_filter = (
        ("created_at", CustomDateFilter),
        ("delivered_at", CustomDateFilter),
        "has_error",
        "is_duplicate",
        "object_type",
        # Both point at IntegrationType, so without explicit titles the
        # sidebar shows two identical "By Integration Type" panels.
        ("data_provider__type", titled_filter("Provider type")),
        ("destination__type", titled_filter("Destination type")),
    )

    def get_queryset(self, request):
        # Pull the source's external id in via the join rather than via
        # ``list_select_related``. Constructing a ``Source`` instance runs
        # ``ChangeLogMixin.__init__``, which resolves the instance's related
        # integration *before* Django populates the FK cache -- so it costs a
        # query per row that select_related cannot prevent. Annotating avoids
        # building the instances at all.
        return super().get_queryset(request).annotate(
            _source_external_id=F("source__external_id")
        )

    @admin.display(description="Source", ordering="source__external_id")
    def source_link(self, obj):
        if not obj.source_id:
            return self.get_empty_value_display()
        return format_html(
            '<a href="{}">{}</a>',
            reverse("admin:integrations_source_change", args=[obj.source_id]),
            obj._source_external_id,
        )


# Override the PeriodicTaskAdmin to allow searching and filtering by integration fields
class GundiPeriodicTaskAdmin(PeriodicTaskAdmin):
    search_fields = (
        "name",
        "configurations_by_periodic_task__integration__id",
        "configurations_by_periodic_task__integration__name",
    )
    list_filter = (
        "enabled",
        "configurations_by_periodic_task__integration__type",
        "configurations_by_periodic_task__integration__owner",
        "task",
    )
admin.site.unregister(PeriodicTask)
admin.site.register(PeriodicTask, GundiPeriodicTaskAdmin)
