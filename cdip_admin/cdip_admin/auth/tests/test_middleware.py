import base64
import json

import pytest
from django.conf import settings
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


@pytest.mark.django_db
def test_api_request_without_session_cookie_authenticates_without_logging_in():
    """
    Machine clients (pull-action runners, dispatchers, Cloud Functions) never
    send a session cookie, so every API call used to be a "first login":
    auth.login() wrote auth_user.last_login (one hot row shared by every
    caller), inserted a django_session row and rotated the CSRF token -- per
    request, at ingestion volume. A cookie-less request to an API path must
    authenticate from the header without any of that.
    """
    User = get_user_model()
    user = User.objects.create(username="svc@example.com", email="svc@example.com")
    assert user.last_login is None
    header = _userinfo_header("svc@example.com", "svc@example.com")

    req = RequestFactory().post("/api/v1.0/observations", HTTP_X_USERINFO=header)
    SessionMiddleware(_noop_response).process_request(req)
    AuthenticationMiddleware(_noop_response).process_request(req)
    OidcRemoteUserMiddleware(_noop_response).process_request(req)

    assert req.user.is_authenticated
    assert req.user.email == "svc@example.com"
    user.refresh_from_db()
    assert user.last_login is None, "stateless API request must not write last_login"
    assert req.session.session_key is None and not req.session.modified, (
        "stateless API request must not create or touch a session"
    )
    assert req.META.get("CSRF_COOKIE_NEEDS_UPDATE") is not True


@pytest.mark.django_db
def test_v2_api_request_without_session_cookie_is_stateless_by_default():
    """The v2 ingestion endpoints are the highest-volume callers."""
    User = get_user_model()
    user = User.objects.create(username="svc@example.com", email="svc@example.com")
    header = _userinfo_header("svc@example.com", "svc@example.com")

    req = RequestFactory().post("/v2/observations/", HTTP_X_USERINFO=header)
    SessionMiddleware(_noop_response).process_request(req)
    AuthenticationMiddleware(_noop_response).process_request(req)
    OidcRemoteUserMiddleware(_noop_response).process_request(req)

    assert req.user.is_authenticated
    user.refresh_from_db()
    assert user.last_login is None
    assert req.session.session_key is None


@pytest.mark.django_db
def test_ui_request_without_session_cookie_still_logs_in():
    """
    A browser's first visit has no cookie either. Non-API paths must keep the
    session-establishing login, or the UI could never start a session.
    """
    User = get_user_model()
    user = User.objects.create(username="person@example.com", email="person@example.com")
    header = _userinfo_header("person@example.com", "person@example.com")

    req = RequestFactory().get("/integrations/", HTTP_X_USERINFO=header)
    SessionMiddleware(_noop_response).process_request(req)
    AuthenticationMiddleware(_noop_response).process_request(req)
    OidcRemoteUserMiddleware(_noop_response).process_request(req)

    assert req.user.is_authenticated
    assert req.session.session_key is not None, "UI login must establish a session"
    user.refresh_from_db()
    assert user.last_login is not None


@pytest.mark.django_db
def test_api_request_with_a_stale_session_cookie_is_stateless():
    """
    A cookie that no longer resolves to a session (expired, cleared by
    clearsessions, or pasted into a script) carries no session user. Treating
    it as a browser would run auth.login() on every request from that client,
    which is exactly the per-request write this rule removes.
    """
    User = get_user_model()
    user = User.objects.create(username="svc@example.com", email="svc@example.com")
    header = _userinfo_header("svc@example.com", "svc@example.com")

    req = RequestFactory().post("/api/v1.0/observations", HTTP_X_USERINFO=header)
    req.COOKIES[settings.SESSION_COOKIE_NAME] = "expired-or-unknown-session-key"
    SessionMiddleware(_noop_response).process_request(req)
    AuthenticationMiddleware(_noop_response).process_request(req)
    OidcRemoteUserMiddleware(_noop_response).process_request(req)

    assert req.user.is_authenticated
    user.refresh_from_db()
    assert user.last_login is None
    assert req.session.session_key is None and not req.session.modified


@pytest.mark.django_db
def test_api_request_with_a_live_session_keeps_the_session():
    """
    A browser that logged in on a UI page and then reaches an API path (the
    browsable API, the v2 docs) keeps its session: no second login, no new
    session row.
    """
    User = get_user_model()
    user = User.objects.create(username="person@example.com", email="person@example.com")
    header = _userinfo_header("person@example.com", "person@example.com")

    first = RequestFactory().get("/integrations/", HTTP_X_USERINFO=header)
    SessionMiddleware(_noop_response).process_request(first)
    AuthenticationMiddleware(_noop_response).process_request(first)
    OidcRemoteUserMiddleware(_noop_response).process_request(first)
    first.session.save()
    session_key = first.session.session_key
    user.refresh_from_db()
    first_login = user.last_login
    assert session_key and first_login

    second = RequestFactory().get("/api/v1.0/organizations", HTTP_X_USERINFO=header)
    second.COOKIES[settings.SESSION_COOKIE_NAME] = session_key
    SessionMiddleware(_noop_response).process_request(second)
    AuthenticationMiddleware(_noop_response).process_request(second)
    OidcRemoteUserMiddleware(_noop_response).process_request(second)

    assert second.user.is_authenticated
    assert second.session.session_key == session_key
    user.refresh_from_db()
    assert user.last_login == first_login


@pytest.mark.django_db
def test_api_request_is_stateless_under_a_mount_prefix():
    """
    The prefixes are written against the URLconf path, so a portal mounted
    under SCRIPT_NAME must still recognise its API routes.
    """
    User = get_user_model()
    user = User.objects.create(username="svc@example.com", email="svc@example.com")
    header = _userinfo_header("svc@example.com", "svc@example.com")

    req = RequestFactory().post(
        "/api/v1.0/observations", HTTP_X_USERINFO=header, SCRIPT_NAME="/portal"
    )
    SessionMiddleware(_noop_response).process_request(req)
    AuthenticationMiddleware(_noop_response).process_request(req)
    OidcRemoteUserMiddleware(_noop_response).process_request(req)

    assert req.path == "/portal/api/v1.0/observations"
    assert req.user.is_authenticated
    user.refresh_from_db()
    assert user.last_login is None
    assert req.session.session_key is None and not req.session.modified
