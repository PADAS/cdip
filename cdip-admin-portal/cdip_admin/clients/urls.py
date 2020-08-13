from django.urls import path

from . import views


urlpatterns = [
    path('client/<str:client_id>', views.client_detail, name='client_detail'),
    path('', views.client_list, name='client_list'),
    path('add', views.client_add, name='client_add'),
    path('client/update/<str:client_id>', views.client_update, name='client_update'),
]
