from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory

from cdip_admin.auth.stateless import is_stateless_request


def _request(path, user=None, method="get"):
    req = getattr(RequestFactory(), method)(path)
    req.user = user or AnonymousUser()
    return req


def test_api_path_without_a_session_user_is_stateless():
    assert is_stateless_request(_request("/api/v1.0/observations", method="post"))


def test_api_path_with_an_authenticated_session_user_is_not_stateless(django_user_model, db):
    user = django_user_model.objects.create(username="person", email="person@example.com")

    assert not is_stateless_request(_request("/api/v1.0/organizations", user=user))


def test_non_api_path_is_never_stateless():
    assert not is_stateless_request(_request("/integrations/"))


def test_string_prefix_setting_is_one_prefix_not_a_character_set(settings):
    """
    A local override written as a string must not explode into single
    characters, where "/" would make every cookie-less browser visit stateless.
    """
    settings.STATELESS_AUTH_PATH_PREFIXES = "/api/"

    assert is_stateless_request(_request("/api/v1.0/devices"))
    assert not is_stateless_request(_request("/integrations/"))


def test_prefix_entries_are_stripped_and_empties_ignored(settings):
    """An env override such as "/api/, /v2/" must still match the v2 routes."""
    settings.STATELESS_AUTH_PATH_PREFIXES = ["/api/", " /v2/", ""]

    assert is_stateless_request(_request("/v2/observations/", method="post"))
    assert not is_stateless_request(_request("/integrations/"))
