import django_filters

from integrations.models import InboundIntegrationConfiguration, DeviceState

from core.permissions import IsServiceAccount, IsGlobalAdmin, IsOrganizationMember
from organizations.models import Organization

class OrganizationFilter(django_filters.FilterSet):
    class Meta:
        model = Organization
        fields = {
            'name': ['contains']
        }

    @property
    def qs(self):
        queryset = super().qs

        requestor = getattr(self.request, 'user', None)
        if not requestor:
            return qs.none

        if not requestor.has_perm('auth.global_admin'):
            queryset = queryset.filter(accountprofile__user=requestor)

        return queryset


class InboundIntegrationConfigurationFilter(django_filters.FilterSet):

    type_slug = django_filters.CharFilter(
        field_name='type__slug',
        lookup_expr='exact'
    )

    type_id = django_filters.UUIDFilter(
        field_name='type__id',
        lookup_expr='exact'
    )

    owner_id = django_filters.UUIDFilter(
        field_name='owner__id',
        lookup_expr='exact'
    )

    enabled = django_filters.BooleanFilter(field_name='enabled', lookup_expr='exact')

    class Meta:
        model = InboundIntegrationConfiguration
        fields = ()

    @property
    def qs(self):
        filtered_qs = super().qs

        if IsGlobalAdmin.has_permission(None, self.request, None):
            return filtered_qs

        requestor = getattr(self.request, 'user', None)

        if IsServiceAccount.has_permission(None, self.request, None):
            client_id = IsServiceAccount.get_client_id(self.request)
            client_profile = IsServiceAccount.get_client_profile(client_id)
            filtered_qs = filtered_qs.filter(type_id=client_profile.type.id)
            return filtered_qs

        filtered_qs = filtered_qs.filter(owner__accountprofile__user=requestor,
                                         owner__accountprofile__role='admin')
        return filtered_qs


class DeviceStateFilter(django_filters.FilterSet):

    inbound_config_id = django_filters.UUIDFilter(
        field_name='device__inbound_configuration__id',
        lookup_expr='exact'
    )

    class Meta:
        model = DeviceState
        fields = ()
