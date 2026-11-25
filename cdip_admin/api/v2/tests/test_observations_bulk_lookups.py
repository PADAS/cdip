"""
A bulk observations request does its integration, source and duplicate lookups
once per request, not once per observation.
"""
import fakeredis
import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from api.v2 import utils as api_utils
from integrations.models import GundiTrace, Source

pytestmark = pytest.mark.django_db


@pytest.fixture
def dedup_db(mocker):
    db = fakeredis.FakeStrictRedis()
    mocker.patch("api.v2.utils.deduplication_db", db)
    return db


@pytest.fixture
def no_duplicates(dedup_db):
    return dedup_db


def _observation(source, minute=0, **extra):
    return {
        "source": source,
        "type": "tracking-device",
        "recorded_at": f"2026-07-24 13:{minute:02d}:00-0700",
        "location": {"lat": -51.690, "lon": -72.714},
        **extra,
    }


def _post(api_client, data, headers):
    return api_client.post(
        reverse("observations-list"), data=data, format="json", **headers
    )


def _count_queries(api_client, data, headers):
    with CaptureQueriesContext(connection) as queries:
        response = _post(api_client, data, headers)
    assert response.status_code == status.HTTP_200_OK
    return len(queries)


def test_query_count_does_not_grow_with_batch_size_for_one_source(
        api_client, mocker, mock_publisher, dedup_db,
        provider_lotek_panthera, keyauth_headers_lotek, lotek_sources
):
    mocker.patch("api.v2.utils.publisher", mock_publisher)
    external_id = str(lotek_sources[0].external_id)

    small = _count_queries(
        api_client, [_observation(external_id, minute=i) for i in range(12)], keyauth_headers_lotek
    )
    large = _count_queries(
        api_client, [_observation(external_id, minute=i) for i in range(12, 48)], keyauth_headers_lotek
    )

    assert large == small


def test_query_count_does_not_grow_with_number_of_existing_sources(
        api_client, mocker, mock_publisher, dedup_db,
        provider_lotek_panthera, keyauth_headers_lotek, make_random_sources
):
    mocker.patch("api.v2.utils.publisher", mock_publisher)
    sources = make_random_sources(provider=provider_lotek_panthera, qty=36)
    external_ids = [str(s.external_id) for s in sources]

    small = _count_queries(
        api_client, [_observation(e) for e in external_ids[:12]], keyauth_headers_lotek
    )
    large = _count_queries(
        api_client, [_observation(e, minute=1) for e in external_ids], keyauth_headers_lotek
    )

    assert large == small


def test_bulk_create_links_each_trace_to_its_own_source(
        api_client, mocker, mock_publisher, no_duplicates,
        provider_lotek_panthera, keyauth_headers_lotek, lotek_sources
):
    mocker.patch("api.v2.utils.publisher", mock_publisher)
    existing = str(lotek_sources[0].external_id)
    # Existing and new sources interleaved, each used more than once
    order = [existing, "new-a", "new-b", existing, "new-a", "new-b"] * 2

    response = _post(
        api_client, [_observation(e, minute=i) for i, e in enumerate(order)], keyauth_headers_lotek
    )

    assert response.status_code == status.HTTP_200_OK
    assert Source.objects.filter(
        integration=provider_lotek_panthera, external_id__in=["new-a", "new-b"]
    ).count() == 2
    object_ids = [item["object_id"] for item in response.json()]
    linked = [
        GundiTrace.objects.get(object_id=object_id).source.external_id
        for object_id in object_ids
    ]
    assert linked == order
    published = mock_publisher.publish.call_args.kwargs["data"]["payload"]["observations"]
    assert [obs["external_source_id"] for obs in published] == order


def test_new_source_in_bulk_takes_its_name_from_the_first_observation(
        api_client, mocker, mock_publisher, no_duplicates,
        provider_lotek_panthera, keyauth_headers_lotek
):
    mocker.patch("api.v2.utils.publisher", mock_publisher)
    data = [
        _observation("named-device", minute=i, source_name=f"Name {i}") for i in range(12)
    ]

    response = _post(api_client, data, keyauth_headers_lotek)

    assert response.status_code == status.HTTP_200_OK
    source = Source.objects.get(integration=provider_lotek_panthera, external_id="named-device")
    assert source.name == "Name 0"


def test_source_ids_sent_as_numbers_or_padded_strings_are_resolved(
        api_client, mocker, mock_publisher, no_duplicates,
        provider_lotek_panthera, keyauth_headers_lotek
):
    mocker.patch("api.v2.utils.publisher", mock_publisher)
    Source.objects.create(integration=provider_lotek_panthera, external_id="12345")
    data = [_observation(12345, minute=0), _observation(" 12345 ", minute=1)] * 6

    response = _post(api_client, data, keyauth_headers_lotek)

    assert response.status_code == status.HTTP_200_OK
    assert Source.objects.filter(integration=provider_lotek_panthera).count() == 1


def test_source_of_another_integration_is_not_reused(
        api_client, mocker, mock_publisher, no_duplicates,
        provider_lotek_panthera, keyauth_headers_lotek, provider_trap_tagger
):
    mocker.patch("api.v2.utils.publisher", mock_publisher)
    other = Source.objects.create(integration=provider_trap_tagger, external_id="shared-id")

    response = _post(
        api_client, [_observation("shared-id", minute=i) for i in range(12)], keyauth_headers_lotek
    )

    assert response.status_code == status.HTTP_200_OK
    own = Source.objects.get(integration=provider_lotek_panthera, external_id="shared-id")
    assert own.id != other.id
    object_id = response.json()[0]["object_id"]
    assert GundiTrace.objects.get(object_id=object_id).source_id == own.id


def _items(integration, source, count):
    return [
        {"integration": integration, "source": source, "recorded_at": f"t{i}"}
        for i in range(count)
    ]


def test_find_duplicate_keys_flags_only_keys_marked_as_seen(dedup_db):
    api_utils.mark_keys_as_seen(["a", "b"], expiration_time=60)

    assert api_utils.find_duplicate_keys(["a", "c", "b"]) == [True, False, True]


def test_find_duplicate_keys_does_not_mark_anything(dedup_db):
    api_utils.find_duplicate_keys(["a", "b"])

    assert dedup_db.keys() == []
    assert api_utils.find_duplicate_keys(["a", "b"]) == [False, False]


def test_find_duplicate_keys_flags_repeats_inside_one_list(dedup_db):
    assert api_utils.find_duplicate_keys(["a", "b", "a"]) == [False, False, True]


def test_marked_keys_expire(dedup_db):
    api_utils.mark_keys_as_seen(["a"], expiration_time=60)

    assert 0 < dedup_db.ttl("a") <= 60


def test_find_and_mark_use_one_round_trip_each(mocker, dedup_db):
    execute = mocker.spy(fakeredis.FakeStrictRedis().pipeline().__class__, "execute")
    keys = [f"key-{i}" for i in range(25)]

    api_utils.find_duplicate_keys(keys)
    api_utils.mark_keys_as_seen(keys, expiration_time=60)

    assert execute.call_count == 2


def test_find_and_mark_with_no_keys(dedup_db):
    assert api_utils.find_duplicate_keys([]) == []
    api_utils.mark_keys_as_seen([], expiration_time=60)


def test_deduplication_key_is_scoped_to_integration_and_source(provider_lotek_panthera, lotek_sources):
    first, second = (
        {"integration": provider_lotek_panthera, "source": source, "recorded_at": "t0"}
        for source in lotek_sources[:2]
    )

    assert api_utils.get_deduplication_key(first) == api_utils.get_deduplication_key(dict(first))
    assert api_utils.get_deduplication_key(first) != api_utils.get_deduplication_key(second)
    assert api_utils.get_deduplication_key(first).startswith(
        f"{provider_lotek_panthera.id}.{lotek_sources[0].id}."
    )


def test_is_duplicate_data_still_detects_a_repeat(dedup_db, provider_lotek_panthera, lotek_sources):
    item = _items(provider_lotek_panthera, lotek_sources[0], 1)[0]

    assert api_utils.is_duplicate_data(item, expiration_time=60) is False
    assert api_utils.is_duplicate_data(item, expiration_time=60) is True


def test_bulk_request_checks_duplicates_in_bulk_and_drops_them(
        api_client, mocker, mock_publisher, dedup_db,
        provider_lotek_panthera, keyauth_headers_lotek, lotek_sources
):
    mocker.patch("api.v2.utils.publisher", mock_publisher)
    execute = mocker.spy(fakeredis.FakeStrictRedis().pipeline().__class__, "execute")
    external_id = str(lotek_sources[0].external_id)
    data = [_observation(external_id, minute=i) for i in range(12)]
    data.append(_observation(external_id, minute=0))  # repeats the first one

    response = _post(api_client, data, keyauth_headers_lotek)

    assert response.status_code == status.HTTP_200_OK
    assert execute.call_count == 2  # One to check the request, one to mark what was published
    published = mock_publisher.publish.call_args.kwargs["data"]["payload"]["observations"]
    assert len(published) == 12
    object_ids = [item["object_id"] for item in response.json()]
    flagged = set(
        str(object_id) for object_id in
        GundiTrace.objects.filter(object_id__in=object_ids, is_duplicate=True)
        .values_list("object_id", flat=True)
    )
    assert flagged == {object_ids[-1]}

    # The same batch sent again is all duplicates: nothing is published
    mock_publisher.publish.reset_mock()
    response = _post(api_client, data, keyauth_headers_lotek)
    assert response.status_code == status.HTTP_200_OK
    assert not mock_publisher.publish.called


def _published_recorded_at(mock_publisher):
    recorded = []
    for call in mock_publisher.publish.call_args_list:
        payload = call.kwargs["data"]["payload"]
        for obs in payload.get("observations", [payload]):
            recorded.append(str(obs["recorded_at"]))
    return recorded


@pytest.mark.parametrize("count", [2, 12])  # Below and above the batch threshold
def test_observations_are_published_on_retry_after_a_failed_publish(
        mocker, mock_publisher, dedup_db, count,
        provider_lotek_panthera, keyauth_headers_lotek, lotek_sources
):
    api_client = APIClient(raise_request_exception=False)
    mocker.patch("api.v2.utils.publisher", mock_publisher)
    external_id = str(lotek_sources[0].external_id)
    data = [_observation(external_id, minute=i) for i in range(count)]

    mock_publisher.publish.side_effect = RuntimeError("Pub/Sub is unavailable")
    response = _post(api_client, data, keyauth_headers_lotek)
    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    mock_publisher.publish.reset_mock(side_effect=True)
    response = _post(api_client, data, keyauth_headers_lotek)

    assert response.status_code == status.HTTP_200_OK
    assert len(_published_recorded_at(mock_publisher)) == count
    object_ids = [item["object_id"] for item in response.json()]
    assert not GundiTrace.objects.filter(object_id__in=object_ids, is_duplicate=True).exists()


def test_retry_after_a_partly_published_request_sends_only_what_was_not_published(
        mocker, mock_publisher, dedup_db, settings,
        provider_lotek_panthera, keyauth_headers_lotek, lotek_sources
):
    settings.OBSERVATIONS_BATCH_THRESHOLD = 3
    settings.OBSERVATIONS_BATCH_MAX_ITEMS = 4
    api_client = APIClient(raise_request_exception=False)
    mocker.patch("api.v2.utils.publisher", mock_publisher)
    external_id = str(lotek_sources[0].external_id)
    data = [_observation(external_id, minute=i) for i in range(6)]

    # The first envelope (4 observations) is published, the second one fails
    mock_publisher.publish.side_effect = [None, RuntimeError("Pub/Sub is unavailable")]
    response = _post(api_client, data, keyauth_headers_lotek)
    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    mock_publisher.publish.reset_mock(side_effect=True)
    response = _post(api_client, data, keyauth_headers_lotek)

    assert response.status_code == status.HTTP_200_OK
    assert len(_published_recorded_at(mock_publisher)) == 2


def test_resending_a_duplicate_keeps_it_marked_as_seen(
        api_client, mocker, mock_publisher, dedup_db,
        provider_lotek_panthera, keyauth_headers_lotek, lotek_sources
):
    mocker.patch("api.v2.utils.publisher", mock_publisher)
    data = [_observation(str(lotek_sources[0].external_id), minute=i) for i in range(12)]
    _post(api_client, data, keyauth_headers_lotek)
    for key in dedup_db.keys():
        dedup_db.expire(key, 5)  # About to expire

    _post(api_client, data, keyauth_headers_lotek)

    assert all(dedup_db.ttl(key) > 5 for key in dedup_db.keys())
