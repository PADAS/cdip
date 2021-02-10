from django.urls import path

from . import views

urlpatterns = [
    path('<uuid:module_id>', views.organizations_detail, name='organizations_detail'),
    path('add/', views.organizations_add, name='organizations_add'),
    path('', views.organizations_list, name='organizations_list'),
    path('update/<uuid:organization_id>', views.organizations_update, name='organizations_update'),
]
