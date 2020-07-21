from django.conf.urls import url
from django.urls import path
from rest_framework_swagger.views import get_swagger_view

from api.views import *

schema_view = get_swagger_view(title="CDIP ADMIN API")

urlpatterns = [
    path('public', public),
    path('private', private),
    path('private-scoped', private_scoped),
    path('organizations', OrganizationsListView.as_view(), name='organization_list'),
    path('organizations/<pk>/', OrganizationDetailsView.as_view(), name='organization_detail'),
    path('inboundintegrationtypes', InboundIntegrationTypeListView.as_view(), name='inboundintegrationtype_list'),
    path('inboundintegrationtypes/<pk>/', InboundIntegrationTypeDetailsView.as_view(),
         name='inboundintegrationtype_detail'),
    path('inboundintegrationconfigurations', InboundIntegrationConfigurationListView.as_view(),
         name='inboundintegrationconfiguration_list'),
    path('inboundintegrationconfigurations/<pk>/', InboundIntegrationConfigurationDetailsView.as_view(),
         name='inboundintegrationconfigurations_detail'),
    path('outboundintegrationtypes', OutboundIntegrationTypeListView.as_view(), name='outboundintegrationtype_list'),
    path('outboundintegrationtypes/<pk>/', OutboundIntegrationTypeDetailsView.as_view(),
         name='outboundintegrationtype_detail'),
    url(r'^docs/', schema_view),
]
