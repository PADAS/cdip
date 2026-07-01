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
