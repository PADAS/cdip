from django.urls import path

from . import views

urlpatterns = [
    path('<uuid:module_id>', views.detail, name='detail'),
    path('', views.integrations_list, name='integrations_list'),
    path('new', views.new, name="new"),
]
