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
]
