from django.shortcuts import render, redirect

from .forms import AccountForm, AccountUpdateForm
from .utils import get_accounts, get_account, add_account, update_account


# Create your views here.
def account_list(request):
    accounts = get_accounts()
    return render(request, "accounts/account_list.html", {"module": accounts})


def account_detail(request, user_id):
    account = get_account(user_id)
    return render(request, "accounts/account_detail.html", {"module": account})


def account_add(request):

    if request.method == 'POST':
        form = AccountForm(request.POST)

        if form.is_valid():
            data = form.cleaned_data
            new_account = add_account(data)

            if new_account:
                return redirect('account_detail', user_id=new_account['user_id'])
            else:
                return redirect("welcome")

    else:
        form = AccountForm()
        return render(request, "accounts/account_add.html", {"form": form})


def account_update(request, user_id):

    if request.method == 'POST':
        form = AccountUpdateForm(request.POST)

        if form.is_valid():
            data = form.cleaned_data
            account_info = update_account(data, user_id)

            if account_info:
                return redirect('account_detail', user_id=account_info['user_id'])
            else:
                return redirect("welcome")

    else:
        form = AccountUpdateForm()
        account = get_account(user_id)
        form.initial['name'] = account["name"]
        form.initial['email'] = account["email"]
        return render(request, "accounts/account_update.html", {"form": form, "user_id": user_id})
