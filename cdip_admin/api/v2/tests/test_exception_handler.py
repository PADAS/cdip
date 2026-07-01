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


def test_unhandled_exception_passes_through_without_logging(caplog):
    """When DRF's handler returns None (exception it doesn't turn into a response),
    ours must pass the None through untouched and emit no log line."""
    from api.v2.exception_handler import logging_exception_handler

    with caplog.at_level(logging.WARNING, logger="api.v2.exception_handler"):
        assert logging_exception_handler(Exception("boom"), {"request": None}) is None
    assert [r for r in caplog.records if r.name == "api.v2.exception_handler"] == []


def test_summarize_detail_skips_valid_items_and_caps_large_batches():
    """Bulk error detail must surface only error-bearing items (by index) without
    stringifying the whole batch, and stay bounded."""
    from api.v2 import exception_handler as eh

    # A large batch that is valid except for two items.
    batch = [{} for _ in range(5000)]
    batch[3] = {"recorded_at": ["This field is required."]}
    batch[4] = {"location": ["Invalid location."]}

    summary = eh._summarize_detail(batch)

    assert "5000" in summary  # item_count reported
    assert "recorded_at" in summary and "location" in summary  # the real errors
    assert len(summary) <= eh._MAX_DETAIL_CHARS + len("…(truncated)")
