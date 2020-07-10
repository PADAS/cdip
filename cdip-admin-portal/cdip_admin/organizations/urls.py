from django.urls import path

from . import views

urlpatterns = [
    path('<uuid:module_id>', views.detail, name='detail'),
    path('', views.organizations_list, name='organizations_list'),
    path('test_api', views.test_api, name='test_api')
]
