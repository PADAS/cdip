from django.urls import path

from . import views


urlpatterns = [
    path('user/<str:user_id>', views.account_detail, name='account_detail'),
    path('', views.account_list, name='account_list'),
    path('add', views.account_add, name='account_add'),
    path('user/update/<str:user_id>', views.account_update, name='account_update'),
]
