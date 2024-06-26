from django.conf.urls import url
from django.urls import path, include
from rest_framework_swagger.views import get_swagger_view
from api.views import *

schema_view = get_swagger_view(title="CDIP ADMIN API")

urlpatterns = [
    path("v1.0/public", public),
    path("v1.0/devices", DeviceListView.as_view(), name="device_list_api"),
    path("v1.0/devices/<pk>", DeviceView.as_view(), name="device_detail_api"),
    # path('v1.0/devices/<device_id>/destinations', get_destinations_for_device),
    # path('v1.0/devices/outbound/configuration/<integration_id>', get_device_list_by_outbound_configuration),
    path(
        "v1.0/devices/states/",
        DeviceStateListView.as_view(),
        name="device_state_list_api",
    ),
    path(
        "v1.0/devices/states/update/<integration_id>", update_inbound_integration_state
    ),
    path(
        "v1.0/organizations", OrganizationsListView.as_view(), name="organization_list"
    ),
    path(
        "v1.0/organizations/<pk>",
        OrganizationDetailsView.as_view(),
        name="organization_detail",
    ),
    path(
        "v1.0/integrations/inbound/<integration_id>/devices",
        IntegrationDeviceView.as_view(),
        name="integration_device_list_api",
    ),
    path(
        "v1.0/integrations/inbound/types",
        InboundIntegrationTypeListView.as_view(),
        name="inboundintegrationtype_list",
    ),
    path(
        "v1.0/integrations/inbound/types/<pk>",
        InboundIntegrationTypeDetailsView.as_view(),
        name="inboundintegrationtype_detail",
    ),
    path(
        "v1.0/integrations/inbound/configurations",
        InboundIntegrationConfigurationListView.as_view(),
        name="inboundintegrationconfiguration_list",
    ),
    path(
        "v1.0/integrations/inbound/configurations/ceres_tag",
        CeresTagIdentifiersListView.as_view(),
        name="inboundintegration_cerestag_list",
    ),
    path(
        "v1.0/integrations/inbound/configurations/<pk>",
        InboundIntegrationConfigurationDetailsView.as_view(),
        name="inboundintegrationconfigurations_detail",
    ),
    path(
        "v1.0/integrations/outbound/types",
        OutboundIntegrationTypeListView.as_view(),
        name="outboundintegrationtype_list",
    ),
    path(
        "v1.0/integrations/outbound/types/<pk>",
        OutboundIntegrationTypeDetailsView.as_view(),
        name="outboundintegrationtype_detail",
    ),
    path(
        "v1.0/integrations/outbound/configurations",
        OutboundIntegrationConfigurationListView.as_view(),
        name="outboundintegrationconfiguration_list",
    ),
    path(
        "v1.0/integrations/outbound/configurations/<pk>",
        OutboundIntegrationConfigurationDetailsView.as_view(),
        name="outboundintegrationconfigurations_detail",
    ),
    path(
        "v1.0/integrations/bridges",
        BridgeIntegrationListView.as_view(),
        name="bridge_integration-list-view",
    ),
    path(
        "v1.0/integrations/bridges/<pk>",
        BridgeIntegrationView.as_view(),
        name="bridge-integration-view",
    ),
    url(r"^docs/", schema_view)
]
