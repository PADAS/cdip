from django.urls import path

from . import views
from .views import OutboundIntegrationConfigurationUpdateView, InboundIntegrationConfigurationUpdateView, \
    DeviceGroupUpdateView, InboundIntegrationConfigurationAddView, OutboundIntegrationConfigurationAddView, \
    DeviceGroupAddView

urlpatterns = [
    path('devices/<uuid:module_id>', views.device_detail,
         name='device_detail'),
    path('devices', views.DeviceList.as_view(), name='device_list'),

    path('devices/groups/<uuid:module_id>', views.DeviceGroupDetail.as_view(),
         name='device_group_detail'),
    path('devices/groups', views.DeviceGroupListView.as_view(), name='device_group_list'),
    path('devices/groups/add', DeviceGroupAddView.as_view(),
         name="device_group_add"),
    path('devices/groups/update/<uuid:device_group_id>',
         DeviceGroupUpdateView.as_view(),
         name="device_group_update"),
    path('devices/groups/management/update/<uuid:device_group_id>',
         views.device_group_management_update,
         name="device_group_management_update"),

    path('devices/state/', views.DeviceStateList.as_view(), name='device_state_list'),

    path('integrations/inbound/type/<uuid:module_id>', views.inbound_integration_type_detail,
         name='inbound_integration_type_detail'),
    path('integrations/inbound/type/add', views.inbound_integration_type_add, name='inbound_integration_type_add'),
    path('integrations/inbound/type/update/<uuid:inbound_integration_type_id>',
         views.inbound_integration_type_update,
         name="inbound_integration_type_update"),
    path('integrations/inbound/type', views.InboundIntegrationTypeListView.as_view(),
         name='inbound_integration_type_list'),

    path('integartions/outbound/type/<uuid:module_id>', views.outbound_integration_type_detail,
         name='outbound_integration_type_detail'),
    path('integrations/outbound/type/add', views.outbound_integration_type_add, name='outbound_integration_type_add'),
    path('integrations/outbound/type/update/<uuid:outbound_integration_type_id>',
         views.outbound_integration_type_update,
         name="outbound_integration_type_update"),
    path('integrations/outbound/type', views.OutboundIntegrationTypeList.as_view(),
         name='outbound_integration_type_list'),

    path('integrations/inbound/configuration', views.InboundIntegrationConfigurationListView.as_view(),
         name="inbound_integration_configuration_list"),
    path('integrations/inbound/configuration/<uuid:module_id>', views.inbound_integration_configuration_detail,
         name="inbound_integration_configuration_detail"),
    path('integrations/inbound/configuration/add', InboundIntegrationConfigurationAddView.as_view(),
         name="inbound_integration_configuration_add"),
    path('integrations/inbound/configuration/update/<uuid:configuration_id>',
         InboundIntegrationConfigurationUpdateView.as_view(),
         name="inbound_integration_configuration_update"),

    path('integrations/outbound/configuration', views.OutboundIntegrationConfigurationListView.as_view(),
         name="outbound_integration_configuration_list"),
    path('integrations/outbound/configuration/<uuid:module_id>', views.outbound_integration_configuration_detail,
         name="outbound_integration_configuration_detail"),
    path('integrations/outbound/configuration/add', OutboundIntegrationConfigurationAddView.as_view(),
         name="outbound_integration_configuration_add"),
    path('integrations/outbound/configuration/update/<uuid:configuration_id>',
         OutboundIntegrationConfigurationUpdateView.as_view(),
         name="outbound_integration_configuration_update"),
]
