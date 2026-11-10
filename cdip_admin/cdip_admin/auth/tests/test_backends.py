import pytest
from django.contrib.auth import get_user_model
from django.db.utils import OperationalError
from django.test import RequestFactory

from cdip_admin.auth.backends import SimpleUserInfoBackend


def _request():
    req = RequestFactory().get("/")
    req.session = {}
    return req


@pytest.mark.django_db
def test_identity_lookup_is_cached(django_assert_num_queries):
    """
    Every authenticated request runs through this backend, including the
    high-volume ingestion path. The user lookup must hit the DB only on the
    first request for a given identity; subsequent requests are served from
    the cache without querying Postgres.
    """
    User = get_user_model()
    User.objects.create(username="svc", email="svc@example.com")
    backend = SimpleUserInfoBackend()
    user_info = {"username": "svc", "email": "svc@example.com"}

    # First call resolves the user from the DB and populates the cache.
    first = backend.authenticate(_request(), user_info=user_info)
    assert first is not None and first.email == "svc@example.com"

    # Second call must not touch the database for identity resolution.
    with django_assert_num_queries(0):
        second = backend.authenticate(_request(), user_info=user_info)
    assert second.email == "svc@example.com"


@pytest.mark.django_db
def test_transient_db_error_propagates_and_is_not_masked_as_auth_failure(mocker):
    """
    A dropped DB connection during identity resolution must propagate (surfaced
    as a retryable 5xx) rather than being swallowed into a silent None, which
    the caller would render as a misleading 401/403 and clients would not retry.
    """
    mocker.patch.object(
        SimpleUserInfoBackend,
        "_get_or_create_user",
        side_effect=OperationalError("server closed the connection unexpectedly"),
    )
    with pytest.raises(OperationalError):
        SimpleUserInfoBackend().authenticate(
            _request(), user_info={"username": "svc", "email": "svc@example.com"}
        )


@pytest.mark.django_db
def test_unparseable_userinfo_is_a_normal_auth_failure():
    """A missing/blank identity is a genuine auth failure -> None (not an error)."""
    backend = SimpleUserInfoBackend()
    assert backend.authenticate(_request(), user_info={}) is None
    assert backend.authenticate(_request(), user_info={"email": "x@example.com"}) is None


@pytest.mark.django_db
def test_client_id_is_exposed_on_the_request_and_never_on_the_session(mocker):
    """
    IsServiceAccount reads client_id from the request, which the DRF
    authenticator populates on every API call. Writing it to the session
    would dirty the session (a django_session row per cookie-less call) and
    leave a stale client_id behind after the header stops carrying it.
    """
    mocker.patch.object(SimpleUserInfoBackend, "_client_profile_exists", return_value=True)
    User = get_user_model()
    User.objects.create(username="svc", email="svc@example.com")
    req = RequestFactory().get("/")
    req.session = {}

    user = SimpleUserInfoBackend().authenticate(
        req, user_info={"username": "svc", "email": "svc@example.com", "client_id": "svc-client"}
    )

    assert user is not None
    assert req.client_id == "svc-client"
    assert req.session == {}


@pytest.mark.django_db
def test_inactive_user_gets_no_client_id(mocker):
    """
    A deactivated service account must not pass IsServiceAccount: the backend
    returns None, and DRF then carries user=None, so client_id must not be
    attached either.
    """
    mocker.patch.object(SimpleUserInfoBackend, "_client_profile_exists", return_value=True)
    User = get_user_model()
    User.objects.create(username="svc", email="svc@example.com", is_active=False)
    req = RequestFactory().post("/api/v1.0/observations")
    req.session = {}

    user = SimpleUserInfoBackend().authenticate(
        req, user_info={"username": "svc", "email": "svc@example.com", "client_id": "svc-client"}
    )

    assert user is None
    assert getattr(req, "client_id", None) is None


@pytest.mark.django_db
def test_client_id_set_through_a_drf_request_is_visible_to_the_permission(mocker):
    """
    In production the backend runs inside DRF's authenticator with a DRF
    Request, and the permission reads from the same wrapper. The value must
    land on the inner Django request so both sides see it.
    """
    from rest_framework.request import Request

    from core.permissions import IsServiceAccount

    mocker.patch.object(SimpleUserInfoBackend, "_client_profile_exists", return_value=True)
    User = get_user_model()
    User.objects.create(username="svc", email="svc@example.com")
    django_request = RequestFactory().post("/api/v1.0/observations")
    django_request.session = {}
    drf_request = Request(django_request)

    SimpleUserInfoBackend().authenticate(
        drf_request, user_info={"username": "svc", "email": "svc@example.com", "client_id": "svc-client"}
    )

    assert django_request.client_id == "svc-client"
    assert IsServiceAccount().has_permission(drf_request, view=None) is True


@pytest.mark.django_db
def test_rejected_credentials_clear_a_client_id_left_by_an_earlier_pass(mocker):
    """
    The middleware and DRF each run the backend on the same Django request.
    A client_id from an earlier accepted pass must not survive a later pass
    whose credentials are rejected.
    """
    mocker.patch.object(SimpleUserInfoBackend, "_client_profile_exists", return_value=True)
    User = get_user_model()
    User.objects.create(username="svc", email="svc@example.com", is_active=False)
    req = RequestFactory().post("/api/v1.0/observations")
    req.session = {}
    req.client_id = "svc-client"

    user = SimpleUserInfoBackend().authenticate(
        req, user_info={"username": "svc", "email": "svc@example.com", "client_id": "svc-client"}
    )

    assert user is None
    assert req.client_id is None
