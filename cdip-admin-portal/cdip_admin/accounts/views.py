import logging
from django.shortcuts import render, redirect
from django.core.exceptions import ObjectDoesNotExist

from .forms import AccountForm, AccountUpdateForm, AccountProfileForm
from .utils import get_accounts, get_account, add_account, update_account
from .models import AccountProfile

logger = logging.getLogger(__name__)


# Create your views here.
def account_list(request):
    logger.info('Getting account list')
    accounts = get_accounts()
    return render(request, "accounts/account_list.html", {"module": accounts})


def account_detail(request, user_id):
    logger.info('Getting account detail')
    account = get_account(user_id)
    return render(request, "accounts/account_detail.html", {"module": account})


def account_add(request):
    logger.info('Adding account')
    if request.method == 'POST':
        account_form = AccountForm(request.POST)

        if account_form.is_valid():
            data = account_form.cleaned_data
            new_account = add_account(data)

            if new_account:
                user_id = new_account['user_id']
                return redirect('account_profile_add', user_id=user_id)
            else:
                return redirect("welcome")

    else:
        account_form = AccountForm()
        return render(request, "accounts/account_add.html", {"account_form": account_form})


def account_update(request, user_id):
    if request.method == 'POST':
        account_form = AccountUpdateForm(request.POST)
        if account_form.is_valid():
            data = account_form.cleaned_data
            account_info = update_account(data, user_id)

            return redirect('account_detail', user_id=account_info['user_id'])
        else:
            return redirect("welcome")

    else:
        account_form = AccountUpdateForm()

        account = get_account(user_id)

        account_form.initial['name'] = account["name"]
        account_form.initial['email'] = account["email"]

        return render(request, "accounts/account_update.html", {"account_form": account_form, "user_id": user_id})


def account_profile_add(request, user_id):
    if request.method == 'POST':
        profile_form = AccountProfileForm(request.POST)

        if profile_form.is_valid():
            profile_form.save()

            return redirect('account_detail', user_id=user_id)
        else:
            return redirect("welcome")

    else:
        profile_form = AccountProfileForm()
        profile_form.initial['user_id'] = user_id
        return render(request, "accounts/account_profile_add.html", {"user_id": user_id, "profile_form": profile_form})


def account_profile_update(request, user_id):
    if request.method == 'POST':
        profile_form = AccountProfileForm(request.POST)

        if profile_form.is_valid():
            profile = profile_form.save(commit=False)
            profile.user_id = user_id
            profile.save()
            return redirect('account_detail', user_id=user_id)
        else:
            return redirect("welcome")

    else:
        profile_form = AccountProfileForm()

        try:
            profile = AccountProfile.objects.get(user_id=user_id)
        except ObjectDoesNotExist:
            profile = None

        if profile:
            profile_form.initial['id'] = profile.id
            profile_form.initial['user_id'] = profile.user_id
            profile_form.initial['organizations'] = profile.organizations
        return render(request, "accounts/account_profile_update.html", {"user_id": user_id, "profile_form": profile_form})
