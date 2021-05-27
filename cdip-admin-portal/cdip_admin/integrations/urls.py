from django.urls import path

from . import views
from .views import OutboundIntegrationConfigurationUpdateView, InboundIntegrationConfigurationUpdateView, \
    DeviceGroupUpdateView, InboundIntegrationConfigurationAddView, OutboundIntegrationConfigurationAddView, \
    DeviceGroupAddView, DeviceGroupManagementUpdateView, BridgeIntegrationListView, BridgeIntegrationAddView, \
    BridgeIntegrationUpdateView

urlpatterns = [
    path('devices/<uuid:module_id>', views.device_detail,
         name='device_detail'),
    path('devices', views.DeviceList.as_view(), name='device_list'),

    path('devicegroups/<uuid:module_id>', views.DeviceGroupDetail.as_view(),
         name='device_group_detail'),
    path('devicegroups', views.DeviceGroupListView.as_view(), name='device_group_list'),
    path('devicegroups/add', DeviceGroupAddView.as_view(),
         name="device_group_add"),
    path('devicegroups/update/<uuid:device_group_id>',
         DeviceGroupUpdateView.as_view(),
         name="device_group_update"),
    path('devicegroups/management/update/<uuid:device_group_id>',
         DeviceGroupManagementUpdateView.as_view(),
         name="device_group_management_update"),

    path('devicestates', views.DeviceStateList.as_view(), name='device_state_list'),

    path('integrations/inboundtype/<uuid:module_id>', views.inbound_integration_type_detail,
         name='inbound_integration_type_detail'),
    path('integrations/inboundtype/add', views.inbound_integration_type_add, name='inbound_integration_type_add'),
    path('integrations/inboundtype/update/<uuid:inbound_integration_type_id>',
         views.inbound_integration_type_update,
         name="inbound_integration_type_update"),
    path('integrations/inboundtype', views.InboundIntegrationTypeListView.as_view(),
         name='inbound_integration_type_list'),

    path('integrations/outboundtype/<uuid:module_id>', views.outbound_integration_type_detail,
         name='outbound_integration_type_detail'),
    path('integrations/outboundtype/add', views.outbound_integration_type_add, name='outbound_integration_type_add'),
    path('integrations/outboundtype/update/<uuid:outbound_integration_type_id>',
         views.outbound_integration_type_update,
         name="outbound_integration_type_update"),
    path('integrations/outboundtype', views.OutboundIntegrationTypeList.as_view(),
         name='outbound_integration_type_list'),

    path('integrations/inboundconfiguration', views.InboundIntegrationConfigurationListView.as_view(),
         name="inbound_integration_configuration_list"),
    path('integrations/inboundconfiguration/<uuid:module_id>', views.inbound_integration_configuration_detail,
         name="inbound_integration_configuration_detail"),
    path('integrations/inboundconfiguration/add', InboundIntegrationConfigurationAddView.as_view(),
         name="inbound_integration_configuration_add"),
    path('integrations/inboundconfiguration/update/<uuid:configuration_id>',
         InboundIntegrationConfigurationUpdateView.as_view(),
         name="inbound_integration_configuration_update"),

    path('integrations/outboundconfiguration', views.OutboundIntegrationConfigurationListView.as_view(),
         name="outbound_integration_configuration_list"),
    path('integrations/outboundconfiguration/<uuid:module_id>', views.outbound_integration_configuration_detail,
         name="outbound_integration_configuration_detail"),
    path('integrations/outboundconfiguration/add', OutboundIntegrationConfigurationAddView.as_view(),
         name="outbound_integration_configuration_add"),
    path('integrations/outboundconfiguration/update/<uuid:configuration_id>',
         OutboundIntegrationConfigurationUpdateView.as_view(),
         name="outbound_integration_configuration_update"),

    path('integrations/bridge', views.BridgeIntegrationListView.as_view(),
         name="bridge_integration_list"),
    path('integrations/bridge/<uuid:module_id>', views.bridge_integration_view,
         name="bridge_integration_view"),
    path('integrations/bridge/add', BridgeIntegrationAddView.as_view(),
         name="bridge_integration_add"),
    path('integrations/bridge/<uuid:id>/update',
         BridgeIntegrationUpdateView.as_view(),
         name="bridge_integration_update"),

]
