from django.http import HttpResponse
from datetime import datetime
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
import json
from django.contrib.auth import logout, login
from django.conf import settings
from django.http import HttpResponseRedirect
from urllib.parse import urlencode

import logging

from integrations.models import InboundIntegrationType
from organizations.models import UserProfile, Organization

logger = logging.getLogger(__name__)


# Create your views here.
def welcome(request):
    return render(request, "website/welcome.html")


def date(request):
    return HttpResponse("This page was served at " + str(datetime.now()))


@login_required
def about(request):
    return HttpResponse("I am working on CDIP. Have a nice day!")


def index(request):
    user = request.user
    if user.is_authenticated:
        return redirect(welcome)
    else:
        return render(request, 'index.html')


def logout_view(request):
    logout(request)
    # Redirect to a success page.
    return render(request, 'index.html')


def login_view(request):
    login(request)
    # Redirect to a success page.
    return render(request, 'index.html')






