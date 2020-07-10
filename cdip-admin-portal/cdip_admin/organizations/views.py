from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404, redirect

from .models import Organization

import http.client


# Create your views here.
def detail(request, module_id):
    organization = get_object_or_404(Organization, pk=module_id)
    return render(request, "organizations/detail.html", {"module": organization})


def organizations_list(request):
    if request.user.has_perm('organizations.view_organization'):

        profile = request.user.user_profile

        return render(request, "organizations/organizations_list.html",
                      {"organizations": profile.organizations.all()})
    else:
        return redirect("welcome")


def test_api(request):

    conn = http.client.HTTPConnection("localhost:8080")

    headers = {
        'authorization': "Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6IjVWU1gxc3F3OUhicV9xWUY5NERlOCJ9.eyJpc3MiOiJodHRwczovL2Rldi1mb3AtMDZxaC51cy5hdXRoMC5jb20vIiwic3ViIjoiNU1kRjBCR2Fha0ZqV1o5Qjd6enhOYjVDUVp3QUNZRUlAY2xpZW50cyIsImF1ZCI6Imh0dHA6Ly9sb2NhbGhvc3Q6ODAwMC8iLCJpYXQiOjE1OTQyMjY0NzIsImV4cCI6MTU5NDMxMjg3MiwiYXpwIjoiNU1kRjBCR2Fha0ZqV1o5Qjd6enhOYjVDUVp3QUNZRUkiLCJzY29wZSI6InJlYWQ6bWVzc2FnZXMiLCJndHkiOiJjbGllbnQtY3JlZGVudGlhbHMiLCJwZXJtaXNzaW9ucyI6WyJyZWFkOm1lc3NhZ2VzIl19.TcNE1Z38Z2oK4FiStCaez7Y05m_Bf4P0Q9bCY9szRF0vqbG98dGpV2D7PYNKiFjIPQ23XdILIIoJeFXwDTqikeqpA5QBpIId37mgvZrP2MRsFWChRTrJGCmCu0peA_-ZkFRAWcHEavzLtJyjCadHn76y_77vqORgZuxhkGcH-OElUy3jIHd-JPSfz1HENiq4-rJlYHdgrfp6LlDD3ItHadKotMZtYVkSy3N25xpmn2CyuctXUPsdvmXYU5aJP1uaOEz4qsemgLFQ57yzuTiJen7dlVlNVVp4nE7zXvmvhW7Ewno_mGTy-qhX8oSbpGXT9FGgHnT8K19lgwa5RUB5OA"}

    conn.request("GET", "/api/private-scoped", headers=headers)

    res = conn.getresponse()
    data = res.read()

    return HttpResponse(data.decode("utf-8"))
