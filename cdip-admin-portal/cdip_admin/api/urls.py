from django.urls import path
from django.conf.urls import url

from api.views import public, private, private_scoped, OrganizationsListView

from rest_framework_swagger.views import get_swagger_view

schema_view = get_swagger_view(title="CDIP ADMIN API")

urlpatterns = [
    path('public', public),
    path('private', private),
    path('private-scoped', private_scoped),
    path('organizations/', OrganizationsListView.as_view(), name='organization_list'),
    url(r'^docs/', schema_view),
]
