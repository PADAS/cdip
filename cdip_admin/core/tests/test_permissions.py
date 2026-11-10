import pytest
from django.test import RequestFactory

from core.permissions import IsServiceAccount


def test_service_account_permission_reads_client_id_from_request():
    """
    Stateless API requests carry client_id on the request object (the backend
    keeps it off the session so no django_session row is written per call).
    """
    req = RequestFactory().post("/api/v1.0/observations")
    req.session = {}
    req.client_id = "svc-client"

    assert IsServiceAccount().has_permission(req, view=None) is True
    assert IsServiceAccount.get_client_id(req) == "svc-client"


def test_service_account_permission_falls_back_to_session():
    """Session-backed (browser) requests keep working unchanged."""
    req = RequestFactory().get("/")
    req.session = {"client_id": "svc-client"}

    assert IsServiceAccount().has_permission(req, view=None)
    assert IsServiceAccount.get_client_id(req) == "svc-client"


def test_service_account_permission_denies_without_client_id():
    req = RequestFactory().get("/")
    req.session = {}

    assert not IsServiceAccount().has_permission(req, view=None)
    assert IsServiceAccount.get_client_id(req) is None


def test_service_account_permission_surfaces_session_backend_errors():
    """
    A failing session store must raise, not be swallowed into a 403; the
    only expected miss is a missing key.
    """

    class BrokenSession(dict):
        def get(self, key, default=None):
            raise RuntimeError("session store down")

    req = RequestFactory().get("/")
    req.session = BrokenSession()

    with pytest.raises(RuntimeError):
        IsServiceAccount.get_client_id(req)


def test_service_account_permission_denies_without_session_attribute():
    req = RequestFactory().get("/")

    assert IsServiceAccount.get_client_id(req) is None
