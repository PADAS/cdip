import pytest
from django.urls import reverse
from rest_framework import status


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


def test_list_sources_as_superuser(
        api_client, superuser, organization, provider_lotek_panthera, provider_movebank_ewt,
        integrations_list, lotek_sources, movebank_sources, routing_rule_1, routing_rule_2,

):
    _test_list_sources(
        api_client=api_client,
        user=superuser,
        # The superuser can see all the sources
        expected_sources=lotek_sources+movebank_sources
    )


def test_list_sources_as_org_admin(
        api_client, org_admin_user, organization, provider_lotek_panthera, provider_movebank_ewt,
        integrations_list, lotek_sources, movebank_sources, routing_rule_1, routing_rule_2
):
    _test_list_sources(
        api_client=api_client,
        user=org_admin_user,  # Belongs to one organization
        # Org admins can only see sources of their organizations
        expected_sources=lotek_sources
    )


def test_list_sources_as_org_admin_2(
        api_client, org_admin_user_2, organization, provider_lotek_panthera, provider_movebank_ewt,
        integrations_list, lotek_sources, movebank_sources, routing_rule_1, routing_rule_2
):
    _test_list_sources(
        api_client=api_client,
        user=org_admin_user_2,  # Belongs to one organization
        # Org admins can only see sources of their organizations
        expected_sources=movebank_sources
    )


def test_list_sources_as_org_viewer(
        api_client, org_viewer_user, organization, provider_lotek_panthera, provider_movebank_ewt,
        integrations_list, lotek_sources, movebank_sources, routing_rule_1, routing_rule_2
):
    _test_list_sources(
        api_client=api_client,
        user=org_viewer_user,  # Belongs to one organization
        # Org viewer can only see sources of their organizations
        expected_sources=lotek_sources
    )


def test_filter_sources_by_external_id_as_superuser(
        api_client, superuser, organization, provider_lotek_panthera, provider_movebank_ewt,
        integrations_list, lotek_sources, movebank_sources, routing_rule_1, routing_rule_2
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
        integrations_list, lotek_sources, movebank_sources, routing_rule_1, routing_rule_2
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
        integrations_list, lotek_sources, movebank_sources, routing_rule_1, routing_rule_2
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
        integrations_list, lotek_sources, movebank_sources, routing_rule_1, routing_rule_2
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
        integrations_list, lotek_sources, movebank_sources, routing_rule_1, routing_rule_2
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
        integrations_list, lotek_sources, movebank_sources, routing_rule_1, routing_rule_2
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
        integrations_list, lotek_sources, movebank_sources, routing_rule_1, routing_rule_2, integration_type_er
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
        integrations_list, lotek_sources, movebank_sources, routing_rule_1, routing_rule_2, integration_type_er
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
        integrations_list, lotek_sources, movebank_sources, routing_rule_1, routing_rule_2, integration_type_er
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
        integrations_list, lotek_sources, movebank_sources, routing_rule_1, routing_rule_2, integration_type_er
):
    selected_destinations = integrations_list[:5]  # All the sources are connected to the first 5
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
        integrations_list, lotek_sources, movebank_sources, routing_rule_1, routing_rule_2, integration_type_er
):
    selected_destinations = integrations_list  # All the destinations
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
        integrations_list, lotek_sources, movebank_sources, routing_rule_1, routing_rule_2, integration_type_er
):
    selected_destinations = integrations_list  # All the destinations
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
        integrations_list, lotek_sources, movebank_sources, routing_rule_1, routing_rule_2, integration_type_er
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
        integrations_list, lotek_sources, movebank_sources, routing_rule_1, routing_rule_2, integration_type_er
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
        integrations_list, lotek_sources, movebank_sources, routing_rule_1, routing_rule_2, integration_type_er
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
        integrations_list, lotek_sources, movebank_sources, routing_rule_1, routing_rule_2, integration_type_er
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
        integrations_list, lotek_sources, movebank_sources, routing_rule_1, routing_rule_2, integration_type_er
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
        integrations_list, lotek_sources, movebank_sources, routing_rule_1, routing_rule_2, integration_type_er
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
        integrations_list, lotek_sources, movebank_sources, provider_movebank_ewt, provider_lotek_panthera,
        routing_rule_1, routing_rule_2
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
        integrations_list, lotek_sources, movebank_sources, provider_movebank_ewt, provider_lotek_panthera,
        routing_rule_1, routing_rule_2
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
        integrations_list, lotek_sources, movebank_sources, provider_movebank_ewt, provider_lotek_panthera,
        routing_rule_1, routing_rule_2
):
    _test_list_sources(
        api_client=api_client,
        user=org_viewer_user_2,
        filters={
            "search": "movebank",  # Looking sources getting data from movebank
        },
        expected_sources=movebank_sources
    )
