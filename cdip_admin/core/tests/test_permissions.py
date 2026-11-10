from django.test import RequestFactory
from rest_framework.request import Request

from core.permissions import IsServiceAccount


def test_service_account_permission_reads_client_id_from_request():
    """The auth backend sets client_id on the Django request on every API call."""
    req = RequestFactory().post("/api/v1.0/observations")
    req.client_id = "svc-client"

    assert IsServiceAccount().has_permission(req, view=None) is True
    assert IsServiceAccount.get_client_id(req) == "svc-client"


def test_service_account_permission_reads_through_a_drf_request():
    django_request = RequestFactory().post("/api/v1.0/observations")
    django_request.client_id = "svc-client"

    assert IsServiceAccount.get_client_id(Request(django_request)) == "svc-client"


def test_service_account_permission_denies_without_client_id():
    req = RequestFactory().get("/")
    req.session = {"client_id": "stale-from-an-old-login"}

    assert not IsServiceAccount().has_permission(req, view=None)
    assert IsServiceAccount.get_client_id(req) is None
