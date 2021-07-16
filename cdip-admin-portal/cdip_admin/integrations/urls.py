from django.urls import path

from . import views
from .views import OutboundIntegrationConfigurationUpdateView, InboundIntegrationConfigurationUpdateView, \
    DeviceGroupUpdateView, InboundIntegrationConfigurationAddView, OutboundIntegrationConfigurationAddView, \
    DeviceGroupAddView, DeviceGroupManagementUpdateView, BridgeIntegrationAddView, \
    BridgeIntegrationUpdateView

urlpatterns = [
    path('devices/<uuid:module_id>', views.device_detail, name='device_detail'),
    path('devices/<uuid:module_id>/edit', views.device_detail, name='device_edit'),
    path('devices', views.DeviceList.as_view(), name='device_list'),

    path('devicegroups/<uuid:module_id>', views.DeviceGroupDetail.as_view(), name='device_group'),
    path('devicegroups/<uuid:module_id>/edit', views.DeviceGroupDetail.as_view(),
         name='device_group_edit'),
    path('devicegroups', views.DeviceGroupListView.as_view(), name='device_group_list'),
    path('devicegroups/add', DeviceGroupAddView.as_view(), name="device_group_add"),
    path('devicegroups/<uuid:device_group_id>/edit',
         DeviceGroupUpdateView.as_view(), name="device_group_update"),
    path('devicegroups/<uuid:device_group_id>/manage',
         DeviceGroupManagementUpdateView.as_view(),
         name="device_group_management_update"),

    path('devicestates', views.DeviceStateList.as_view(), name='device_state_list'),

    path('inboundtypes/<uuid:module_id>', views.inbound_integration_type_detail,
         name='inbound_integration_type_detail'),
    path('inboundtypes/add', views.inbound_integration_type_add, name='inbound_integration_type_add'),
    path('inboundtypes/<uuid:inbound_integration_type_id>/edit',
         views.inbound_integration_type_update,
         name="inbound_integration_type_update"),
    path('inboundtypes', views.InboundIntegrationTypeListView.as_view(),
         name='inbound_integration_type_list'),

    path('outboundtypes/<uuid:module_id>', views.outbound_integration_type_detail,
         name='outbound_integration_type_detail'),
    path('outboundtypes/add', views.outbound_integration_type_add, name='outbound_integration_type_add'),
    path('outboundtypes/<uuid:outbound_integration_type_id>/edit',
         views.outbound_integration_type_update,
         name="outbound_integration_type_update"),
    path('outboundtypes', views.OutboundIntegrationTypeList.as_view(),
         name='outbound_integration_type_list'),

    path('inboundconfigurations', views.InboundIntegrationConfigurationListView.as_view(),
         name="inbound_integration_configuration_list"),
    path('inboundconfigurations/<uuid:module_id>', views.inbound_integration_configuration_detail,
         name="inbound_integration_configuration_detail"),
    path('inboundconfigurations/add', InboundIntegrationConfigurationAddView.as_view(),
         name="inbound_integration_configuration_add"),
    path('inboundconfigurations/<uuid:configuration_id>/edit',
         InboundIntegrationConfigurationUpdateView.as_view(),
         name="inbound_integration_configuration_update"),

    path('outboundconfigurations', views.OutboundIntegrationConfigurationListView.as_view(),
         name="outbound_integration_configuration_list"),
    path('outboundconfigurations/<uuid:module_id>', views.outbound_integration_configuration_detail,
         name="outbound_integration_configuration_detail"),
    path('outboundconfigurations/add', OutboundIntegrationConfigurationAddView.as_view(),
         name="outbound_integration_configuration_add"),
    path('outboundconfigurations/<uuid:configuration_id>/edit',
         OutboundIntegrationConfigurationUpdateView.as_view(),
         name="outbound_integration_configuration_update"),

    path('bridges', views.BridgeIntegrationListView.as_view(),
         name="bridge_integration_list"),
    path('bridges/<uuid:module_id>', views.bridge_integration_view,
         name="bridge_integration_view"),
    path('bridges/add', BridgeIntegrationAddView.as_view(),
         name="bridge_integration_add"),
    path('bridges/<uuid:id>/edit',
         BridgeIntegrationUpdateView.as_view(),
         name="bridge_integration_update"),

]
