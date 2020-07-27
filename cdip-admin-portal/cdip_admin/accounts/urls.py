from django.urls import path

from . import views


urlpatterns = [
    path('<uuid:user_id>', views.account_detail, name='account_detail'),
    path('', views.AccountList.as_view(), name='account_list'),
]
