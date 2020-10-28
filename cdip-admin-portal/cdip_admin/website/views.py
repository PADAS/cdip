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


# def logout(request):
#     log_out(request)
#     return_to = urlencode({'returnTo': request.build_absolute_uri('/')})
#
#     logout_url = f'https://{settings.SOCIAL_AUTH_AUTH0_DOMAIN}/v2/logout?client_id={settings.SOCIAL_AUTH_AUTH0_KEY}&{return_to}'
#     return HttpResponseRedirect(logout_url)


@login_required
def profile(request):
    user = request.user
    logger.debug('User: %s (%s)', user, user.id)
    auth0user = user.social_auth.get(provider='auth0')

    user_profile = []

    try:
        for org in Organization.objects.filter(user_profile__user=user):
            user_profile.append(org.name)
    except UserProfile.DoesNotExist: 
        logger.debug('User has no UserProfile')

    userdata = {
        'user_id': auth0user.uid,
        'name': user.first_name,
        'picture': auth0user.extra_data['picture'],
        'organizations': user_profile
    }

    return render(request, 'website/profile.html', {
        'auth0User': auth0user,
        'userdata': json.dumps(userdata, indent=4)
    })





