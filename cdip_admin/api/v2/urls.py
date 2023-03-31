from django.conf.urls import url
from django.urls import path, include
from rest_framework_swagger.views import get_swagger_view
from . import views
from rest_framework.routers import DefaultRouter
from rest_framework_nested.routers import NestedSimpleRouter


default_router = DefaultRouter()
default_router.register('organizations', views.OrganizationView, basename="organizations")
organizations_router = NestedSimpleRouter(default_router, r'organizations', lookup='organization')
organizations_router.register(r'members', views.MemberViewSet, basename='members')
default_router.register('destinations', views.DestinationView, basename="destinations")

schema_view = get_swagger_view(title="CDIP ADMIN API V2")

urlpatterns = [
    url(r"^docs/", schema_view),
    path(r'', include(default_router.urls)),
    path(r'', include(organizations_router.urls)),
]
