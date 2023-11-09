import pytest
from django.urls import reverse
from rest_framework import status

from activity_log.core import ActivityActions
from activity_log.models import ActivityLog
from integrations.models import (
    Integration,
    IntegrationAction,
    IntegrationConfiguration,
)


pytestmark = pytest.mark.django_db


def _test_list_integrations(api_client, user, organization):
    api_client.force_authenticate(user)
    response = api_client.get(
        reverse("integrations-list"),
    )
    assert response.status_code == status.HTTP_200_OK
    response_data = response.json()
    integrations = response_data["results"]
    if user.is_superuser:
        # The superuser can see all the integrations
        integrations_qs = Integration.objects.all()
    else: # Only see integrations owned by the organization(s) where the user is a member
        integrations_qs = Integration.objects.filter(owner=organization)
    expected_integrations_ids = [str(uid) for uid in integrations_qs.values_list("id", flat=True)]
    assert len(integrations) == len(expected_integrations_ids)
    for integration in integrations:
        assert integration.get("id") in expected_integrations_ids
        assert "name" in integration
        assert "base_url" in integration
        assert "enabled" in integration
        assert "type" in integration
        owner = integration.get("owner")
        assert owner
        assert "id" in owner
        assert "name" in owner
        assert "description" in owner
        # Check the action configurations
        assert "configurations" in integration
        configurations = integration.get("configurations")
        for configuration in configurations:
            assert "integration" in configuration
            assert "action" in configuration
            assert "data" in configuration


def test_list_integrations_as_superuser(api_client, superuser, organization, integrations_list):
    _test_list_integrations(
        api_client=api_client,
        user=superuser,
        organization=organization
    )


def test_list_integrations_as_org_admin(api_client, org_admin_user, organization, integrations_list):
    _test_list_integrations(
        api_client=api_client,
        user=org_admin_user,
        organization=organization
    )


def test_list_integrations_as_org_viewer(api_client, org_viewer_user, organization, integrations_list):
    _test_list_integrations(
        api_client=api_client,
        user=org_viewer_user,
        organization=organization
    )


def _test_activity_logs_on_instance_created(activity_log, instance, user):
    model = str(instance._meta.model.__name__)
    details = activity_log.details
    assert activity_log
    assert activity_log.log_type == ActivityLog.LogTypes.DATA_CHANGE
    assert activity_log.log_level == ActivityLog.LogLevels.INFO
    assert activity_log.origin == ActivityLog.Origin.PORTAL
    assert activity_log.title == f"{model} {ActivityActions.CREATED.value} by {user}"
    assert details.get("model_name") == model
    assert details.get("instance_pk") == str(instance.pk)
    assert details.get("action") == ActivityActions.CREATED.value
    assert activity_log.is_reversible
    assert activity_log.revert_data == {
        "model_name": model,
        "instance_pk": str(instance.pk)
    }


def _test_activity_logs_on_instance_updated(activity_log, instance, user, expected_changes, expected_revert_data):
    model = str(instance._meta.model.__name__)
    details = activity_log.details
    assert activity_log
    assert activity_log.log_type == ActivityLog.LogTypes.DATA_CHANGE
    assert activity_log.log_level == ActivityLog.LogLevels.INFO
    assert activity_log.origin == ActivityLog.Origin.PORTAL
    assert activity_log.title == f"{model} {ActivityActions.UPDATED.value} by {user}"
    assert details.get("model_name") == model
    assert details.get("instance_pk") == str(instance.pk)
    assert details.get("action") == ActivityActions.UPDATED.value
    assert "changes" in details
    assert activity_log.is_reversible
    changes = details.get("changes")
    for field, value in expected_changes.items():
        assert changes.get(field) == value
    revert_data = activity_log.revert_data
    for field, value in expected_revert_data.items():
        assert revert_data.get(field) == value


def _test_create_integration(
        api_client, user, owner, integration_type, base_url, name, configurations, create_default_route=True
):
    request_data = {
      "name": name,
      "type": str(integration_type.id),
      "owner": str(owner.id),
      "base_url": base_url,
      "configurations": configurations,
      "create_default_route": create_default_route
    }
    api_client.force_authenticate(user)
    response = api_client.post(
        reverse("integrations-list"),
        data=request_data,
        format='json'
    )
    assert response.status_code == status.HTTP_201_CREATED
    response_data = response.json()
    assert "id" in response_data
    # Check that the integration was created in the database
    integration = Integration.objects.get(id=response_data["id"])
    # Check that the operations were recorded in the activity log
    activity_log = ActivityLog.objects.filter(integration_id=integration.id, value="integration_created").first()
    _test_activity_logs_on_instance_created(
        activity_log=activity_log,
        instance=integration,
        user=user
    )

    # Check that the related configurations where created too
    total_configurations = integration.configurations.count()
    assert total_configurations == len(configurations)
    activity_logs = ActivityLog.objects.filter(integration_id=integration.id, value="integrationconfiguration_created").all()
    assert activity_logs.count() == total_configurations
    sorted_configurations = integration.configurations.order_by("-created_at")
    # Check activity logs for each configuration
    for i, configuration in enumerate(sorted_configurations):
        activity_log = activity_logs[i]
        _test_activity_logs_on_instance_created(
            activity_log=activity_log,
            instance=configuration,
            user=user
        )

    # Check that a default routing rule is created
    if create_default_route:
        assert integration.default_route
        activity_log = ActivityLog.objects.filter(integration_id=integration.id, value="integration_updated").first()
        _test_activity_logs_on_instance_updated(
            activity_log=activity_log,
            instance=integration,
            user=user,
            expected_changes={
                "default_route_id": str(integration.default_route.id),
            },
            expected_revert_data={
                "instance_pk": str(integration.pk),
                "model_name": "Integration",
                "original_values": {
                    "default_route_id": None
                }
            }
        )
    else:
        assert integration.default_route is None


def test_create_er_integration_as_superuser(
        api_client, superuser, organization, integration_type_er, get_random_id, er_action_auth,
        er_action_push_events, er_action_push_positions, er_action_pull_events, er_action_pull_positions
):
    _test_create_integration(
        api_client=api_client,
        user=superuser,
        owner=organization,
        integration_type=integration_type_er,
        base_url="https://reservex.pamdas.org",
        name=f"Reserve X {get_random_id()}",
        configurations=[
            {
                "action": str(er_action_auth.id),
                "data": {
                    "username": "reservex@pamdas.org",
                    "password": "P4sSW0rD"
                }
            },
            {
                "action": str(er_action_push_positions.id),
                "data": {
                    "sensor_type": "tracker"
                }
            }
            # Other actions in this example don't require extra settings
        ]
    )


def test_create_er_integration_as_org_admin(
        api_client, org_admin_user, organization, integration_type_er, get_random_id, er_action_auth,
        er_action_push_events, er_action_push_positions, er_action_pull_events, er_action_pull_positions
):
    _test_create_integration(
        api_client=api_client,
        user=org_admin_user,
        owner=organization,
        integration_type=integration_type_er,
        base_url="https://reservey.pamdas.org",
        name=f"Reserve Y {get_random_id()}",
        configurations=[
            {
                "action": str(er_action_auth.id),
                "data": {
                    "username": "reservey@pamdas.org",
                    "password": "P4sSW0rD"
                }
            },
            {
                "action": str(er_action_push_positions.id),
                "data": {
                    "sensor_type": "tracker"
                }
            }
            # Other actions in this example don't require extra settings
        ]
    )


def test_create_er_integration_without_default_route_as_org_admin(
        api_client, org_admin_user, organization, integration_type_er, get_random_id, er_action_auth,
        er_action_push_events, er_action_push_positions, er_action_pull_events, er_action_pull_positions
):
    _test_create_integration(
        api_client=api_client,
        user=org_admin_user,
        owner=organization,
        integration_type=integration_type_er,
        base_url="https://reservedest.pamdas.org",
        name=f"Reserve Dest {get_random_id()}",
        configurations=[
            {
                "action": str(er_action_auth.id),
                "data": {
                    "username": "reservedest@pamdas.org",
                    "password": "P4sSW0rD"
                }
            },
            {
                "action": str(er_action_push_positions.id),
                "data": {
                    "sensor_type": "tracker"
                }
            }
            # Other actions in this example don't require extra settings
        ],
        create_default_route=False  # Destination only integration
    )


def _test_cannot_create_integration(api_client, user, owner, integration_type, base_url, name, configurations):
    request_data = {
      "name": name,
      "type": str(integration_type.id),
      "owner": str(owner.id),
      "base_url": base_url,
      "configurations": configurations
    }
    api_client.force_authenticate(user)
    response = api_client.post(
        reverse("integrations-list"),
        data=request_data,
        format='json'
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_cannot_create_integrations_as_org_viewer(api_client, org_viewer_user, organization, integration_type_er, get_random_id):
    _test_cannot_create_integration(
        api_client=api_client,
        user=org_viewer_user,
        owner=organization,
        integration_type=integration_type_er,
        base_url="https://reservez.pamdas.org",
        name=f"Reserve Z {get_random_id()}",
        configurations=[]
    )


def _test_cannot_create_integration_with_invalid_params(api_client, user, owner, integration_type, base_url, name, configurations):
    request_data = {
      "name": name,
      "type": str(integration_type.id),
      "owner": str(owner.id),
      "base_url": base_url,
      "configurations": configurations
    }
    api_client.force_authenticate(user)
    response = api_client.post(
        reverse("integrations-list"),
        data=request_data,
        format='json'
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_cannot_create_integrations_with_invalid_config_as_org_admin(
        api_client, org_admin_user, organization, integration_type_er, get_random_id, er_action_auth,
        er_action_push_events, er_action_push_positions, er_action_pull_events, er_action_pull_positions
):
    _test_cannot_create_integration_with_invalid_params(
        api_client=api_client,
        user=org_admin_user,
        owner=organization,
        integration_type=integration_type_er,
        base_url="https://reservei.pamdas.org",
        name=f"Reserve Invalid {get_random_id()}",
        configurations=[
            {
                "action": str(er_action_auth.id),
                "data": {
                    "username": "reservey@pamdas.org",
                    # "password": "P4sSW0rD"  #  Password left out intentionally for this test
                }
            },
            {
                "action": str(er_action_push_positions.id),
                # Action data left out intentionally for this test
                # "data": {
                #     "sensor_type": "tracker"
                # }
            }
            # Other actions in this example don't require extra settings
        ]
    )


def test_cannot_create_integrations_with_invalid_url_as_org_admin(
        api_client, org_admin_user, organization, integration_type_er, get_random_id, er_action_auth,
        er_action_push_events, er_action_push_positions, er_action_pull_events, er_action_pull_positions
):
    _test_cannot_create_integration_with_invalid_params(
        api_client=api_client,
        user=org_admin_user,
        owner=organization,
        integration_type=integration_type_er,
        base_url="notaurl",
        name=f"Reserve Invalid {get_random_id()}",
        configurations=[
            {
                "action": str(er_action_auth.id),
                "data": {
                    "username": "reservey@pamdas.org",
                    "password": "P4sSW0rD"  #  Password left out intentionally for this test
                }
            },
            {
                "action": str(er_action_push_positions.id),
                "data": {
                    "sensor_type": "tracker"
                }
            }
            # Other actions in this example don't require extra settings
        ]
    )
# ToDo: Add more tests for configuration schema validations


def _test_filter_integrations(api_client, user, filters, expected_integrations):
    api_client.force_authenticate(user)
    response = api_client.get(
        reverse("integrations-list"),
        data=filters
    )
    assert response.status_code == status.HTTP_200_OK
    response_data = response.json()
    integrations = response_data["results"]
    # Check that the returned integrations are the expected ones
    expected_integrations_ids = [str(i.id) for i in expected_integrations]
    assert len(integrations) == len(expected_integrations_ids)
    for dest in integrations:
        assert dest.get("id") in expected_integrations_ids


def test_filter_integrations_exact_as_superuser(api_client, superuser, organization, integrations_list):
    destination = integrations_list[0]
    _test_filter_integrations(
        api_client=api_client,
        user=superuser,
        filters={
            "owner": str(destination.owner.id),
            "enabled": True,
            "type": str(destination.type.id),
            "base_url": str(destination.base_url)
        },
        expected_integrations=list(
            Integration.objects.filter(
                owner=destination.owner,
                enabled=True,
                type=destination.type,
                base_url=destination.base_url
            )
        )
    )


def test_filter_integrations_iexact_as_superuser(api_client, superuser, organization, integrations_list):
    destination = integrations_list[0]
    _test_filter_integrations(
        api_client=api_client,
        user=superuser,
        filters={
            "base_url__iexact": str(destination.base_url).capitalize()
        },
        expected_integrations=list(
            Integration.objects.filter(
                owner=destination.owner,
                enabled=True,
                type=destination.type,
                base_url=destination.base_url
            )
        )
    )


def test_filter_integrations_exact_as_org_admin(api_client, org_admin_user, organization, integrations_list):
    _test_filter_integrations(
        api_client=api_client,
        user=org_admin_user,
        filters={
            "owner": str(organization.id),
            "enabled": True
        },
        expected_integrations=list(
            Integration.objects.filter(
                owner=organization,
                enabled=True
            )
        )
    )


def test_filter_integrations_exact_as_org_viewer(api_client, org_viewer_user, organization, integration_type_er, integrations_list):
    # Viewer belongs to organization which owns the first 5 integrations of type EarthRanger
    _test_filter_integrations(
        api_client=api_client,
        user=org_viewer_user,
        filters={
            "owner": str(organization.id),
            "type": str(integration_type_er.id)
        },
        expected_integrations=list(
            Integration.objects.filter(
                owner=organization,
                type=integration_type_er
            )
        )
    )


def test_filter_integrations_multiselect_as_superuser(api_client, superuser, organization, other_organization, integrations_list):
    # Superuser can see integrations owned by any organizations
    owners = [organization, other_organization]
    base_urls = [d.base_url for d in integrations_list[1::2]]
    _test_filter_integrations(
        api_client=api_client,
        user=superuser,
        filters={  # Multiple owners and Multiple base_urls allowed
            "owner__in": ",".join([str(o.id) for o in owners]),
            "base_url__in": ",".join(base_urls)
        },
        expected_integrations=list(
            Integration.objects.filter(
                owner__in=owners,
                base_url__in=base_urls
            )
        )
    )


def test_filter_integrations_multiselect_as_org_admin(api_client, org_admin_user, organization, other_organization, integrations_list):
    # Org Admins can see integrations owned by the organizations they belong to
    # This org admin belongs to "organization" owning the first 5 integrations of "integrations_list"
    owners = org_admin_user.accountprofile.organizations.all()
    base_urls = [d.base_url for d in integrations_list[:3]]  # Select three out of five possible base_urls
    _test_filter_integrations(
        api_client=api_client,
        user=org_admin_user,
        filters={  # Multiple owners and Multiple base_urls allowed
            "owner__in": ",".join([str(o.id) for o in owners]),
            "base_url__in": ",".join(base_urls)
        },
        expected_integrations=list(
            Integration.objects.filter(
                owner__in=owners,
                base_url__in=base_urls
            )
        )
    )


def test_filter_integrations_multiselect_as_org_viewer(api_client, org_viewer_user, organization, other_organization, integrations_list):
    # Org Viewer can see integrations owned by the organizations they belong to
    # This org viewer belongs to "organization" owning the first 5 integrations of "integrations_list"
    owners = org_viewer_user.accountprofile.organizations.all()
    base_urls = [d.base_url for d in integrations_list[:2]]  # Select two out of five possible base_urls
    _test_filter_integrations(
        api_client=api_client,
        user=org_viewer_user,
        filters={  # Multiple owners and Multiple base_urls allowed
            "owner__in": ",".join([str(o.id) for o in owners]),
            "base_url__in": ",".join(base_urls)
        },
        expected_integrations=list(
            Integration.objects.filter(
                owner__in=owners,
                base_url__in=base_urls
            )
        )
    )


def test_filter_integrations_by_action_type_as_superuser(api_client, superuser, organization, other_organization, integrations_list):
    _test_filter_integrations(
        api_client=api_client,
        user=superuser,
        filters={  # Integrations which can be used as destination
            "action_type": IntegrationAction.ActionTypes.PUSH_DATA.value
        },
        expected_integrations=list(
            Integration.objects.filter(  # Superuser can see all the integrations
                type__actions__type=IntegrationAction.ActionTypes.PUSH_DATA.value
            ).distinct()
        )  # Ensure there are no duplicates
    )


def test_filter_integrations_by_action_type_as_org_admin(api_client, org_admin_user, organization, other_organization, integrations_list):
    # Org Admins can see integrations owned by the organizations they belong to
    # This org admin belongs to "organization" owning the first 5 integrations of "integrations_list"
    _test_filter_integrations(
        api_client=api_client,
        user=org_admin_user,
        filters={  # Integrations which can be used as data provider
            "action_type": IntegrationAction.ActionTypes.PULL_DATA.value
        },
        expected_integrations=integrations_list[:5]
    )


def test_filter_integrations_by_action_type_as_org_viewer(api_client, org_viewer_user, organization, other_organization, integrations_list):
    # Org Viewer can see integrations owned by the organizations they belong to
    # This org viewer belongs to "organization" owning the first 5 integrations of "integrations_list"
    owners = org_viewer_user.accountprofile.organizations.all()
    _test_filter_integrations(
        api_client=api_client,
        user=org_viewer_user,
        filters={  # Integrations which can be used as data provider
            "action_type": IntegrationAction.ActionTypes.AUTHENTICATION.value
        },
        expected_integrations=list(
            Integration.objects.filter(
                owner__in=owners,
                type__actions__type=IntegrationAction.ActionTypes.AUTHENTICATION.value
            ).distinct()
        )
    )


def _test_filter_integration_types(api_client, user, filters, expected_integration_types):
    api_client.force_authenticate(user)
    response = api_client.get(
        reverse("integration-types-list"),
        data=filters
    )
    assert response.status_code == status.HTTP_200_OK
    response_data = response.json()
    integration_types = response_data["results"]
    # Check that the returned integrations are the expected ones
    expected_type_ids = [str(t.id) for t in expected_integration_types]
    assert len(integration_types) == len(expected_type_ids)
    for type in integration_types:
        assert type.get("id") in expected_type_ids
        assert "name" in type
        assert "value" in type
        assert "description" in type
        assert "actions" in type


def test_filter_integrations_types_by_action_type_as_superuser(
        api_client, superuser, organization, other_organization,
        integration_type_er, integration_type_movebank, integration_type_lotek,
        integration_type_smart, smart_action_auth, smart_action_push_events,
        integrations_list, provider_movebank_ewt, provider_lotek_panthera
):
    _test_filter_integration_types(
        api_client=api_client,
        user=superuser,
        filters={  # Integrations which can be used as destination
            "action_type": IntegrationAction.ActionTypes.PUSH_DATA.value
        },
        expected_integration_types=[integration_type_er, integration_type_smart]
    )


def test_filter_integrations_types_by_action_type_as_org_admin(
        api_client, org_admin_user, organization, other_organization,
        integration_type_er, integration_type_movebank, integration_type_lotek,
        integration_type_smart, smart_action_auth, smart_action_push_events,
        integrations_list, provider_movebank_ewt, provider_lotek_panthera
):
    _test_filter_integration_types(
        api_client=api_client,
        user=org_admin_user,
        filters={  # Integrations supporting the authentication action
            "action_type": IntegrationAction.ActionTypes.AUTHENTICATION.value
        },
        expected_integration_types=[
            integration_type_er, integration_type_movebank, integration_type_lotek, integration_type_smart
        ]
    )


def test_filter_integrations_types_type_as_org_viewer(
        api_client, org_viewer_user, organization, other_organization,
        integration_type_er, integration_type_movebank, integration_type_lotek,
        integration_type_smart, smart_action_auth, smart_action_push_events,
        integrations_list, provider_movebank_ewt, provider_lotek_panthera
):
    _test_filter_integration_types(
        api_client=api_client,
        user=org_viewer_user,
        filters={  # Integrations which can be used as data provider
            "action_type": IntegrationAction.ActionTypes.PULL_DATA.value
        },
        expected_integration_types=[integration_type_er, integration_type_movebank, integration_type_lotek]
    )


def test_filter_integrations_types_by_action_type_and_in_use_as_superuser(
        api_client, superuser, organization, other_organization,
        integration_type_er, integration_type_movebank, integration_type_lotek,
        integration_type_smart, smart_action_auth, smart_action_push_events,
        integrations_list, provider_movebank_ewt, provider_lotek_panthera
):
    _test_filter_integration_types(
        api_client=api_client,
        user=superuser,
        filters={  # Types in use in destinations
            "action_type": IntegrationAction.ActionTypes.PUSH_DATA.value,
            "in_use_only": True  # Get Only types in use in integrations that the user can see
        },
        expected_integration_types=[integration_type_er]
    )


def test_filter_integrations_types_by_action_type_and_in_use_as_org_admin(
        api_client, org_admin_user_2, organization, other_organization,
        integration_type_er, integration_type_movebank, integration_type_lotek,
        integration_type_smart, smart_action_auth, smart_action_push_events,
        integrations_list, provider_movebank_ewt, provider_lotek_panthera
):
    _test_filter_integration_types(
        api_client=api_client,
        user=org_admin_user_2,
        filters={  # Integrations in use supporting the authentication action
            "action_type": IntegrationAction.ActionTypes.AUTHENTICATION.value,
            "in_use_only": True  # Get Only types in use in integrations that the user can see
        },
        expected_integration_types=[integration_type_er, integration_type_movebank]
    )


def test_filter_integrations_types_type_and_in_use_as_org_viewer(
        api_client, org_viewer_user, organization, other_organization,
        integration_type_er, integration_type_movebank, integration_type_lotek,
        integration_type_smart, smart_action_auth, smart_action_push_events,
        integrations_list, provider_movebank_ewt, provider_lotek_panthera
):
    _test_filter_integration_types(
        api_client=api_client,
        user=org_viewer_user,
        filters={  # Types in use in destinations
            "action_type": IntegrationAction.ActionTypes.PUSH_DATA.value,
            "in_use_only": True  # Get Only types in use in integrations that the user can see
        },
        expected_integration_types=[integration_type_er]
    )


def test_filter_integrations_types_by_search_term_as_superuser(
        api_client, superuser, organization, other_organization,
        integration_type_er, integration_type_movebank, integration_type_lotek,
        integration_type_smart, smart_action_auth, smart_action_push_events,
        integrations_list, provider_movebank_ewt, provider_lotek_panthera
):
    _test_filter_integration_types(
        api_client=api_client,
        user=superuser,
        filters={
            "search": "smar",
            "search_fields": "value"  # partial match in the value field
        },
        expected_integration_types=[integration_type_smart]
    )


def test_filter_integrations_types_by_search_term_as_org_admin(
        api_client, org_admin_user, organization, other_organization,
        integration_type_er, integration_type_movebank, integration_type_lotek,
        integration_type_smart, smart_action_auth, smart_action_push_events,
        integrations_list, provider_movebank_ewt, provider_lotek_panthera
):
    _test_filter_integration_types(
        api_client=api_client,
        user=org_admin_user,
        filters={
            "search": "earth",
            "search_fields": "^value"  # value starts with "earth"
        },
        expected_integration_types=[integration_type_er]
    )


def test_filter_integrations_types_by_search_term_as_org_viewer(
        api_client, org_viewer_user_2, organization, other_organization,
        integration_type_er, integration_type_movebank, integration_type_lotek,
        integration_type_smart, smart_action_auth, smart_action_push_events,
        integrations_list, provider_movebank_ewt, provider_lotek_panthera
):
    _test_filter_integration_types(
        api_client=api_client,
        user=org_viewer_user_2,
        filters={
            "search": "bank",
            "search_fields": "name"  # partial match in the name field
        },
        expected_integration_types=[integration_type_movebank]
    )


def _test_filter_integration_urls(api_client, user, search_term, search_fields, extra_filters, expected_integrations):
    api_client.force_authenticate(user)
    response = api_client.get(
        f"{reverse('integrations-list')}urls/",
        data={
            "search": search_term,
            "search_fields": search_fields,
            **extra_filters
        }
    )
    assert response.status_code == status.HTTP_200_OK
    response_data = response.json()
    integrations = response_data["results"]
    # Check that the returned integrations are the expected ones
    expected_integrations_ids = [str(i.id) for i in expected_integrations]
    assert len(integrations) == len(expected_integrations_ids)
    for integration in integrations:
        assert integration.get("id") in expected_integrations_ids
        assert "base_url" in integration
        assert search_term in integration["base_url"]


def test_filter_integrations_urls_by_search_term_as_superuser(
        api_client, superuser, organization, other_organization,
        integration_type_er, integration_type_movebank, integration_type_lotek,
        integration_type_smart, smart_action_auth, smart_action_push_events,
        integrations_list, provider_movebank_ewt, provider_lotek_panthera,
):
    _test_filter_integration_urls(
        api_client=api_client,
        user=superuser,
        search_term="mov",
        search_fields="base_url",
        extra_filters={
            "action_type": "pull"
        },
        expected_integrations=[provider_movebank_ewt]
    )


def test_filter_integrations_urls_by_search_term_as_org_admin(
        api_client, org_admin_user, organization, other_organization,
        integration_type_er, integration_type_movebank, integration_type_lotek,
        integration_type_smart, smart_action_auth, smart_action_push_events,
        integrations_list, provider_movebank_ewt, provider_lotek_panthera,
):
    _test_filter_integration_urls(
        api_client=api_client,
        user=org_admin_user,
        search_term="pamdas",  # ER Sites
        search_fields="base_url",
        extra_filters={
            "action_type": "push"  # Integrations used as destinations
        },
        expected_integrations=integrations_list[:5]  # First 5 ER integrations are owned by organization
    )


def test_filter_integrations_urls_by_search_term_as_org_viewer(
        api_client, org_viewer_user, organization, other_organization,
        integration_type_er, integration_type_movebank, integration_type_lotek,
        integration_type_smart, smart_action_auth, smart_action_push_events,
        integrations_list, provider_movebank_ewt, provider_lotek_panthera,
):
    _test_filter_integration_urls(
        api_client=api_client,
        user=org_viewer_user,
        search_term="lot",  # Lotek
        search_fields="base_url",
        extra_filters={
            "action_type": "pull"  # Integrations used as providers
        },
        expected_integrations=[provider_lotek_panthera]
    )


def _test_filter_integration_owners(api_client, user, search_term, search_fields, extra_filters, expected_owners):
    api_client.force_authenticate(user)
    response = api_client.get(
        f"{reverse('integrations-list')}owners/",
        data={
            "search": search_term,
            "search_fields": search_fields,
            **extra_filters
        }
    )
    assert response.status_code == status.HTTP_200_OK
    response_data = response.json()
    owners = response_data["results"]
    # Check that the returned integrations are the expected ones
    expected_owners_ids = [str(i.id) for i in expected_owners]
    assert len(owners) == len(expected_owners_ids)
    for owner in owners:
        assert owner.get("id") in expected_owners_ids
        assert "name" in owner
        assert search_term.lower() in owner["name"].lower()


def test_filter_integrations_owner_by_search_term_as_superuser(
        api_client, superuser, organization, other_organization,
        integration_type_er, integration_type_movebank, integration_type_lotek,
        integration_type_smart, smart_action_auth, smart_action_push_events,
        integrations_list, provider_movebank_ewt, provider_lotek_panthera,
):
    _test_filter_integration_owners(
        api_client=api_client,
        user=superuser,
        search_term="tes",  # Test Organizations
        search_fields="owner__name",
        extra_filters={
            "action_type": "push"  # Destinations
        },
        expected_owners=[organization, other_organization]
    )


def test_filter_integrations_owner_by_search_term_as_org_admin(
        api_client, org_admin_user, organization, other_organization,
        integration_type_er, integration_type_movebank, integration_type_lotek,
        integration_type_smart, smart_action_auth, smart_action_push_events,
        integrations_list, provider_movebank_ewt, provider_lotek_panthera,
):
    _test_filter_integration_owners(
        api_client=api_client,
        user=org_admin_user,
        search_term="lew",  # Test Organization Lewa
        search_fields="owner__name",
        extra_filters={
            "action_type": "push"  # Destinations
        },
        expected_owners=[organization]
    )


def test_filter_integrations_owner_by_search_term_as_org_viewer(
        api_client, org_viewer_user_2, organization, other_organization,
        integration_type_er, integration_type_movebank, integration_type_lotek,
        integration_type_smart, smart_action_auth, smart_action_push_events,
        integrations_list, provider_movebank_ewt, provider_lotek_panthera,
):
    _test_filter_integration_owners(
        api_client=api_client,
        user=org_viewer_user_2,
        search_term="ew",  # Test Organization EWT
        search_fields="owner__name",
        extra_filters={
            "action_type": "push"  # Destinations
        },
        expected_owners=[other_organization]
    )


def _test_global_search_integrations(
        api_client, user, search_term, expected_integrations,  extra_filters=None, search_fields=None
):
    api_client.force_authenticate(user)
    query_params = {
        "search": search_term,
    }
    if search_fields:
        query_params["search_fields"] = search_fields
    if extra_filters:
        query_params.update(extra_filters)
    response = api_client.get(
        reverse('integrations-list'),
        data=query_params
    )
    assert response.status_code == status.HTTP_200_OK
    response_data = response.json()
    integrations = response_data["results"]
    # Check that the returned integrations are the expected ones
    expected_integrations_ids = [str(i.id) for i in expected_integrations]
    assert len(integrations) == len(expected_integrations_ids)
    for owner in integrations:
        assert owner.get("id") in expected_integrations_ids


def test_global_search_integrations_as_superuser(
        api_client, superuser, organization, other_organization,
        integration_type_er, integration_type_movebank, integration_type_lotek,
        integration_type_smart, smart_action_auth, smart_action_push_events,
        integrations_list, provider_movebank_ewt, provider_lotek_panthera,
):
    _test_global_search_integrations(
        api_client=api_client,
        user=superuser,
        search_term="pamdas.org",  # Looking for earth ranger integrations
        expected_integrations=integrations_list  # As superuser can see all the integrations
    )


def test_global_search_integrations_as_org_admin(
        api_client, org_admin_user_2, organization, other_organization,
        integration_type_er, integration_type_movebank, integration_type_lotek,
        integration_type_smart, smart_action_auth, smart_action_push_events,
        integrations_list, provider_movebank_ewt, provider_lotek_panthera,
):
    _test_global_search_integrations(
        api_client=api_client,
        user=org_admin_user_2,
        search_term="bank",  # Looking for Movebank integrations
        expected_integrations=[provider_movebank_ewt]
    )


def test_global_search_integrations_as_org_viewer(
        api_client, org_viewer_user, organization, other_organization,
        integration_type_er, integration_type_movebank, integration_type_lotek,
        integration_type_smart, smart_action_auth, smart_action_push_events,
        integrations_list, provider_movebank_ewt, provider_lotek_panthera,
):
    _test_global_search_integrations(
        api_client=api_client,
        user=org_viewer_user,
        search_term="pAnTHer",  # Looking for integration with Parthera
        expected_integrations=[provider_lotek_panthera]
    )


def test_global_search_integrations_combined_with_filters_as_superuser(
        api_client, superuser, organization, other_organization,
        integration_type_er, integration_type_movebank, integration_type_lotek,
        integration_type_smart, smart_action_auth, smart_action_push_events,
        integrations_list, provider_movebank_ewt, provider_lotek_panthera,
):
    _test_global_search_integrations(
        api_client=api_client,
        user=superuser,
        search_term="earth",  # Looking for earth ranger integrations
        search_fields="^type__name",
        extra_filters={
            "action_type": "push"  # Destinations
        },
        expected_integrations=integrations_list  # As superuser can see all the integrations
    )


def test_global_search_integrations_combined_with_filters_as_org_admin(
        api_client, org_admin_user_2, organization, other_organization,
        integration_type_er, integration_type_movebank, integration_type_lotek,
        integration_type_smart, smart_action_auth, smart_action_push_events,
        integrations_list, provider_movebank_ewt, provider_lotek_panthera,
):
    _test_global_search_integrations(
        api_client=api_client,
        user=org_admin_user_2,
        search_term="Bank",  # Looking for Movebank integrations
        search_fields="name",
        extra_filters={
            "action_type": "pull",  # Provider
            "owner__in": f"{organization.id},{other_organization.id}"  # Selected Owners
        },
        expected_integrations=[provider_movebank_ewt]
    )


def test_global_search_integrations_combined_with_filters_as_org_viewer(
        api_client, org_viewer_user, organization, other_organization,
        integration_type_er, integration_type_movebank, integration_type_lotek,
        integration_type_smart, smart_action_auth, smart_action_push_events,
        integrations_list, provider_movebank_ewt, provider_lotek_panthera,
):
    _test_global_search_integrations(
        api_client=api_client,
        user=org_viewer_user,
        search_term="lot",  # Looking for integration with Parthera
        search_fields="^type__value",
        extra_filters={
            "action_type": "pull",  # Provider
        },
        expected_integrations=[provider_lotek_panthera]
    )


def _test_update_integration_config(
        api_client, user, integration, new_configurations_data, original_configurations_data=None
):
    api_client.force_authenticate(user)
    response = api_client.patch(
        reverse("integrations-detail", kwargs={"pk": integration.id}),
        data={
          "configurations": new_configurations_data
        },
        format='json'
    )
    assert response.status_code == status.HTTP_200_OK
    integration.refresh_from_db()
    # Check the API response
    response_data = response.json()
    assert "configurations" in response_data
    for config_response in response_data["configurations"]:
        assert "id" in config_response
        assert "integration" in config_response
        assert "action" in config_response
        assert "data" in config_response
    # Compare the response with request data
    for config_request in new_configurations_data:
        if "id" in config_request:  # Updated
            config_response = next((c for c in response_data["configurations"] if c["id"] == config_request["id"]), None)
            assert config_response
            configuration = IntegrationConfiguration.objects.get(id=config_request["id"])
            # Check activity logs
            activity_log = ActivityLog.objects.get(
                integration=integration,
                details__action=ActivityActions.UPDATED.value,
                details__instance_pk=config_request["id"]
            )
            expected_revert_data = {
                "instance_pk": str(configuration.pk),
                "model_name": "IntegrationConfiguration"
            }
            if original_configurations_data:
                expected_revert_data["original_values"] = original_configurations_data[config_request["id"]]
            _test_activity_logs_on_instance_updated(
                activity_log=activity_log,
                instance=configuration,
                user=user,
                expected_changes={
                    "data": config_request["data"]
                },
                expected_revert_data=expected_revert_data
            )
        else:  # Created a new config
            configuration = IntegrationConfiguration.objects.get(
                integration=integration,
                action_id=config_request["action"],
                data=config_request["data"]
            )
            # Check activity logs
            activity_log = ActivityLog.objects.filter(
                integration=integration,
                details__action=ActivityActions.CREATED.value,
                details__model_name="IntegrationConfiguration"
            ).last()
            assert activity_log
            _test_activity_logs_on_instance_created(
                activity_log=activity_log,
                instance=configuration,
                user=user
            )
        # Check that the new config was saved in the db
        assert configuration.data == config_request["data"]
        # Check that the config cannot be reassigned to other integration
        assert configuration.integration == integration


def test_update_integration_config_as_org_admin(
        api_client, org_admin_user, organization, provider_lotek_panthera,
        lotek_action_auth, lotek_action_pull_positions,
):
    lotek_auth_config = lotek_action_auth.configurations_by_action.get(integration=provider_lotek_panthera)
    lotek_pull_positions_config = lotek_action_pull_positions.configurations_by_action.get(integration=provider_lotek_panthera)
    _test_update_integration_config(
        api_client=api_client,
        user=org_admin_user,
        integration=provider_lotek_panthera,
        new_configurations_data=[
            {
                "id": str(lotek_auth_config.id),
                "data": {
                    "username": "user@lotek.com",
                    "password": "NewP4sSW0rD"
                }
            },
            {
                "id": str(lotek_pull_positions_config.id),
                "integration": str(provider_lotek_panthera.id),  # Optional, ignored
                "action": str(lotek_action_pull_positions.id),  # Optional, ignored
                "data": {
                    "start_time": "2023-11-10T00:00:00Z"
                }
            }
        ],
        original_configurations_data={
            str(lotek_auth_config.id): {
                "data": lotek_auth_config.data
            },
            str(lotek_pull_positions_config.id): {
                "data": lotek_pull_positions_config.data
            }
        }
    )


def test_update_integration_config_as_superuser(
        api_client, superuser, organization, provider_lotek_panthera,
        lotek_action_auth, lotek_action_pull_positions,
):
    lotek_auth_config = lotek_action_auth.configurations_by_action.get(integration=provider_lotek_panthera)
    lotek_pull_positions_config = lotek_action_pull_positions.configurations_by_action.get(integration=provider_lotek_panthera)
    _test_update_integration_config(
        api_client=api_client,
        user=superuser,
        integration=provider_lotek_panthera,
        new_configurations_data=[
            {
                "id": str(lotek_auth_config.id),
                "data": {
                    "username": "user@lotek.com",
                    "password": "OtherP4sSW0rD"
                }
            },
            {
                "id": str(lotek_pull_positions_config.id),
                "integration": str(provider_lotek_panthera.id),  # Optional, ignored
                "action": str(lotek_action_pull_positions.id),  # Optional, ignored
                "data": {
                    "start_time": "2023-12-31T00:00:00Z"
                }
            }
        ]
    )


def test_update_or_create_integration_config_as_org_admin(
        api_client, org_admin_user, organization, provider_lotek_panthera,
        lotek_action_auth, lotek_action_pull_positions, lotek_action_list_devices
):
    lotek_auth_config = lotek_action_auth.configurations_by_action.get(integration=provider_lotek_panthera)
    _test_update_integration_config(
        api_client=api_client,
        user=org_admin_user,
        integration=provider_lotek_panthera,
        new_configurations_data=[
            {  # Config to be updated
                "id": str(lotek_auth_config.id),
                "data": {
                    "username": "user2@lotek.com",
                    "password": "OtherP4sSW0rD"
                }
            },
            {  # New Config
                "action": str(lotek_action_list_devices.id),  # Required for creation
                "data": {
                    "group_id": "1234"
                }
            }
        ]
    )


def _test_get_integration_api_key(
        api_client, user, integration
):
    api_client.force_authenticate(user)
    url = f'{reverse("integrations-detail", kwargs={"pk": integration.id})}api-key/'
    response = api_client.get(url)
    assert response.status_code == status.HTTP_200_OK
    # Check that a non-empty API Key is returned
    response_data = response.json()
    assert response_data.get("api_key")


def test_get_integration_api_key_as_org_admin(
        api_client, mocker, mock_get_api_key, org_admin_user, organization, provider_lotek_panthera
):
    mocker.patch("integrations.models.v2.Integration.api_key", mock_get_api_key)
    _test_get_integration_api_key(
        api_client=api_client,
        user=org_admin_user,
        integration=provider_lotek_panthera
    )
    assert mock_get_api_key.called


def test_get_integration_api_key_as_superuser(
        api_client, mocker, mock_get_api_key, superuser, organization, provider_lotek_panthera
):
    mocker.patch("integrations.models.v2.Integration.api_key", mock_get_api_key)
    _test_get_integration_api_key(
        api_client=api_client,
        user=superuser,
        integration=provider_lotek_panthera
    )
    assert mock_get_api_key.called
