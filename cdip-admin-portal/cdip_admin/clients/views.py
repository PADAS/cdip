from django.shortcuts import render, redirect

# Create your views here.
from clients.forms import ClientForm, ClientUpdateForm
from clients.utils import get_clients, get_client, add_client, update_client


def client_list(request):
    clients = get_clients()
    return render(request, "clients/client_list.html", {"module": clients})


def client_detail(request, client_id):
    client = get_client(client_id)
    return render(request, "clients/client_detail.html", {"module": client})


def client_add(request):

    if request.method == 'POST':
        form = ClientForm(request.POST)

        if form.is_valid():
            data = form.cleaned_data
            new_client = add_client(data)

            if new_client:
                return redirect('account_detail', client_id=new_client['client_id'])
            else:
                return redirect("welcome")

    else:
        form = ClientForm()
        return render(request, "clients/client_add.html", {"form": form})


def client_update(request, client_id):

    if request.method == 'POST':
        form = ClientUpdateForm(request.POST)

        if form.is_valid():
            data = form.cleaned_data
            client_info = update_client(data, client_id)

            if client_info:
                return redirect('client_detail', client_id=client_info['client_id'])
            else:
                return redirect("welcome")

    else:
        form = ClientUpdateForm()
        account = get_client(client_id)
        form.initial['name'] = account["name"]
        form.initial['description'] = account["description"]
        return render(request, "clients/client_update.html", {"form": form, "client_id": client_id})
