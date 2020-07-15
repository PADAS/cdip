from django.urls import path

from . import views

urlpatterns = [
    path('InboundIntegrationType/<uuid:module_id>', views.inbound_integration_type_detail,
         name='inbound_integration_type_detail'),
    path('InboundIntegrationType', views.InboundIntegrationTypeList.as_view(), name='inbound_integration_type_list'),

    path('OutboundIntegrationType/<uuid:module_id>', views.outbound_integration_type_detail,
         name='outbound_integration_type_detail'),
    path('OutboundIntegrationType', views.OutboundIntegrationTypeList.as_view(), name='outbound_integration_type_list'),

    path('InboundIntegrationConfiguration', views.InboundIntegrationConfigurationList.as_view(),
         name="inbound_integration_configuration_list"),
    path('InboundIntegrationConfiguration/<uuid:module_id>', views.inbound_integration_configuration_detail,
         name="inbound_integration_configuration_detail"),
    path('InboundIntegrationConfiguration/Add', views.inbound_integration_configuration_add,
         name="inbound_integration_configuration_add"),

    path('OutboundIntegrationConfiguration', views.OutboundIntegrationConfigurationList.as_view(),
         name="outbound_integration_configuration_list"),
    path('OutboundIntegrationConfiguration/<uuid:module_id>', views.outbound_integration_configuration_detail,
         name="outbound_integration_configuration_detail"),
    path('OutboundIntegrationConfiguration/Add', views.outbound_integration_configuration_add,
         name="outbound_integration_configuration_add"),
]
