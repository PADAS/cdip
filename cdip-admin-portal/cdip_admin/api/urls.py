from django.conf.urls import url
from django.urls import path
from rest_framework_swagger.views import get_swagger_view

from api.views import *

schema_view = get_swagger_view(title="CDIP ADMIN API")

urlpatterns = [
    path('v1.0/public', public),
    path('v1.0/private', private),
    path('v1.0/private-scoped', private_scoped),

    path('v1.0/organizations', OrganizationsListView.as_view(), name='organization_list'),
    path('v1.0/organizations/<pk>/', OrganizationDetailsView.as_view(), name='organization_detail'),

    path('v1.0/inboundintegrationtypes', InboundIntegrationTypeListView.as_view(), name='inboundintegrationtype_list'),
    path('v1.0/inboundintegrationtypes/<pk>', InboundIntegrationTypeDetailsView.as_view(),
         name='inboundintegrationtype_detail'),

    path('v1.0/inboundintegrationconfigurations', InboundIntegrationConfigurationListView.as_view(),
         name='inboundintegrationconfiguration_list'),
    path('v1.0/inboundintegrationconfigurations/<pk>', InboundIntegrationConfigurationDetailsView.as_view(),
         name='inboundintegrationconfigurations_detail'),
    path('v1.0/inboundintegrationconfigurations/<type_id>/type', InboundIntegrationConfigurationListViewByType.as_view(),
         name='inboundintegrationconfigurationsbytype_detail'),

    path('v1.0/outboundintegrationtypes', OutboundIntegrationTypeListView.as_view(), name='outboundintegrationtype_list'),
    path('v1.0/outboundintegrationtypes/<pk>', OutboundIntegrationTypeDetailsView.as_view(),
         name='outboundintegrationtype_detail'),

    path('v1.0/outboundintegrationconfigurations', OutboundIntegrationConfigurationListView.as_view(),
         name='outboundintegrationconfiguration_list'),
    path('v1.0/outboundintegrationconfigurations/<pk>', OutboundIntegrationConfigurationDetailsView.as_view(),
         name='outboundintegrationconfigurations_detail'),

    url(r'^docs/', schema_view),
]
