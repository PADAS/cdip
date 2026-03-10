from django.urls import path

from . import views
from organizations.views import *

urlpatterns = [
    path(
        "<uuid:module_id>",
        OrganizationDetailListView.as_view(),
        name="organizations_detail",
    ),
    path("add/", views.organizations_add, name="organizations_add"),
    path("", OrganizationsListView.as_view(), name="organizations_list"),
    path(
        "update/<uuid:organization_id>",
        OrganizationUpdateView.as_view(),
        name="organizations_update",
    ),
    path(
        "<uuid:organization_id>/members/",
        views.org_members_list,
        name="org_members_list",
    ),
    path(
        "<uuid:organization_id>/members/add/",
        views.org_members_add,
        name="org_members_add",
    ),
    path(
        "<uuid:organization_id>/members/<int:member_id>/remove/",
        views.org_members_remove,
        name="org_members_remove",
    ),
    path(
        "<uuid:organization_id>/members/<int:member_id>/role/",
        views.org_members_change_role,
        name="org_members_change_role",
    ),
]
