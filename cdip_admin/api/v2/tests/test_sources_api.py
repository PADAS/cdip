import pytest
from django.urls import reverse
from rest_framework import status

from integrations.models import Source


pytestmark = pytest.mark.django_db


def _test_list_sources(api_client, user, expected_sources, filters=None):
    request_data = {}
    if filters:
        request_data.update(filters)
    api_client.force_authenticate(user)
    response = api_client.get(
        reverse("sources-list"),
        data=request_data
    )
    assert response.status_code == status.HTTP_200_OK
    response_data = response.json()
    sources = response_data["results"]
    # Check that the returned sources are the expected ones
    expected_sources_ids = [s.external_id for s in expected_sources]
    assert len(sources) == len(expected_sources_ids)
    for source in sources:
        assert "external_id" in source
        assert source.get("external_id") in expected_sources_ids
        assert "status" in source
        assert "provider" in source
        assert "destinations" in source
        assert "routing_rules" in source
        assert "update_frequency" in source
        assert "last_update" in source
        assert "created_at" in source


def test_list_sources_as_superuser(
        api_client, superuser, organization, provider_lotek_panthera, provider_movebank_ewt,
        integrations_list_er, lotek_sources, movebank_sources, route_1, route_2,

):
    _test_list_sources(
        api_client=api_client,
        user=superuser,
        # The superuser can see all the sources
        expected_sources=lotek_sources+movebank_sources
    )


def test_list_sources_as_org_admin(
        api_client, org_admin_user, organization, provider_lotek_panthera, provider_movebank_ewt,
        integrations_list_er, lotek_sources, movebank_sources, route_1, route_2
):
    _test_list_sources(
        api_client=api_client,
        user=org_admin_user,  # Belongs to one organization
        # Org admins can only see sources of their organizations
        expected_sources=lotek_sources
    )


def test_list_sources_as_org_admin_2(
        api_client, org_admin_user_2, organization, provider_lotek_panthera, provider_movebank_ewt,
        integrations_list_er, lotek_sources, movebank_sources, route_1, route_2
):
    _test_list_sources(
        api_client=api_client,
        user=org_admin_user_2,  # Belongs to one organization
        # Org admins can only see sources of their organizations
        expected_sources=movebank_sources
    )


def test_list_sources_as_org_viewer(
        api_client, org_viewer_user, organization, provider_lotek_panthera, provider_movebank_ewt,
        integrations_list_er, lotek_sources, movebank_sources, route_1, route_2
):
    _test_list_sources(
        api_client=api_client,
        user=org_viewer_user,  # Belongs to one organization
        # Org viewer can only see sources of their organizations
        expected_sources=lotek_sources
    )


def test_filter_sources_by_external_id_as_superuser(
        api_client, superuser, organization, provider_lotek_panthera, provider_movebank_ewt,
        integrations_list_er, lotek_sources, movebank_sources, route_1, route_2
):
    selected_sources = lotek_sources[1::2] + movebank_sources[:2]  # pick some sources semi-randomly
    _test_list_sources(
        api_client=api_client,
        user=superuser,
        filters={
            "external_id__in": ",".join(
                [s.external_id for s in selected_sources]
            )
        },
        expected_sources=selected_sources
    )


def test_filter_sources_by_external_id_as_org_admin(
        api_client, org_admin_user_2, organization, provider_lotek_panthera, provider_movebank_ewt,
        integrations_list_er, lotek_sources, movebank_sources, route_1, route_2
):
    selected_sources = movebank_sources[::2]  # pick some sources semi-randomly
    _test_list_sources(
        api_client=api_client,
        user=org_admin_user_2,
        filters={
            "external_id__in": ",".join(
                [s.external_id for s in selected_sources]
            )
        },
        expected_sources=selected_sources
    )


def test_filter_sources_by_external_id_as_org_viewer(
        api_client, org_viewer_user, organization, provider_lotek_panthera, provider_movebank_ewt,
        integrations_list_er, lotek_sources, movebank_sources, route_1, route_2
):
    _test_list_sources(
        api_client=api_client,
        user=org_viewer_user,
        filters={
            "external_id__in": lotek_sources[0].external_id  # Select a single source
        },
        expected_sources=[lotek_sources[0]]
    )


def test_filter_sources_by_provider_type_as_superuser(
        api_client, superuser, organization, provider_lotek_panthera, provider_movebank_ewt,
        integrations_list_er, lotek_sources, movebank_sources, route_1, route_2
):
    _test_list_sources(
        api_client=api_client,
        user=superuser,
        filters={
            "provider_type__in": f"{provider_movebank_ewt.type.value},{provider_lotek_panthera.type.value}"
        },
        expected_sources=movebank_sources+lotek_sources
    )


def test_filter_sources_by_provider_type_as_org_admin(
        api_client, org_admin_user_2, organization, provider_lotek_panthera, provider_movebank_ewt,
        integrations_list_er, lotek_sources, movebank_sources, route_1, route_2
):
    _test_list_sources(
        api_client=api_client,
        user=org_admin_user_2,
        filters={
            "provider_type": provider_movebank_ewt.type.value
        },
        expected_sources=movebank_sources
    )


def test_filter_sources_by_provider_type_as_org_viewer(
        api_client, org_viewer_user_2, organization, provider_lotek_panthera, provider_movebank_ewt,
        integrations_list_er, lotek_sources, movebank_sources, route_1, route_2
):
    _test_list_sources(
        api_client=api_client,
        user=org_viewer_user_2,
        filters={
            "provider_type": provider_movebank_ewt.type.value
        },
        expected_sources=movebank_sources
    )


def test_filter_sources_by_destination_type_as_superuser(
        api_client, superuser, organization, provider_lotek_panthera, provider_movebank_ewt,
        integrations_list_er, lotek_sources, movebank_sources, route_1, route_2, integration_type_er
):
    _test_list_sources(
        api_client=api_client,
        user=superuser,
        filters={
            "destination_type": integration_type_er.value
        },
        expected_sources=lotek_sources+movebank_sources
    )


def test_filter_sources_by_destination_type_as_org_admin(
        api_client, org_admin_user, organization, provider_lotek_panthera, provider_movebank_ewt,
        integrations_list_er, lotek_sources, movebank_sources, route_1, route_2, integration_type_er
):
    _test_list_sources(
        api_client=api_client,
        user=org_admin_user,
        filters={
            "destination_type": integration_type_er.value
        },
        expected_sources=lotek_sources
    )


def test_filter_sources_by_destination_type_as_org_viewer(
        api_client, org_viewer_user_2, organization, provider_lotek_panthera, provider_movebank_ewt,
        integrations_list_er, lotek_sources, movebank_sources, route_1, route_2, integration_type_er
):
    _test_list_sources(
        api_client=api_client,
        user=org_viewer_user_2,
        filters={
            "destination_type": integration_type_er.value
        },
        expected_sources=movebank_sources
    )


def test_filter_sources_by_multiple_destination_urls_as_superuser(
        api_client, superuser, organization, provider_lotek_panthera, provider_movebank_ewt,
        integrations_list_er, lotek_sources, movebank_sources, route_1, route_2, integration_type_er
):
    selected_destinations = integrations_list_er[:6]  # All the sources are connected to the first 6
    _test_list_sources(
        api_client=api_client,
        user=superuser,
        filters={
            "destination_url__in": ",".join(
                [i.base_url for i in selected_destinations]
            )
        },
        expected_sources=movebank_sources+lotek_sources
    )


def test_filter_sources_by_multiple_destination_urls_as_org_admin(
        api_client, org_admin_user, organization, provider_lotek_panthera, provider_movebank_ewt,
        integrations_list_er, lotek_sources, movebank_sources, route_1, route_2, integration_type_er
):
    selected_destinations = integrations_list_er  # All the destinations
    _test_list_sources(
        api_client=api_client,
        user=org_admin_user,
        filters={
            "destination_url__in": ",".join(
                [i.base_url for i in selected_destinations]
            )
        },
        expected_sources=lotek_sources  # This org admin can only see lotek sources
    )


def test_filter_sources_by_multiple_destination_urls_as_org_viewer(
        api_client, org_viewer_user_2, organization, provider_lotek_panthera, provider_movebank_ewt,
        integrations_list_er, lotek_sources, movebank_sources, route_1, route_2, integration_type_er
):
    selected_destinations = integrations_list_er  # All the destinations
    _test_list_sources(
        api_client=api_client,
        user=org_viewer_user_2,
        filters={
            "destination_url__in": ",".join(
                [i.base_url for i in selected_destinations]
            )
        },
        expected_sources=movebank_sources  # This org viewer can only see movebank sources
    )


def test_filter_sources_by_owner_exact_as_superuser(
        api_client, superuser, organization, other_organization, provider_lotek_panthera, provider_movebank_ewt,
        integrations_list_er, lotek_sources, movebank_sources, route_1, route_2, integration_type_er
):
    _test_list_sources(
        api_client=api_client,
        user=superuser,
        filters={
            "owner": str(other_organization.id)
        },
        expected_sources=movebank_sources
    )


def test_filter_sources_by_multiple_owners_as_superuser(
        api_client, superuser, organization, other_organization, provider_lotek_panthera, provider_movebank_ewt,
        integrations_list_er, lotek_sources, movebank_sources, route_1, route_2, integration_type_er
):
    _test_list_sources(
        api_client=api_client,
        user=superuser,
        filters={
            "owner__in": ",".join([str(organization.id), str(other_organization.id)])
        },
        expected_sources=lotek_sources+movebank_sources
    )


def test_filter_sources_by_owner_exact_as_org_admin(
        api_client, org_admin_user, organization, other_organization, provider_lotek_panthera, provider_movebank_ewt,
        integrations_list_er, lotek_sources, movebank_sources, route_1, route_2, integration_type_er
):
    _test_list_sources(
        api_client=api_client,
        user=org_admin_user,
        filters={
            "owner": str(organization.id)
        },
        expected_sources=lotek_sources
    )


def test_filter_sources_by_multiple_owners_as_org_admin(
        api_client, org_admin_user, organization, other_organization, provider_lotek_panthera, provider_movebank_ewt,
        integrations_list_er, lotek_sources, movebank_sources, route_1, route_2, integration_type_er
):
    _test_list_sources(
        api_client=api_client,
        user=org_admin_user,
        filters={
            "owner__in": ",".join([str(organization.id), str(other_organization.id)])
        },
        expected_sources=lotek_sources
    )


def test_filter_sources_by_owner_exact_as_org_viewer(
        api_client, org_viewer_user, organization, other_organization, provider_lotek_panthera, provider_movebank_ewt,
        integrations_list_er, lotek_sources, movebank_sources, route_1, route_2, integration_type_er
):
    _test_list_sources(
        api_client=api_client,
        user=org_viewer_user,
        filters={
            "owner": str(organization.id)
        },
        expected_sources=lotek_sources
    )


def test_filter_sources_by_multiple_owners_as_org_viewer(
        api_client, org_viewer_user_2, organization, other_organization, provider_lotek_panthera, provider_movebank_ewt,
        integrations_list_er, lotek_sources, movebank_sources, route_1, route_2, integration_type_er
):
    _test_list_sources(
        api_client=api_client,
        user=org_viewer_user_2,
        filters={
            "owner__in": ",".join([str(organization.id), str(other_organization.id)])
        },
        expected_sources=movebank_sources
    )


# def _test_global_search_sources(
#         api_client, user, search_term, expected_sources,  extra_filters=None, search_fields=None
# ):
#     api_client.force_authenticate(user)
#     query_params = {
#         "search": search_term,
#     }
#     if search_fields:
#         query_params["search_fields"] = search_fields
#     if extra_filters:
#         query_params.update(extra_filters)
#     response = api_client.get(
#         reverse('sources-list'),
#         data=query_params
#     )
#     assert response.status_code == status.HTTP_200_OK
#     response_data = response.json()
#     sources = response_data["results"]
#     # Check that the returned sources are the expected ones
#     expected_sources_ids = [str(i.id) for i in expected_sources]
#     assert len(sources) == len(expected_sources_ids)
#     for conn in sources:
#         assert conn.get("id") in expected_sources_ids


def test_global_search_sources_as_superuser(
        api_client, superuser, organization, other_organization,
        integration_type_er, integration_type_movebank, integration_type_lotek,
        integration_type_smart, smart_action_auth, smart_action_push_events,
        integrations_list_er, lotek_sources, movebank_sources, provider_movebank_ewt, provider_lotek_panthera,
        route_1, route_2
):
    _test_list_sources(
        api_client=api_client,
        user=superuser,
        filters={
            "search": "pamdas.org",  # Looking sources sending data to earth ranger sites
        },
        expected_sources=lotek_sources+movebank_sources  # All the sources
    )


def test_global_search_sources_as_org_admin(
        api_client, org_admin_user, organization, other_organization,
        integration_type_er, integration_type_movebank, integration_type_lotek,
        integration_type_smart, smart_action_auth, smart_action_push_events,
        integrations_list_er, lotek_sources, movebank_sources, provider_movebank_ewt, provider_lotek_panthera,
        route_1, route_2
):
    _test_list_sources(
        api_client=api_client,
        user=org_admin_user,
        filters={
            "search": "lotek",  # Looking sources getting data from lotek
        },
        expected_sources=lotek_sources
    )


def test_global_search_sources_as_org_viewer(
        api_client, org_viewer_user_2, organization, other_organization,
        integration_type_er, integration_type_movebank, integration_type_lotek,
        integration_type_smart, smart_action_auth, smart_action_push_events,
        integrations_list_er, lotek_sources, movebank_sources, provider_movebank_ewt, provider_lotek_panthera,
        route_1, route_2
):
    _test_list_sources(
        api_client=api_client,
        user=org_viewer_user_2,
        filters={
            "search": "movebank",  # Looking sources getting data from movebank
        },
        expected_sources=movebank_sources
    )


# ---- Manual source creation (GUNDI-5178) ----------------------------------


def _post_source(api_client, user, provider_id, external_id="new-collar-001", name=None):
    payload = {"provider": provider_id, "external_id": external_id}
    if name is not None:
        payload["name"] = name
    api_client.force_authenticate(user)
    return api_client.post(reverse("sources-list"), data=payload, format="json")


def _test_create_source(api_client, user, provider, external_id="new-collar-001", name="Kifaru"):
    response = _post_source(
        api_client, user, str(provider.id), external_id=external_id, name=name
    )
    assert response.status_code == status.HTTP_201_CREATED, response.content
    response_data = response.json()
    source = Source.objects.get(id=response_data["id"])
    assert source.external_id == external_id
    assert source.integration_id == provider.id
    if name is not None:
        assert source.name == name
    # The write response is rendered with the retrieve serializer, so the UI can use it
    # without a follow-up GET.
    for field in (
        "id", "external_id", "status", "provider", "destinations",
        "routing_rules", "update_frequency", "last_update", "created_at",
    ):
        assert field in response_data
    return source


def test_create_source_as_superuser(
        api_client, superuser, organization, provider_lotek_panthera
):
    _test_create_source(api_client, superuser, provider_lotek_panthera)


def test_create_source_as_org_admin(
        api_client, org_admin_user, organization, provider_lotek_panthera
):
    _test_create_source(api_client, org_admin_user, provider_lotek_panthera)


def test_create_source_without_name(
        api_client, org_admin_user, organization, provider_lotek_panthera
):
    source = _test_create_source(
        api_client, org_admin_user, provider_lotek_panthera, name=None
    )
    assert source.name == ""


def test_create_source_that_has_never_reported(
        api_client, org_admin_user, organization, provider_lotek_panthera
):
    # The point of the endpoint: a device can be listed in a routing filter before it has
    # ever sent data. Such a source has no SourceState, which the API reports as "unknown".
    response = _post_source(
        api_client, org_admin_user, str(provider_lotek_panthera.id), external_id="not-yet-seen"
    )
    assert response.status_code == status.HTTP_201_CREATED, response.content
    assert response.json()["last_update"] == "unknown"


def test_cannot_create_source_as_org_viewer(
        api_client, org_viewer_user, organization, provider_lotek_panthera
):
    response = _post_source(api_client, org_viewer_user, str(provider_lotek_panthera.id))
    assert response.status_code == status.HTTP_403_FORBIDDEN, response.content
    assert not Source.objects.filter(external_id="new-collar-001").exists()


def test_cannot_create_source_for_another_org_provider_as_org_admin(
        api_client, org_admin_user, organization, other_organization, provider_movebank_ewt
):
    response = _post_source(api_client, org_admin_user, str(provider_movebank_ewt.id))
    assert response.status_code == status.HTTP_403_FORBIDDEN, response.content
    assert not Source.objects.filter(external_id="new-collar-001").exists()


def test_create_duplicate_source_is_rejected(
        api_client, org_admin_user, organization, provider_lotek_panthera, lotek_sources
):
    existing = lotek_sources[0]
    response = _post_source(
        api_client, org_admin_user, str(provider_lotek_panthera.id),
        external_id=existing.external_id,
    )
    assert response.status_code == status.HTTP_409_CONFLICT, response.content
    assert "already exists" in response.content.decode()


def test_create_source_reusing_external_id_from_another_provider(
        api_client, superuser, organization, other_organization,
        provider_lotek_panthera, provider_movebank_ewt, movebank_sources
):
    # external_id is unique per provider, not globally — the same collar id may legitimately
    # exist under two providers. This is why routing's filter payload is keyed by provider.
    borrowed = movebank_sources[0].external_id
    _test_create_source(
        api_client, superuser, provider_lotek_panthera, external_id=borrowed
    )


@pytest.mark.parametrize(
    "provider_id",
    [
        pytest.param("not-a-uuid", id="malformed-provider"),
        pytest.param("6b8f3c1e-0000-4000-8000-000000000000", id="unknown-provider"),
        pytest.param(None, id="missing-provider"),
    ],
)
def test_create_source_with_bad_provider_does_not_error_in_permission_layer(
        api_client, org_admin_user, organization, provider_lotek_panthera, provider_id
):
    # The org resolver reads `provider` straight off the request body. Before GUNDI-5178 it
    # passed the raw value to Integration.objects.get(), which raised out of the permission
    # layer as a 500 for anything missing, malformed or unknown. Unreachable while the
    # viewset was read-only; reachable now.
    response = _post_source(api_client, org_admin_user, provider_id)
    assert response.status_code == status.HTTP_403_FORBIDDEN, response.content


def test_create_source_with_unknown_provider_as_superuser_is_a_validation_error(
        api_client, superuser, organization, provider_lotek_panthera
):
    # Superusers short-circuit the org resolver, so they reach the serializer and get the
    # field-level error rather than the 403 a scoped user sees.
    response = _post_source(
        api_client, superuser, "6b8f3c1e-0000-4000-8000-000000000000"
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST, response.content
    assert "provider" in response.json()
