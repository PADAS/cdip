from django.urls import path

from . import views

urlpatterns = [
    path('devices/<uuid:module_id>', views.device_detail,
         name='device_detail'),
    path('devices', views.DeviceList.as_view(), name='device_list'),

    path('integrations/inbound/type/<uuid:module_id>', views.inbound_integration_type_detail,
         name='inbound_integration_type_detail'),
    path('integrations/inbound/type', views.InboundIntegrationTypeList.as_view(), name='inbound_integration_type_list'),

    path('integartions/outbound/type/<uuid:module_id>', views.outbound_integration_type_detail,
         name='outbound_integration_type_detail'),
    path('integrations/outbound/type', views.OutboundIntegrationTypeList.as_view(), name='outbound_integration_type_list'),

    path('integrations/inbound/configuration', views.InboundIntegrationConfigurationList.as_view(),
         name="inbound_integration_configuration_list"),
    path('integrations/inbound/configuration/<uuid:module_id>', views.inbound_integration_configuration_detail,
         name="inbound_integration_configuration_detail"),
    path('integrations/inbound/configuration/add', views.inbound_integration_configuration_add,
         name="inbound_integration_configuration_add"),

    path('integrations/outbound/configuration', views.OutboundIntegrationConfigurationList.as_view(),
         name="outbound_integration_configuration_list"),
    path('integrations/outbound/configuration/<uuid:module_id>', views.outbound_integration_configuration_detail,
         name="outbound_integration_configuration_detail"),
    path('integrations/outbound/configuration/add', views.outbound_integration_configuration_add,
         name="outbound_integration_configuration_add"),
]
