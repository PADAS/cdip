import logging

from django.core.exceptions import ObjectDoesNotExist, SuspiciousOperation, PermissionDenied
from django.shortcuts import render, redirect, get_object_or_404

# Create your views here.
from clients.forms import ClientForm, ClientUpdateForm, ClientProfileForm
from clients.models import ClientProfile
from clients.utils import get_clients, get_client, add_client, update_client, get_client_by_client_id, get_client_secret
from core.permissions import IsGlobalAdmin

logger = logging.getLogger(__name__)


def client_list(request):
    if not IsGlobalAdmin.has_permission(None, request, None):
        raise PermissionDenied

    clients = get_clients()
    return render(request, "clients/client_list.html", {"module": clients})


def client_detail(request, client_id):
    if not IsGlobalAdmin.has_permission(None, request, None):
        raise PermissionDenied

    client = get_client(client_id)

    try:
        profile = ClientProfile.objects.get(client_id=client['clientId'])
    except ObjectDoesNotExist:
        profile = None

    organizations = []

    if profile:
        try:
            for org in profile.organizations.all():
                organizations.append(org.name)
        except profile.DoesNotExist:
            logger.debug('Client does not have a Profile')

    return render(request, "clients/client_detail.html", {"client": client, 'organizations': organizations,
                                                          'profile': profile})


def client_secret(request, client_id):
    if not IsGlobalAdmin.has_permission(None, request, None):
        raise PermissionDenied

    client = get_client_secret(client_id)

    return render(request, "clients/client_secret.html", {"client": client, "client_id": client_id})


def client_add(request):
    if not IsGlobalAdmin.has_permission(None, request, None):
        raise PermissionDenied

    if request.method == 'POST':
        form = ClientForm(request.POST)
        profile_form = ClientProfileForm(request.POST)

        if form.is_valid() and profile_form.is_valid():
            client_info = form.cleaned_data
            type_id = profile_form.instance.type.id
            response = add_client(client_info, type_id)

            if response is not None:
                profile_form.cleaned_data['client_id'] = client_info['clientId']
                profile_form.instance.client_id = client_info['clientId']
                profile_form.save()
                return redirect('client_detail', response)
            else:
                raise SuspiciousOperation

    else:
        form = ClientForm()
        form.initial['rootUrl'] = request.headers['Host']
        profile_form = ClientProfileForm()
        return render(request, "clients/client_add.html", {"form": form, "profile_form": profile_form})


def client_update(request, client_id):
    if not IsGlobalAdmin.has_permission(None, request, None):
        raise PermissionDenied

    client = get_client(client_id)

    if request.method == 'POST':
        form = ClientUpdateForm(request.POST)

        if form.is_valid():
            data = form.cleaned_data
            response = update_client(data, client_id)

            if response:
                try:
                    profile = ClientProfile.objects.get(client_id=client['clientId'])
                except ObjectDoesNotExist:
                    profile = None

                if profile:
                    profile.client_id = data['clientId']
                    profile.save()
                return redirect('client_detail', client_id=client_id)
            else:
                raise SuspiciousOperation

    else:
        form = ClientUpdateForm()
        form.initial['clientId'] = client["clientId"]
        form.initial['rootUrl'] = client["rootUrl"]
        form.initial['protocol'] = client["protocol"]

        return render(request, "clients/client_update.html", {"form": form,
                                                              "client_id": client_id})


def client_profile_add(request, client_id):
    if not IsGlobalAdmin.has_permission(None, request, None):
        raise PermissionDenied

    if request.method == 'POST':
        profile_form = ClientProfileForm(request.POST)

        if profile_form.is_valid():
            profile_form.save()
            client = get_client_by_client_id(client_id)
            client_uuid = client[0]['id']
            return redirect('client_detail', client_id=client_uuid)
        else:
            return render(request, "clients/client_profile_add.html", {"client_id": client_id,
                                                                       "profile_form": profile_form})

    else:
        profile_form = ClientProfileForm()
        profile_form.initial['client_id'] = client_id
        return render(request, "clients/client_profile_add.html", {"client_id": client_id,
                                                                   "profile_form": profile_form})


def client_profile_update(request, client_id):
    if not IsGlobalAdmin.has_permission(None, request, None):
        raise PermissionDenied

    profile = get_object_or_404(ClientProfile, client_id=client_id)

    if request.method == 'POST':
        profile_form = ClientProfileForm(instance=profile, data=request.POST)
        if profile_form.is_valid():
            profile_form.save()
            client = get_client_by_client_id(client_id)
            client_uuid = client[0]['id']
            return redirect('client_detail', client_id=client_uuid)
        else:
            return render(request, "clients/client_profile_add.html", {"user_id": client_id,
                                                                       "profile_form": profile_form})

    else:
        profile_form = ClientProfileForm()

        profile_form.initial['id'] = profile.id
        profile_form.initial['client_id'] = profile.client_id
        profile_form.initial['type'] = profile.type
        profile_form.initial['organizations'] = profile.organizations.all()

        return render(request, "clients/client_profile_update.html", {"profile_form": profile_form,
                                                                      "client_id": client_id})
