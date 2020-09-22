from django.urls import path

from . import views


urlpatterns = [
    path('<str:client_id>', views.client_detail, name='client_detail'),
    path('', views.client_list, name='client_list'),
    path('add/', views.client_add, name='client_add'),
    path('update/<str:client_id>', views.client_update, name='client_update'),
    path('profile/add/<str:client_id>', views.client_profile_add, name='client_profile_add'),
    path('profile/update/<str:client_id>', views.client_profile_update, name='client_profile_update'),
]
