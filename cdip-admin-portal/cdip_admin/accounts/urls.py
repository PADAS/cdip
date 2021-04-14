from django.urls import path

from . import views
from .views import AccountsListView, AccountsAddView, AccountsUpdateView

urlpatterns = [
    path('<str:user_id>', views.account_detail, name='account_detail'),
    path('', AccountsListView.as_view(), name='account_list'),
    path('add/', AccountsAddView.as_view(), name='account_add'),
    path('update/<str:user_id>', AccountsUpdateView.as_view(), name='account_update'),
    path('profile/add/<str:user_id>', views.account_profile_add, name='account_profile_add'),
    path('profile/update/<str:user_id>', views.account_profile_update, name='account_profile_update'),
]
