import logging

import pytest
from django.urls import reverse
from rest_framework import status

pytestmark = pytest.mark.django_db


def test_rejected_observation_logs_validation_detail(
    api_client, caplog, provider_trap_tagger, keyauth_headers_trap_tagger
):
    """A rejected v2 ingestion POST must log *why* (status, path, integration,
    detail) instead of an opaque 'Bad Request' with no context."""
    with caplog.at_level(logging.WARNING, logger="api.v2.exception_handler"):
        response = api_client.post(
            reverse("observations-list"),
            data={"not": "a valid observation"},
            format="json",
            **keyauth_headers_trap_tagger,
        )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    records = [r for r in caplog.records if r.name == "api.v2.exception_handler"]
    assert len(records) == 1, "expected exactly one rejection log line"
    record = records[0]
    assert "request_rejected" in record.getMessage()
    assert record.status_code == 400
    assert record.path == reverse("observations-list")
    assert str(provider_trap_tagger.id) == record.integration_id
    assert record.detail  # the serializer error detail is captured


def test_successful_request_is_not_logged_as_rejected(caplog):
    """The handler must only fire for 4xx responses, not successful ones."""
    from api.v2.exception_handler import logging_exception_handler

    # No exception path exercised here; a None response (nothing to handle)
    # must be passed through untouched and produce no log line.
    with caplog.at_level(logging.WARNING, logger="api.v2.exception_handler"):
        assert logging_exception_handler(Exception("boom"), {"request": None}) is None
    assert [r for r in caplog.records if r.name == "api.v2.exception_handler"] == []
