from django.urls import path

from . import views

urlpatterns = [
    path('<uuid:module_id>', views.organizations_detail, name='organizations_detail'),
    path('', views.organizations_list, name='organizations_list'),
]
