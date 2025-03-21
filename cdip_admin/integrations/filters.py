from django.db.models import Subquery
from django.utils.translation import ugettext_lazy as _
import django_filters
from django_filters import rest_framework as django_filters_rest

from activity_log.models import ActivityLog
from core.permissions import IsGlobalAdmin, IsOrganizationMember
from integrations.models import (
    DeviceState,
    DeviceGroup,
    Device,
    Organization,
    InboundIntegrationType,
    InboundIntegrationConfiguration,
    OutboundIntegrationConfiguration,
    OutboundIntegrationType,
    BridgeIntegration,
    Integration,
    IntegrationType,
    get_user_integrations_qs,
    Source, Route, GundiTrace, IntegrationAction, IntegrationStatus, ConnectionStatus, filter_connections_by_status
)
from core.widgets import CustomBooleanWidget, HasErrorBooleanWidget
from django.db.models import Q
from django.contrib.postgres.aggregates import ArrayAgg


# set the organization filter options to the organizations that user is member of
def organization_filter(request):
    qs = Organization.objects.order_by("name")
    if not IsGlobalAdmin.has_permission(None, request, None):
        return IsOrganizationMember.filter_queryset_for_user(qs, request.user, "name")
    return qs


# set the type filter options to the types relevant to the organizations that user is member of
def inbound_type_filter(request):
    type_qs = InboundIntegrationType.objects.all()
    if not IsGlobalAdmin.has_permission(None, request, None):
        org_qs = IsOrganizationMember.filter_queryset_for_user(
            Organization.objects.all(), request.user, "name"
        )
        types = Device.objects.filter(
            inbound_configuration__owner__in=org_qs
        ).values_list("inbound_configuration__type")
        type_qs = type_qs.filter(
            inboundintegrationconfiguration__type__in=types
        ).distinct()
    return type_qs


def outbound_integration_filter(request):
    qs = OutboundIntegrationConfiguration.objects.order_by("name")
    if not IsGlobalAdmin.has_permission(None, request, None):
        return IsOrganizationMember.filter_queryset_for_user(qs, request.user, "name")
    return qs


# set the type filter options to the types relevant to the organizations that user is member of
def outbound_type_filter(request):
    type_qs = OutboundIntegrationType.objects.all()
    if not IsGlobalAdmin.has_permission(None, request, None):
        org_qs = IsOrganizationMember.filter_queryset_for_user(
            Organization.objects.all(), request.user, "name"
        )
        type_qs = type_qs.filter(
            outboundintegrationconfiguration__owner__in=org_qs
        ).distinct()
    return type_qs


class DeviceStateFilter(django_filters.FilterSet):

    external_id = django_filters.CharFilter(
        field_name="device__external_id",
        lookup_expr="icontains",
        label=_("External ID"),
    )

    organization = django_filters.ModelChoiceFilter(
        queryset=organization_filter,
        field_name="device__inbound_configuration__owner",
        to_field_name="name",
        empty_label=_("Owners"),
    )

    inbound_config_type = django_filters.ModelChoiceFilter(
        queryset=inbound_type_filter,
        field_name="device__inbound_configuration__type",
        to_field_name="name",
        empty_label=_("Types"),
    )

    class Meta:
        model = DeviceState
        fields = (
            "organization",
            "inbound_config_type",
            "external_id",
        )

    @property
    def qs(self):
        qs = super().qs
        if not IsGlobalAdmin.has_permission(None, self.request, None):
            return IsOrganizationMember.filter_queryset_for_user(
                qs, self.request.user, "device__inbound_configuration__owner__name"
            )
        else:
            return qs


class DeviceGroupFilter(django_filters.FilterSet):

    device_group = django_filters.CharFilter(
        field_name="name", lookup_expr="icontains", label="Name"
    )

    organization = django_filters.ModelChoiceFilter(
        queryset=organization_filter,
        field_name="owner",
        to_field_name="name",
        empty_label=_("All Organizations"),
    )

    destinations = django_filters.ModelChoiceFilter(
        queryset=outbound_integration_filter,
        field_name="destinations",
        to_field_name="name",
        empty_label=_("All Destinations"),
    )

    class Meta:
        model = DeviceGroup
        fields = ("organization", "device_group", "destinations")

    def __init__(self, *args, **kwargs):
        # this can appropriately update the ui filter elements
        # check for stored values and set form values accordingly
        super(DeviceGroupFilter, self).__init__(*args, **kwargs)
        if "owner_filter" in self.request.session:
            self.form.initial["organization"] = self.request.session["owner_filter"]

    @property
    def qs(self):
        qs = super().qs
        if "organization" in self.data:
            if not self.data.get("organization"):
                self.request.session.pop("owner_filter", None)
            else:
                self.request.session["owner_filter"] = self.data["organization"]
        if not IsGlobalAdmin.has_permission(None, self.request, None):
            return IsOrganizationMember.filter_queryset_for_user(
                qs, self.request.user, "owner__name"
            )
        if "owner_filter" in self.request.session:
            return qs.filter(owner__name=self.request.session["owner_filter"])
        return qs


class DeviceFilter(django_filters.FilterSet):

    external_id = django_filters.CharFilter(
        field_name="external_id", lookup_expr="icontains", label=_("External ID")
    )

    organization = django_filters.ModelChoiceFilter(
        queryset=organization_filter,
        field_name="inbound_configuration__owner",
        to_field_name="name",
        empty_label=_("Owners"),
    )

    inbound_config_type = django_filters.ModelChoiceFilter(
        queryset=inbound_type_filter,
        field_name="inbound_configuration__type",
        to_field_name="name",
        empty_label=_("Types"),
    )

    class Meta:
        model = Device
        fields = (
            "organization",
            "inbound_config_type",
            "external_id",
        )

    def __init__(self, *args, **kwargs):
        # this can appropriately update the ui filter elements
        # check for stored values and set form values accordingly
        super(DeviceFilter, self).__init__(*args, **kwargs)
        if "owner_filter" in self.request.session:
            self.form.initial["organization"] = self.request.session["owner_filter"]

    @property
    def qs(self):
        qs = super().qs
        if "organization" in self.data:
            if not self.data.get("organization"):
                self.request.session.pop("owner_filter", None)
            else:
                self.request.session["owner_filter"] = self.data["organization"]
        if not IsGlobalAdmin.has_permission(None, self.request, None):
            return IsOrganizationMember.filter_queryset_for_user(
                qs, self.request.user, "owner__name"
            )
        if "owner_filter" in self.request.session:
            return qs.filter(
                inbound_configuration__owner__name=self.request.session["owner_filter"]
            )
        return qs


def filter_has_error_key(queryset, name, value):
    fn = queryset.filter if value else queryset.exclude
    return fn(state__has_key='error')


class InboundIntegrationFilter(django_filters.FilterSet):

    name = django_filters.CharFilter(
        field_name="name", lookup_expr="icontains", label=_("Name")
    )

    organization = django_filters.ModelChoiceFilter(
        queryset=organization_filter,
        field_name="owner",
        to_field_name="name",
        empty_label=_("All Owners"),
    )

    inbound_config_type = django_filters.ModelChoiceFilter(
        queryset=inbound_type_filter,
        field_name="type",
        to_field_name="name",
        empty_label=_("All Types"),
    )

    enabled = django_filters.BooleanFilter(widget=CustomBooleanWidget)

    has_errors =  django_filters.BooleanFilter(widget=HasErrorBooleanWidget,
        field_name='state',
        method=filter_has_error_key
       )

    class Meta:
        model = InboundIntegrationConfiguration
        fields = ("organization", "inbound_config_type", "name", "enabled")

    def __init__(self, *args, **kwargs):
        # this can appropriately update the ui filter elements
        # check for stored values and set form values accordingly
        super(InboundIntegrationFilter, self).__init__(*args, **kwargs)
        if "owner_filter" in self.request.session:
            self.form.initial["organization"] = self.request.session["owner_filter"]

    @property
    def qs(self):
        qs = super().qs
        if "organization" in self.data:
            if not self.data.get("organization"):
                self.request.session.pop("owner_filter", None)
            else:
                self.request.session["owner_filter"] = self.data["organization"]
        if not IsGlobalAdmin.has_permission(None, self.request, None):
            return IsOrganizationMember.filter_queryset_for_user(
                qs, self.request.user, "owner__name"
            )
        if "owner_filter" in self.request.session:
            return qs.filter(owner__name=self.request.session["owner_filter"])
        return qs


class OutboundIntegrationFilter(django_filters.FilterSet):
    def affected_destinations_filter(self, request, name, value):
        return OutboundIntegrationConfiguration.objects.filter(
            Q(devicegroup__inbound_integration_configurations__type__name__icontains=value) |
            Q(devicegroup__devices__inbound_configuration__type__name__icontains=value)).order_by('id').distinct('id')

    name = django_filters.CharFilter(
        field_name="name", lookup_expr="icontains", label=_("Name")
    )

    organization = django_filters.ModelChoiceFilter(
        queryset=organization_filter,
        field_name="owner",
        to_field_name="name",
        empty_label=_("All Owners"),
    )

    outbound_config_type = django_filters.ModelChoiceFilter(
        queryset=outbound_type_filter,
        field_name="type",
        to_field_name="name",
        empty_label=_("All Outbound Types"),
    )

    enabled = django_filters.BooleanFilter(widget=CustomBooleanWidget)

    outbound_affected_destinations = django_filters.ModelChoiceFilter(
        queryset=inbound_type_filter,
        method='affected_destinations_filter',
        to_field_name="name",
        empty_label=_("All Inbound Integration Types"),
        field_name="name",
    )

    class Meta:
        model = OutboundIntegrationConfiguration
        fields = ("organization", "name", "outbound_config_type", "outbound_affected_destinations", "enabled")

    def __init__(self, *args, **kwargs):
        # this can appropriately update the ui filter elements
        # check for stored values and set form values accordingly
        super(OutboundIntegrationFilter, self).__init__(*args, **kwargs)
        if "owner_filter" in self.request.session:
            self.form.initial["organization"] = self.request.session["owner_filter"]

    @property
    def qs(self):
        qs = super().qs
        if "organization" in self.data:
            if not self.data.get("organization"):
                self.request.session.pop("owner_filter", None)
            else:
                self.request.session["owner_filter"] = self.data["organization"]

        # if "outbound_affected_destinations" in self.data:
        #     # get all device groups associated with the selected inbound type
        #     selected_inbound_type = self.data["outbound_affected_destinations"]
        #     associated_device_groups = InboundIntegrationConfiguration.objects.filter_by(selected_inbound_type)
        #     # get all destination(s) associated with the device groups
        #     self.data["outbound_affected_destinations"] = associated_device_groups

        if not IsGlobalAdmin.has_permission(None, self.request, None):
            return IsOrganizationMember.filter_queryset_for_user(
                qs, self.request.user, "owner__name"
            )
        if "owner_filter" in self.request.session:
            return qs.filter(owner__name=self.request.session["owner_filter"])
        return qs


class BridgeIntegrationFilter(django_filters.FilterSet):
    enabled = django_filters.BooleanFilter(widget=CustomBooleanWidget)

    class Meta:
        model = BridgeIntegration
        fields = ("enabled",)


class CharInFilter(django_filters_rest.BaseInFilter, django_filters_rest.CharFilter):
    pass


class IntegrationFilter(django_filters_rest.FilterSet):
    action_type = django_filters_rest.CharFilter(field_name="type__actions__type", lookup_expr="iexact", distinct=True)
    action_type__in = CharInFilter(field_name="type__actions__type", lookup_expr="in", distinct=True)
    action = django_filters_rest.CharFilter(field_name="type__actions__value", lookup_expr="iexact", )
    action__in = CharInFilter(field_name="type__actions__value", lookup_expr="in", )
    status = django_filters_rest.CharFilter(field_name="status__status", lookup_expr="iexact", )
    status__in = CharInFilter(field_name="status__status", lookup_expr="in", )
    is_used_as_provider = django_filters_rest.BooleanFilter(method="filter_is_used_as_provider")

    class Meta:
        model = Integration
        fields = {
            'id': ['exact', 'in'],
            'base_url': ['exact', 'iexact', 'in'],
            'enabled': ['exact', 'in'],
            'type': ['exact', 'in'],
            'owner': ['exact', 'in'],
        }

    def filter_is_used_as_provider(self, queryset, name, value):
        # Get integrations set as provider in any route
        return queryset.filter(routing_rules_by_provider__isnull=(not value))


class ConnectionFilter(django_filters_rest.FilterSet):
    provider_type = django_filters_rest.CharFilter(field_name="type__value", lookup_expr="iexact")
    provider_type__in = CharInFilter(field_name="type__value", lookup_expr="in")
    destination_type = django_filters_rest.CharFilter(method='filter_by_destination_type')
    destination_type__in = CharInFilter(method='filter_by_destination_type', lookup_expr="in")
    destination_url = django_filters_rest.CharFilter(method='filter_by_destination_url')
    destination_url__in = CharInFilter(method='filter_by_destination_url', lookup_expr="in")
    destination_id = django_filters_rest.UUIDFilter(method='filter_by_destination_id')
    source_id = django_filters_rest.UUIDFilter(method='filter_by_source_id')
    status = django_filters_rest.CharFilter(method='filter_by_status')

    class Meta:
        model = Integration
        fields = {
            'owner': ['exact', 'in'],
        }

    def filter_by_destination_type(self, queryset, name, value):
        destinations = value if isinstance(value, list) else [value]
        # Annotate the destination types
        qs_with_destination_types = queryset.annotate(
            destination_types=ArrayAgg(
                "routing_rules_by_provider__destinations__type__value",
                filter=Q(routing_rules_by_provider__destinations__isnull=False)
            )
        )
        # Filter integrations having at least one destination with a type matching at least one of the provided values
        return qs_with_destination_types.filter(destination_types__overlap=destinations)

    def filter_by_destination_url(self, queryset, name, value):
        destination_urls = value if isinstance(value, list) else [value]
        # Annotate the destination urls
        qs_with_destination_urls = queryset.annotate(
            destination_urls=ArrayAgg(
                "routing_rules_by_provider__destinations__base_url",
                filter=Q(routing_rules_by_provider__destinations__isnull=False)
            )
        )
        # Filter integrations having at least one destination with an url matching at least one of the provided values
        return qs_with_destination_urls.filter(destination_urls__overlap=destination_urls)

    def filter_by_destination_id(self, queryset, name, value):
        # Filter integrations having a destination with id matching the provided value
        return queryset.filter(
            routing_rules_by_provider__destinations__id=str(value)
        )

    def filter_by_source_id(self, queryset, name, value):
        # Filter integrations having at source with id matching the provided value
        return queryset.filter(
            sources_by_integration__id=str(value)
        )

    def filter_by_status(self, queryset, name, value):
        return filter_connections_by_status(queryset=queryset, status=value)


class IntegrationTypeFilter(django_filters_rest.FilterSet):
    action_type = django_filters_rest.CharFilter(field_name="actions__type", lookup_expr="iexact", distinct=True)
    action_type__in = CharInFilter(field_name="actions__type", lookup_expr="in", distinct=True)
    action = django_filters_rest.CharFilter(field_name="actions__value", lookup_expr="iexact", )
    action__in = CharInFilter(field_name="actions__value", lookup_expr="in", )
    in_use_only = django_filters_rest.BooleanFilter(method='filter_types_in_use_only')
    has_webhook = django_filters_rest.BooleanFilter(method="filter_types_with_webhook")
    is_provider = django_filters_rest.BooleanFilter(method="filter_types_is_provider")

    class Meta:
        model = IntegrationType
        fields = {
            'value': ['exact', 'iexact', 'in'],
        }

    def filter_types_in_use_only(self, queryset, name, value):
        if value:  # in_use_only = True
            # Get only the types under use in integrations related to the current user
            user_integrations = get_user_integrations_qs(user=self.request.user)
            return queryset.filter(
                id__in=Subquery(user_integrations.values("type").distinct())
            )
        return queryset

    def filter_types_with_webhook(self, queryset, name, value):
        return queryset.filter(~Q(webhook__isnull=value))

    def filter_types_is_provider(self, queryset, name, value):
        # Types having pull actions or webhooks can be data providers
        is_provider_q = Q(actions__type=IntegrationAction.ActionTypes.PULL_DATA.value) | Q(webhook__isnull=False)
        if value:
            return queryset.filter(is_provider_q)
        else:
            return queryset.filter(~is_provider_q)


class SourceFilter(django_filters_rest.FilterSet):
    provider = django_filters_rest.CharFilter(field_name="integration__id", lookup_expr="iexact")
    provider_type = django_filters_rest.CharFilter(field_name="integration__type__value", lookup_expr="iexact")
    provider_type__in = CharInFilter(field_name="integration__type__value", lookup_expr="in")
    destination_type = django_filters_rest.CharFilter(method='filter_by_destination_type')
    destination_type__in = CharInFilter(method='filter_by_destination_type', lookup_expr="in")
    destination_url = django_filters_rest.CharFilter(method='filter_by_destination_url')
    destination_url__in = CharInFilter(method='filter_by_destination_url', lookup_expr="in")
    owner = django_filters_rest.CharFilter(field_name="integration__owner__id", lookup_expr="iexact")
    owner__in = CharInFilter(field_name="integration__owner__id", lookup_expr="in")

    class Meta:
        model = Source
        fields = {
            'external_id': ['exact', 'iexact', 'in'],
        }

    def filter_by_destination_type(self, queryset, name, value):
        destinations = value if isinstance(value, list) else [value]
        # Annotate the destination types
        qs_with_destination_types = queryset.annotate(
            destination_types=ArrayAgg(
                "integration__routing_rules_by_provider__destinations__type__value",
                filter=Q(integration__routing_rules_by_provider__destinations__isnull=False)
            )
        )
        # Filter integrations having at least one destination with a type matching at least one of the provided values
        return qs_with_destination_types.filter(destination_types__overlap=destinations)

    def filter_by_destination_url(self, queryset, name, value):
        destination_urls = value if isinstance(value, list) else [value]
        # Annotate the destination urls
        qs_with_destination_urls = queryset.annotate(
            destination_urls=ArrayAgg(
                "integration__routing_rules_by_provider__destinations__base_url",
                filter=Q(integration__routing_rules_by_provider__destinations__isnull=False)
            )
        )
        # Filter integrations having at least one destination with an url matching at least one of the provided values
        return qs_with_destination_urls.filter(destination_urls__overlap=destination_urls)


class RouteFilter(django_filters_rest.FilterSet):
    provider = django_filters_rest.CharFilter(
        field_name="data_providers__id",
        lookup_expr="iexact",
    )
    provider__in = CharInFilter(
        field_name="data_providers__id",
        lookup_expr="in",
    )
    destination = django_filters_rest.CharFilter(
        field_name="destinations__id",
        lookup_expr="iexact",
    )
    destination__in = CharInFilter(
        field_name="destinations__id",
        lookup_expr="in",
    )
    destination_url = django_filters_rest.CharFilter(
        method='filter_by_destination_url'
    )
    destination_url__in = CharInFilter(
        method='filter_by_destination_url',
        lookup_expr="in"
    )

    class Meta:
        model = Route
        fields = {
            'id': ['exact', 'iexact', 'in'],
        }

    def filter_by_destination_url(self, queryset, name, value):
        destination_urls = value if isinstance(value, list) else [value]
        # Annotate the destination urls
        qs_with_destination_urls = queryset.annotate(
            destination_urls=ArrayAgg(
                "destinations__base_url",
                filter=Q(destinations__isnull=False)
            )
        )
        # Filter integrations having at least one destination with an url matching at least one of the provided values
        return qs_with_destination_urls.filter(destination_urls__overlap=destination_urls)


class GundiTraceFilter(django_filters_rest.FilterSet):

    class Meta:
        model = GundiTrace
        fields = {
            'object_id': ['exact', ],
            'related_to': ['exact', ],
            'data_provider': ['exact', ],
            'destination': ['exact', ],
            'external_id': ['exact', ]
        }


class ActivityLogFilter(django_filters_rest.FilterSet):
    log_level = django_filters_rest.CharFilter(method='filter_by_log_level')
    log_type = django_filters_rest.CharFilter(
        field_name="log_type",
        lookup_expr="exact",
    )
    origin = django_filters_rest.CharFilter(
        field_name="origin",
        lookup_expr="exact",
    )
    integration = django_filters_rest.CharFilter(
        field_name="integration__id",
        lookup_expr="exact",
    )
    integration__in = CharInFilter(
        field_name="integration__id",
        lookup_expr="in",
    )
    value = django_filters_rest.CharFilter(
        field_name="value",
        lookup_expr="exact",
    )
    from_date = django_filters_rest.DateTimeFilter(field_name="created_at", lookup_expr="gte")
    to_date = django_filters_rest.DateTimeFilter(field_name="created_at", lookup_expr="lte")
    is_reversible = django_filters_rest.BooleanFilter(field_name="is_reversible")

    class Meta:
        model = ActivityLog
        exclude = ["title", "details", "revert_data", ]

    def filter_by_log_level(self, queryset, name, value):
        return queryset.filter(log_level__gte=int(value))
