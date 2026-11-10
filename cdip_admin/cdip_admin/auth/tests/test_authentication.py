import pytest
from django.contrib.auth import get_user_model
from django.test import RequestFactory
from rest_framework.request import Request

from cdip_admin.auth.authentication import SimpleUserInfoAuthentication
from cdip_admin.auth.backends import SimpleUserInfoBackend
from cdip_admin.auth.tests.helpers import userinfo_header


@pytest.mark.django_db
def test_rejected_credentials_do_not_authenticate_as_a_none_user():
    """
    DRF treats any tuple as a successful authentication, so returning
    (None, ...) leaves request.user as None and group-based permissions
    raise instead of denying. A rejected header must return None so DRF
    falls through to the anonymous user and permissions deny cleanly.
    """
    User = get_user_model()
    User.objects.create(username="svc", email="svc@example.com", is_active=False)
    django_request = RequestFactory().post(
        "/api/v1.0/observations", HTTP_X_USERINFO=userinfo_header("svc", "svc@example.com")
    )

    assert SimpleUserInfoAuthentication().authenticate(Request(django_request)) is None


@pytest.mark.django_db
def test_accepted_credentials_return_the_user():
    User = get_user_model()
    User.objects.create(username="svc", email="svc@example.com")
    django_request = RequestFactory().post(
        "/api/v1.0/observations", HTTP_X_USERINFO=userinfo_header("svc", "svc@example.com")
    )

    user, _ = SimpleUserInfoAuthentication().authenticate(Request(django_request))

    assert user.username == "svc"
