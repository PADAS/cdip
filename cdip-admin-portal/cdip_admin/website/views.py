from django.shortcuts import render
from django.http import HttpResponse
from datetime import datetime

from integrations.models import InboundIntegrationType


# Create your views here.
def welcome(request):
    return render(request, "website/welcome.html",
                  {"integrations": InboundIntegrationType.objects.all()})


def date(request):
    return HttpResponse("This page was served at " + str(datetime.now()))


def about(request):
    return HttpResponse("I am working on CDIP. Have a nice day!")


