import base64
import json

import pytest
from django.contrib.auth import get_user_model
from django.contrib.sessions.middleware import SessionMiddleware
from django.middleware.csrf import get_token
from django.test import RequestFactory

from cdip_admin.auth.middleware import (
    AuthenticationMiddleware,
    OidcRemoteUserMiddleware,
)


def _userinfo_header(username, email):
    return base64.b64encode(
        json.dumps({"username": username, "email": email}).encode("utf-8")
    )


def _noop_response(request):
    return None


@pytest.mark.django_db
def test_authenticated_user_with_mismatched_username_does_not_rotate_csrf_token():
    """
    OidcRemoteUserMiddleware must not re-login an already-authenticated user on
    every request. auth.login() calls rotate_token(), which regenerates the
    CSRF secret -- a form rendered earlier then fails on submit with
    "CSRF token from POST incorrect."

    The trigger is a user whose stored Django username differs from the
    Keycloak `username` claim. The backend (SimpleUserInfoBackend) resolves
    users by email, so the same user authenticates fine, but the middleware's
    username-based guard never short-circuits and logs in on every request.
    """
    User = get_user_model()
    email = "person@example.com"
    # Stored Django username == email, but Keycloak sends a short username claim.
    User.objects.create(username=email, email=email)
    header = _userinfo_header(username="person", email=email)

    factory = RequestFactory()

    # Request 1: establishes the session and logs the user in. Rotation here is
    # expected and correct -- this is where the form's CSRF token is minted.
    req1 = factory.get("/", HTTP_X_USERINFO=header)
    SessionMiddleware(_noop_response).process_request(req1)
    AuthenticationMiddleware(_noop_response).process_request(req1)
    OidcRemoteUserMiddleware(_noop_response).process_request(req1)
    assert req1.user.is_authenticated
    get_token(req1)  # mint the CSRF secret a rendered form would embed
    req1.session.save()

    # Request 2: same session, user already authenticated (e.g. the browser
    # fetching an asset or autocomplete while the form is open). This must NOT
    # rotate the CSRF token, or the still-open form's token goes stale.
    req2 = factory.get("/", HTTP_X_USERINFO=header)
    req2.session = req1.session
    AuthenticationMiddleware(_noop_response).process_request(req2)
    assert req2.user.is_authenticated  # loaded from the session
    OidcRemoteUserMiddleware(_noop_response).process_request(req2)

    assert req2.META.get("CSRF_COOKIE_NEEDS_UPDATE") is not True, (
        "CSRF token was rotated on a follow-up request for an already-"
        "authenticated user; this breaks form POSTs with 'CSRF token "
        "incorrect.'"
    )


@pytest.mark.django_db
def test_genuine_user_switch_still_logs_in_the_new_user():
    """
    The no-rotation guard must not defeat the security behavior: when the header
    presents a *different* user than the one in the session, the middleware must
    switch the session to the new user (and rotate the token, as login does).
    """
    User = get_user_model()
    first = User.objects.create(username="first@example.com", email="first@example.com")
    User.objects.create(username="second@example.com", email="second@example.com")

    factory = RequestFactory()

    # Session belongs to `first`.
    req1 = factory.get("/", HTTP_X_USERINFO=_userinfo_header("first@example.com", "first@example.com"))
    SessionMiddleware(_noop_response).process_request(req1)
    AuthenticationMiddleware(_noop_response).process_request(req1)
    OidcRemoteUserMiddleware(_noop_response).process_request(req1)
    assert req1.user.email == "first@example.com"
    req1.session.save()

    # A request arrives in the same session but with `second` in the header.
    req2 = factory.get("/", HTTP_X_USERINFO=_userinfo_header("second@example.com", "second@example.com"))
    req2.session = req1.session
    AuthenticationMiddleware(_noop_response).process_request(req2)
    OidcRemoteUserMiddleware(_noop_response).process_request(req2)

    assert req2.user.email == "second@example.com"
    assert req2.META.get("CSRF_COOKIE_NEEDS_UPDATE") is True, (
        "Switching the session to a different user must rotate the CSRF token."
    )


@pytest.mark.django_db
def test_matching_username_short_circuits_without_rotation():
    """
    The common case -- stored Django username equals the `username` claim --
    must short-circuit without re-login or token rotation.
    """
    User = get_user_model()
    User.objects.create(username="match@example.com", email="match@example.com")
    header = _userinfo_header("match@example.com", "match@example.com")

    factory = RequestFactory()
    req1 = factory.get("/", HTTP_X_USERINFO=header)
    SessionMiddleware(_noop_response).process_request(req1)
    AuthenticationMiddleware(_noop_response).process_request(req1)
    OidcRemoteUserMiddleware(_noop_response).process_request(req1)
    req1.session.save()

    req2 = factory.get("/", HTTP_X_USERINFO=header)
    req2.session = req1.session
    AuthenticationMiddleware(_noop_response).process_request(req2)
    OidcRemoteUserMiddleware(_noop_response).process_request(req2)

    assert req2.META.get("CSRF_COOKIE_NEEDS_UPDATE") is not True
