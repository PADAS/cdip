from django.urls import path

from . import views

urlpatterns = [
    path("devices/<uuid:module_id>", views.device_detail, name="device_detail"),
    path(
        "devices/<uuid:module_id>/edit",
        views.DeviceUpdateView.as_view(),
        name="device_update",
    ),
    path("devices", views.DeviceList.as_view(), name="device_list"),
    path("devices/add", views.DeviceAddView.as_view(), name="device_add"),
    path(
        "devicegroups/<uuid:module_id>",
        views.DeviceGroupDetail.as_view(),
        name="device_group",
    ),
    path("devicegroups", views.DeviceGroupListView.as_view(), name="device_group_list"),
    path("devicegroups/add", views.DeviceGroupAddView.as_view(), name="device_group_add"),
    path(
        "devicegroups/<uuid:device_group_id>/edit",
        views.DeviceGroupUpdateView.as_view(),
        name="device_group_update",
    ),
    path(
        "devicegroups/<uuid:device_group_id>/manage",
        views.DeviceGroupManagementUpdateView.as_view(),
        name="device_group_management_update",
    ),
    path("devicestates", views.DeviceStateList.as_view(), name="device_state_list"),
    path(
        "inboundtypes/<uuid:module_id>",
        views.inbound_integration_type_detail,
        name="inbound_integration_type_detail",
    ),
    path(
        "inboundtypes/add",
        views.inbound_integration_type_add,
        name="inbound_integration_type_add",
    ),
    path(
        "inboundtypes/<uuid:inbound_integration_type_id>/edit",
        views.inbound_integration_type_update,
        name="inbound_integration_type_update",
    ),
    path(
        "inboundtypes",
        views.InboundIntegrationTypeListView.as_view(),
        name="inbound_integration_type_list",
    ),
    path(
        "outboundtypes/<uuid:module_id>",
        views.outbound_integration_type_detail,
        name="outbound_integration_type_detail",
    ),
    path(
        "outboundtypes/add",
        views.outbound_integration_type_add,
        name="outbound_integration_type_add",
    ),
    path(
        "outboundtypes/<uuid:outbound_integration_type_id>/edit",
        views.outbound_integration_type_update,
        name="outbound_integration_type_update",
    ),
    path(
        "outboundtypes",
        views.OutboundIntegrationTypeList.as_view(),
        name="outbound_integration_type_list",
    ),
    path(
        "inboundconfigurations",
        views.InboundIntegrationConfigurationListView.as_view(),
        name="inbound_integration_configuration_list",
    ),
    path(
        "inboundconfigurations/<uuid:id>",
        views.inbound_integration_configuration_detail,
        name="inbound_integration_configuration_detail",
    ),
    path(
        "inboundconfigurations/add",
        views.InboundIntegrationConfigurationAddView.as_view(),
        name="inbound_integration_configuration_add",
    ),
    path(
        "inboundconfigurations/<uuid:configuration_id>/edit",
        views.InboundIntegrationConfigurationUpdateView.as_view(),
        name="inbound_integration_configuration_update",
    ),
    path(
        "inboundconfigurations/type_modal/<uuid:integration_id>/",
        views.InboundIntegrationConfigurationUpdateView.type_modal,
        name="inboundconfigurations/type_modal",
    ),
    path(
        "inboundconfigurations/schema/<str:integration_type>/<uuid:integration_id>/<str:update>",
        views.InboundIntegrationConfigurationUpdateView.schema,
        name="inboundconfigurations/schema",
    ),
    path(
        "inboundconfigurations/dropdown_restore/<uuid:integration_id>/",
        views.InboundIntegrationConfigurationUpdateView.dropdown_restore,
        name="inboundconfigurations/dropdown_restore",
    ),
    path(
        "outboundconfigurations",
        views.OutboundIntegrationConfigurationListView.as_view(),
        name="outbound_integration_configuration_list",
    ),
    path(
        "outboundconfigurations/<uuid:module_id>",
        views.outbound_integration_configuration_detail,
        name="outbound_integration_configuration_detail",
    ),
    path(
        "outboundconfigurations/add",
        views.OutboundIntegrationConfigurationAddView.as_view(),
        name="outbound_integration_configuration_add",
    ),
    path(
        "outboundconfigurations/<uuid:configuration_id>/edit",
        views.OutboundIntegrationConfigurationUpdateView.as_view(),
        name="outbound_integration_configuration_update",
    ),
    path(
        "outboundconfigurations/type_modal/<uuid:configuration_id>/",
        views.OutboundIntegrationConfigurationUpdateView.type_modal,
        name="outboundconfigurations/type_modal",
    ),
    path(
        "outboundconfigurations/schema/<str:configuration_type>/<uuid:configuration_id>/<str:update>",
        views.OutboundIntegrationConfigurationUpdateView.schema,
        name="outboundconfigurations/schema",
    ),
    path(
        "outboundconfigurations/dropdown_restore/<uuid:integration_id>/",
        views.OutboundIntegrationConfigurationUpdateView.dropdown_restore,
        name="outboundconfigurations/dropdown_restore",
    ),
    path(
        "bridges",
        views.BridgeIntegrationListView.as_view(),
        name="bridge_integration_list",
    ),
    path(
        "bridges/<uuid:module_id>",
        views.bridge_integration_view,
        name="bridge_integration_view",
    ),
    path(
        "bridges/add", views.BridgeIntegrationAddView.as_view(), name="bridge_integration_add"
    ),
    path(
        "bridges/<uuid:id>/edit",
        views.BridgeIntegrationUpdateView.as_view(),
        name="bridge_integration_update",
    ),
    path(
        "bridges/type_modal/<uuid:integration_id>/",
        views.BridgeIntegrationUpdateView.type_modal,
        name="bridges/type_modal",
    ),
    path(
        "bridges/schema/<str:integration_type>/<uuid:integration_id>/<str:update>",
        views.BridgeIntegrationUpdateView.schema,
        name="bridges/schema",
    ),
    path(
        "bridges/dropdown_restore/<uuid:integration_id>/",
        views.BridgeIntegrationUpdateView.dropdown_restore,
        name="bridges/dropdown_restore",
    )
]
