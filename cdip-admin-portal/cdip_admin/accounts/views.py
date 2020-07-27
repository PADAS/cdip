from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import ListView

from .utils import get_accounts, Account


# Create your views here.
class AccountList(ListView):
    template_name = 'accounts/account_list.html'
    queryset = get_accounts()
    context_object_name = 'accounts'
    paginate_by = 2


def account_detail(request, user_id):
    account = get_object_or_404(Account, pk=user_id)
    return render(request, "accounts/account_detail;.html", {"module": account})
