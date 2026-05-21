import pytest
from django.contrib.auth.models import User

from core.admin import EstimatedCountPaginator


pytestmark = pytest.mark.django_db


# Use User as the target model: it's already in the test DB (auth fixture)
# and small, so the exact-count fallback is cheap and predictable. The
# pg_class estimate path is exercised by mocking ``_pg_class_estimate``;
# we don't try to fake Postgres planner state in the test database.


def _ordered_users():
    # Avoid the UnorderedObjectListWarning the paginator emits otherwise.
    return User.objects.all().order_by("id")


def _make_paginator(queryset, per_page=20):
    return EstimatedCountPaginator(queryset, per_page)


def test_count_returns_estimate_when_above_threshold(mocker):
    mocker.patch("core.admin.connection.vendor", "postgresql")
    mocker.patch.object(
        EstimatedCountPaginator, "_pg_class_estimate", return_value=50_000
    )

    paginator = _make_paginator(_ordered_users())
    assert paginator.count == 50_000


def test_count_falls_back_to_exact_when_estimate_below_threshold(mocker):
    # On a brand-new or freshly-truncated table reltuples can read as 0
    # (or a tiny seed). The paginator should fall through to the exact
    # count rather than surface the bogus estimate.
    mocker.patch("core.admin.connection.vendor", "postgresql")
    mocker.patch.object(
        EstimatedCountPaginator, "_pg_class_estimate", return_value=5
    )

    paginator = _make_paginator(_ordered_users())
    assert paginator.count == User.objects.count()


def test_count_falls_back_to_exact_when_estimate_is_none(mocker):
    # ``_pg_class_estimate`` returns None on catalog-read failure. Must
    # surface the real count rather than 0 or AttributeError.
    mocker.patch("core.admin.connection.vendor", "postgresql")
    mocker.patch.object(
        EstimatedCountPaginator, "_pg_class_estimate", return_value=None
    )

    paginator = _make_paginator(_ordered_users())
    assert paginator.count == User.objects.count()


def test_count_skips_pg_class_when_queryset_is_filtered(mocker):
    # A WHERE clause means the catalog estimate covers the whole table
    # rather than the filtered subset. We must not even ask pg_class.
    mocker.patch("core.admin.connection.vendor", "postgresql")
    estimate = mocker.patch.object(EstimatedCountPaginator, "_pg_class_estimate")

    paginator = _make_paginator(_ordered_users().filter(is_staff=True))
    _ = paginator.count

    estimate.assert_not_called()


def test_count_skips_pg_class_on_non_postgres_backend(mocker):
    mocker.patch("core.admin.connection.vendor", "sqlite")
    estimate = mocker.patch.object(EstimatedCountPaginator, "_pg_class_estimate")

    paginator = _make_paginator(_ordered_users())
    _ = paginator.count

    estimate.assert_not_called()


def test_pg_class_estimate_returns_none_on_exception(mocker):
    # Direct test of the helper's swallow-and-return-None contract — a
    # misconfigured DB or revoked SELECT on pg_class must not break the
    # admin page.
    mocker.patch("core.admin.connection.cursor", side_effect=RuntimeError("boom"))
    assert EstimatedCountPaginator._pg_class_estimate("activity_log_activitylog") is None
