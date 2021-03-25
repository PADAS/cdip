from django.urls import path

from . import views
from organizations.views import *

urlpatterns = [
    path('<uuid:module_id>', views.organizations_detail, name='organizations_detail'),
    path('add/', views.organizations_add, name='organizations_add'),
    path('', OrganizationsListView.as_view(), name='organizations_list'),
    path('update/<uuid:organization_id>', views.organizations_update, name='organizations_update'),
]
