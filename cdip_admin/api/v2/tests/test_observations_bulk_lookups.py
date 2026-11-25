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

from api.v2 import utils as api_utils
from integrations.models import GundiTrace, Source

pytestmark = pytest.mark.django_db


@pytest.fixture
def dedup_db(mocker):
    db = fakeredis.FakeStrictRedis()
    mocker.patch("api.v2.utils.deduplication_db", db)
    return db


@pytest.fixture
def no_duplicates(mocker):
    mocker.patch("api.v2.utils.is_duplicate_data", return_value=False)
    mocker.patch(
        "api.v2.utils.find_duplicate_data",
        side_effect=lambda items, expiration_time: [False] * len(items),
    )


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


def test_find_duplicate_data_flags_items_seen_before(dedup_db, provider_lotek_panthera, lotek_sources):
    items = [
        {"integration": provider_lotek_panthera, "source": lotek_sources[0], "recorded_at": f"t{i}"}
        for i in range(3)
    ]

    first = api_utils.find_duplicate_data(items, expiration_time=60)
    second = api_utils.find_duplicate_data(items, expiration_time=60)

    assert first == [False, False, False]
    assert second == [True, True, True]


def test_find_duplicate_data_flags_repeats_inside_one_batch(dedup_db, provider_lotek_panthera, lotek_sources):
    item = {"integration": provider_lotek_panthera, "source": lotek_sources[0], "recorded_at": "t0"}
    other = {"integration": provider_lotek_panthera, "source": lotek_sources[1], "recorded_at": "t0"}

    flags = api_utils.find_duplicate_data([item, other, dict(item)], expiration_time=60)

    assert flags == [False, False, True]


def test_find_duplicate_data_keys_expire(dedup_db, provider_lotek_panthera, lotek_sources):
    item = {"integration": provider_lotek_panthera, "source": lotek_sources[0], "recorded_at": "t0"}

    api_utils.find_duplicate_data([item], expiration_time=60)

    keys = dedup_db.keys()
    assert len(keys) == 1
    assert 0 < dedup_db.ttl(keys[0]) <= 60


def test_find_duplicate_data_uses_one_round_trip(mocker, dedup_db, provider_lotek_panthera, lotek_sources):
    execute = mocker.spy(fakeredis.FakeStrictRedis().pipeline().__class__, "execute")
    items = [
        {"integration": provider_lotek_panthera, "source": lotek_sources[0], "recorded_at": f"t{i}"}
        for i in range(25)
    ]

    api_utils.find_duplicate_data(items, expiration_time=60)

    assert execute.call_count == 1


def test_find_duplicate_data_with_no_items(dedup_db):
    assert api_utils.find_duplicate_data([], expiration_time=60) == []


def test_is_duplicate_data_still_detects_a_repeat(dedup_db, provider_lotek_panthera, lotek_sources):
    item = {"integration": provider_lotek_panthera, "source": lotek_sources[0], "recorded_at": "t0"}

    assert api_utils.is_duplicate_data(item, expiration_time=60) is False
    assert api_utils.is_duplicate_data(item, expiration_time=60) is True


def test_bulk_request_checks_duplicates_in_one_round_trip_and_drops_them(
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
    assert execute.call_count == 1
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
