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
default_router.register('integrations/types', views.IntegrationTypeView, basename='integration-types')
default_router.register('integrations', views.IntegrationsView, basename="integrations")
integrations_router = NestedSimpleRouter(default_router, r'integrations', lookup='integration')
integrations_router.register(r'actions', views.ActionTriggerView, basename='actions')
default_router.register('connections', views.ConnectionsView, basename="connections")
default_router.register('sources', views.SourcesView, basename="sources")
default_router.register('routes', views.RoutesView, basename="routes")
default_router.register('observations', views.ObservationsView, basename="observations")
default_router.register('events', views.EventsView, basename="events")
events_router = NestedSimpleRouter(default_router, r'events', lookup='event')
events_router.register(r'attachments', views.AttachmentViewSet, basename='attachments')
default_router.register('traces', views.GundiTraceViewSet, basename="traces")
default_router.register('logs', views.ActivityLogsViewSet, basename="logs")


schema_view = get_swagger_view(title="CDIP ADMIN API V2")

urlpatterns = [
    url(r"^docs/", schema_view),
    # User details for any kind of user
    path(
        'users/me/',
        view=views.UsersView.as_view(
             {
                 'get': 'retrieve',
             }
        ),
        name="user-details"
    ),
    path(r'', include(default_router.urls)),
    path(r'', include(integrations_router.urls)),
    path(r'', include(organizations_router.urls)),
    path(r'', include(events_router.urls)),
]
