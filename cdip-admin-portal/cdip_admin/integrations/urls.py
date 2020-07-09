from django.urls import path

from . import views

urlpatterns = [
    path('<uuid:module_id>', views.detail, name='detail'),
    path('', views.IntegrationsList.as_view(), name='integrations_list'),
    path('new', views.new, name="new"),
]
