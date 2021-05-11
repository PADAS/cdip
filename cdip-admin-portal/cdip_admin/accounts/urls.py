from django.urls import path

from . import views
from .views import AccountsListView, AccountsAddView, AccountsUpdateView, AccountProfileUpdateView

urlpatterns = [
    path('<str:user_id>', views.account_detail, name='account_detail'),
    path('', AccountsListView.as_view(), name='account_list'),
    path('add/<str:org_id>', AccountsAddView.as_view(), name='account_add'),
    path('update/<str:user_id>', AccountsUpdateView.as_view(), name='account_update'),
    path('profile/update/<str:org_id>/<str:user_id>', AccountProfileUpdateView.as_view(), name='account_profile_update'),
]
