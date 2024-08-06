import asyncio
import base64
from datetime import datetime
from unittest.mock import PropertyMock
import pytest
import random
from typing import NamedTuple, Any
from django.contrib.auth.models import User, Group
from rest_framework.utils import json
from rest_framework.test import APIClient
from accounts.models import AccountProfile, AccountProfileOrganization
from activity_log.models import ActivityLog
from core.enums import DjangoGroups, RoleChoices
from accounts.models import EULA, UserAgreement
from integrations.models import (
    InboundIntegrationType,
    OutboundIntegrationType,
    BridgeIntegrationType,
    InboundIntegrationConfiguration,
    OutboundIntegrationConfiguration,
    BridgeIntegration,
    DeviceGroup,
    Device,
    DeviceState,
    # New integration models below (Gundi 2.0)
    Integration,
    IntegrationType,
    IntegrationAction,
    IntegrationConfiguration,
    Route,
    SourceFilter,
    ListFilter,
    Source,
    SourceState,
    SourceConfiguration,
    ensure_default_route,
    RouteConfiguration,
    GundiTrace, IntegrationWebhook, WebhookConfiguration,
)
from organizations.models import Organization
from pathlib import Path
from gundi_core.events import (
    IntegrationWebhookStarted,
    WebhookExecutionStarted,
    IntegrationWebhookComplete,
    WebhookExecutionComplete,
    IntegrationWebhookFailed,
    WebhookExecutionFailed, IntegrationWebhookCustomLog, CustomWebhookLog, LogLevel
)


def async_return(result):
    f = asyncio.Future()
    f.set_result(result)
    return f


@pytest.fixture
def api_client():
    """
    Use this client to test API endpoints.
    It'll take care of dict-to-json serialization among other things.
    https://www.django-rest-framework.org/api-guide/testing/#apiclient
    """
    return APIClient()


@pytest.fixture
def superuser():
    email = "superuser@gundiservice.org"
    user, _ = User.objects.get_or_create(
        username=email,
        email=email,
        first_name="John",
        last_name="Doe",
        is_superuser=True,
    )
    return user


@pytest.fixture
def org_admin_user(organization, org_members_group):
    email = "orgadmin@gundiservice.org"
    user, _ = User.objects.get_or_create(
        username=email, email=email, first_name="Caroline", last_name="West"
    )
    user.groups.add(org_members_group.id)
    account_profile, _ = AccountProfile.objects.get_or_create(
        user_id=user.id,
    )
    AccountProfileOrganization.objects.get_or_create(
        accountprofile_id=account_profile.id,
        organization_id=organization.id,
        role=RoleChoices.ADMIN.value,
    )
    return user


@pytest.fixture
def org_admin_user_2(other_organization, org_members_group):
    email = "orgadmin2@gundiservice.org"
    user, _ = User.objects.get_or_create(
        username=email, email=email, first_name="Jack", last_name="Pearson"
    )
    user.groups.add(org_members_group.id)
    account_profile, _ = AccountProfile.objects.get_or_create(
        user_id=user.id,
    )
    AccountProfileOrganization.objects.get_or_create(
        accountprofile_id=account_profile.id,
        organization_id=other_organization.id,
        role=RoleChoices.ADMIN.value,
    )
    return user


@pytest.fixture
def org_viewer_user(organization, org_members_group):
    email = "orgviewer@gundiservice.org"
    user, _ = User.objects.get_or_create(
        username=email, email=email, first_name="Colin", last_name="Gray"
    )
    user.groups.add(org_members_group.id)
    account_profile, _ = AccountProfile.objects.get_or_create(
        user_id=user.id,
    )
    AccountProfileOrganization.objects.get_or_create(
        accountprofile_id=account_profile.id,
        organization_id=organization.id,
        role=RoleChoices.VIEWER.value,
    )
    return user


@pytest.fixture
def org_viewer_user_2(other_organization, org_members_group):
    email = "orgaviewer2@gundiservice.org"
    user, _ = User.objects.get_or_create(
        username=email, email=email, first_name="Phill", last_name="Wane"
    )
    user.groups.add(org_members_group.id)
    account_profile, _ = AccountProfile.objects.get_or_create(
        user_id=user.id,
    )
    AccountProfileOrganization.objects.get_or_create(
        accountprofile_id=account_profile.id,
        organization_id=other_organization.id,
        role=RoleChoices.VIEWER.value,
    )
    return user


@pytest.fixture
def new_random_user(new_user_email, org_members_group):
    def _make_random_user():
        email = new_user_email()
        user = User.objects.create(username=email, email=email)
        user.groups.add(org_members_group.id)
        AccountProfile.objects.create(
            user_id=user.id,
        )
        return user

    return _make_random_user


@pytest.fixture
def new_user_email(get_random_id):
    def _make_random_email():
        unique_id = get_random_id()
        while True:
            try:
                email = f"testuser-{unique_id}@gundiservice.org"
                User.objects.get(username=email)
            except User.DoesNotExist:
                return email
            else:  # Try a new email
                unique_id = get_random_id()

    return _make_random_email


@pytest.fixture
def organization(get_random_id):
    org, _ = Organization.objects.get_or_create(
        name=f"Test Organization Lewa {get_random_id()}",
        description="A reserve in Africa",
    )
    return org


@pytest.fixture
def other_organization(get_random_id):
    org, _ = Organization.objects.get_or_create(
        name=f"Test Organization EWT {get_random_id()}",
        description="A different reserve in Africa",
    )
    return org


@pytest.fixture
def members_apo_list(organization, new_random_user):
    members_apo_list = []
    for i in range(10):
        user = new_random_user()
        apo = AccountProfileOrganization.objects.create(
            accountprofile_id=user.accountprofile.id,
            organization_id=organization.id,
            role=RoleChoices.VIEWER.value,
        )
        members_apo_list.append(apo)
    return members_apo_list


@pytest.fixture
def organizations_list(get_random_id, organization):
    orgs = [organization]  # Organization having an admin and a viewer
    for i in range(10):
        org, _ = Organization.objects.get_or_create(
            name=f"Test Organization {get_random_id()}",
            description="A reserve in Africa",
        )
        orgs.append(org)
    return orgs


@pytest.fixture
def org_members_group():
    group, _ = Group.objects.get_or_create(name=DjangoGroups.ORGANIZATION_MEMBER.value)
    return group


@pytest.fixture
def mock_add_account(mocker):
    add_account = mocker.MagicMock()
    add_account.return_value = True
    return add_account


@pytest.fixture
def mock_send_invite_email_task(mocker):
    return mocker.MagicMock()


@pytest.fixture
def get_random_id():
    """
    A helper function that generates a ramdom alphanumeric id, to be used as external_id of Devices
    """

    def _make_device_id():
        return "".join(random.sample([chr(x) for x in range(97, 97 + 26)], 12))

    return _make_device_id


@pytest.fixture
def integration_type_lotek():
    return IntegrationType.objects.create(
        name="Lotek",
        value="lotek",
        description="Standard inbound integration type for pulling data from Lotek API.",
    )


@pytest.fixture
def lotek_action_auth(integration_type_lotek):
    return IntegrationAction.objects.create(
        integration_type=integration_type_lotek,
        type=IntegrationAction.ActionTypes.AUTHENTICATION,
        name="Authenticate",
        value="auth",
        description="Use credentials to authenticate against Lotek API",
        schema={
            "type": "object",
            "required": ["username", "password"],
            "properties": {
                "password": {"type": "string"},
                "username": {"type": "string"},
            },
        },
    )


@pytest.fixture
def lotek_action_pull_positions(integration_type_lotek):
    return IntegrationAction.objects.create(
        integration_type=integration_type_lotek,
        type=IntegrationAction.ActionTypes.PULL_DATA,
        is_periodic_action=True,
        name="Pull Positions",
        value="pull_positions",
        description="Pull Tracking data from Lotek API",
        schema={
            "type": "object",
            "required": ["start_time"],
            "properties": {"start_time": {"type": "string"}},
        },
    )


@pytest.fixture
def lotek_action_list_devices(integration_type_lotek):
    return IntegrationAction.objects.create(
        integration_type=integration_type_lotek,
        type=IntegrationAction.ActionTypes.GENERIC,
        name="List Devices",
        value="list_devices",
        description="Pull devices list from Lotek API",
        schema={
            "type": "object",
            "required": ["group_id"],
            "properties": {"group_id": {"type": "string"}},
        },
    )


@pytest.fixture
def integration_type_movebank():
    return IntegrationType.objects.create(
        name="Move Bank",
        value="movebank",
        description="Standard Integration type for Move Bank API.",
    )


@pytest.fixture
def mb_action_auth(integration_type_movebank):
    return IntegrationAction.objects.create(
        integration_type=integration_type_movebank,
        type=IntegrationAction.ActionTypes.AUTHENTICATION,
        name="Authenticate",
        value="auth",
        description="Use credentials to authenticate against Move Bank API",
        schema={
            "type": "object",
            "required": ["email", "password"],
            "properties": {"password": {"type": "string"}, "email": {"type": "string"}},
        },
    )


@pytest.fixture
def mb_action_pull_positions(integration_type_movebank):
    return IntegrationAction.objects.create(
        integration_type=integration_type_movebank,
        type=IntegrationAction.ActionTypes.PULL_DATA,
        name="Pull Positions",
        value="pull_positions",
        description="Pull Tracking data from Move Bank API",
        schema={
            "type": "object",
            "required": ["max_records_per_individual"],
            "properties": {"max_records_per_individual": {"type": "integer"}},
        },
    )


@pytest.fixture
def mb_action_permissions(integration_type_movebank):
    return IntegrationAction.objects.create(
        type=IntegrationAction.ActionTypes.AUTHENTICATION,
        name="Permissions",
        value="permissions",
        integration_type=integration_type_movebank,
    )


@pytest.fixture
def integration_type_er():
    # Create an integration type for Earth Ranger
    integration_type = IntegrationType.objects.create(
        name="EarthRanger",
        value="earth_ranger",
        description="Standard type for distributing data to EarthRanger sites.",
    )
    return integration_type


@pytest.fixture
def er_action_auth(integration_type_er):
    return IntegrationAction.objects.create(
        integration_type=integration_type_er,
        type=IntegrationAction.ActionTypes.AUTHENTICATION,
        name="Authenticate",
        value="auth",
        description="Use credentials to authenticate against Earth Ranger API",
        schema={
            "type": "object",
            "required": ["username", "password"],
            "properties": {
                "password": {"type": "string"},
                "username": {"type": "string"},
            },
        },
    )


@pytest.fixture
def er_action_push_positions(integration_type_er):
    return IntegrationAction.objects.create(
        integration_type=integration_type_er,
        type=IntegrationAction.ActionTypes.PUSH_DATA,
        name="Push Positions",
        value="push_positions",
        description="Push Tracking data to Earth Ranger API",
        schema={
            "type": "object",
            "required": ["sensor_type"],
            "properties": {"sensor_type": {"type": "string"}},
        },
    )


@pytest.fixture
def er_action_push_events(integration_type_er):
    return IntegrationAction.objects.create(
        integration_type=integration_type_er,
        type=IntegrationAction.ActionTypes.PUSH_DATA,
        name="Push Events",
        value="push_events",
        description="Push Event data to Earth Ranger API",
    )


@pytest.fixture
def er_action_pull_positions(integration_type_er):
    return IntegrationAction.objects.create(
        integration_type=integration_type_er,
        type=IntegrationAction.ActionTypes.PULL_DATA,
        name="Pull Positions",
        value="pull_positions",
        description="Pull Tracking data from Earth Ranger API",
    )


@pytest.fixture
def er_action_pull_events(integration_type_er):
    return IntegrationAction.objects.create(
        integration_type=integration_type_er,
        type=IntegrationAction.ActionTypes.PULL_DATA,
        name="Pull Events",
        value="pull_events",
        description="Pull Event data from Earth Ranger API",
    )


@pytest.fixture
def integration_type_smart():
    return IntegrationType.objects.create(
        name="SMART",
        value="smart_connect",
        description="Standard integration type for pushing data to SMART Cloud.",
    )


@pytest.fixture
def smart_action_push_events(integration_type_smart):
    return IntegrationAction.objects.create(
        integration_type=integration_type_smart,
        type=IntegrationAction.ActionTypes.PUSH_DATA,
        name="Push Events",
        value="push_events",
        description="Push Event data to SMART Cloud API",
    )


@pytest.fixture
def smart_action_auth(integration_type_smart):
    return IntegrationAction.objects.create(
        integration_type=integration_type_smart,
        type=IntegrationAction.ActionTypes.AUTHENTICATION,
        name="Authenticate",
        value="auth",
        description="API Key to authenticate against SMART API",
        schema={
            "type": "object",
            "required": ["api_key"],
            "properties": {"api_key": {"type": "string"}},
        },
    )


@pytest.fixture
def smart_integration(
        organization,
        other_organization,
        integration_type_smart,
        get_random_id,
        smart_action_auth,
        smart_action_push_events,
):
    # Create the integration
    site_url = f"{get_random_id()}.smart.wps.org"
    integration, _ = Integration.objects.get_or_create(
        type=integration_type_smart,
        name=f"SMART Site {get_random_id()}",
        owner=other_organization,
        base_url=site_url,
    )
    # Configure actions
    IntegrationConfiguration.objects.create(
        integration=integration,
        action=smart_action_auth,
        data={
            "api_key": f"SMART-{get_random_id()}-KEY",
        },
    )
    ensure_default_route(integration=integration)
    return integration


@pytest.fixture
def integration_type_wpswatch():
    # Create an integration type for Earth Ranger
    integration_type = IntegrationType.objects.create(
        name="WPS Watch",
        value="wps_watch",
        description="Standard type for distributing data to WPS Watch sites.",
    )
    return integration_type


@pytest.fixture
def wpswatch_action_push_events(integration_type_wpswatch):
    return IntegrationAction.objects.create(
        integration_type=integration_type_wpswatch,
        type=IntegrationAction.ActionTypes.PUSH_DATA,
        name="Push Events",
        value="push_events",
        description="Push Event data to WPA Watch API",
    )


@pytest.fixture
def provider_lotek_panthera(
        get_random_id,
        organization,
        integration_type_lotek,
        lotek_action_auth,
        lotek_action_pull_positions,
):
    provider, _ = Integration.objects.get_or_create(
        type=integration_type_lotek,
        name=f"Lotek Provider For Panthera {get_random_id()}",
        owner=organization,
        base_url=f"api.test.lotek.com",
    )
    # Configure actions
    IntegrationConfiguration.objects.create(
        integration=provider,
        action=lotek_action_auth,
        data={
            "username": f"user-{get_random_id()}@lotek.com",
            "password": f"passwd-{get_random_id()}",
        },
    )
    IntegrationConfiguration.objects.create(
        integration=provider,
        action=lotek_action_pull_positions,
        data={"start_time": "2023-01-01T00:00:00Z"},
    )
    ensure_default_route(integration=provider)
    return provider


@pytest.fixture
def provider_movebank_ewt(
        get_random_id,
        other_organization,
        integration_type_movebank,
        mb_action_auth,
        mb_action_pull_positions,
):
    provider, _ = Integration.objects.get_or_create(
        type=integration_type_movebank,
        name=f"Movebank Provider For EWT {get_random_id()}",
        owner=other_organization,
        base_url=f"https://api.test.movebank.com",
    )
    # Configure actions
    IntegrationConfiguration.objects.create(
        integration=provider,
        action=mb_action_auth,
        data={
            "email": f"user-{get_random_id()}@movebank.com",
            "password": f"passwd-{get_random_id()}",
        },
    )
    IntegrationConfiguration.objects.create(
        integration=provider,
        action=mb_action_pull_positions,
        data={"max_records_per_individual": 20000},
    )
    ensure_default_route(integration=provider)
    return provider


@pytest.fixture
def integration_type_liquidtech():
    return IntegrationType.objects.create(
        name="Liquidtech Integration",
        value="liquidtech",
        description="Standard Integration type for Liquidtech.",
    )


@pytest.fixture
def liquidtech_webhook(integration_type_liquidtech):
    return IntegrationWebhook.objects.create(
        name="Liquidtech Webhook",
        value="liquidtech_webhook",
        description="Liquidtech Webhook",
        integration_type=integration_type_liquidtech,
        schema={
            "title": "Liquidtech Payload Format",
            "type": "object",
            "properties": {
                "hex_format": {"title": "Data Format", "type": "object"},
                "hex_data_field": {"title": "Data Field", "type": "string"}
            },
            "required": ["hex_format", "hex_data_field"]
        }
    )


@pytest.fixture
def provider_liquidtech_with_webhook_config(
        get_random_id,
        organization,
        integration_type_liquidtech,
        liquidtech_webhook,
):
    provider = Integration.objects.create(
        type=integration_type_liquidtech,
        name=f"Liquidtech Webhooks",
        owner=organization,
        base_url=f"https://api.test.movebank.com",
    )
    # Configure webhook
    WebhookConfiguration.objects.create(
        integration=provider,
        webhook=liquidtech_webhook,
        data={
            "hex_data_field": "data",
            "hex_format": {
                "fields": [
                    {
                        "name": "start_bit",
                        "format": "B",
                        "output_type": "int"
                    },
                    {
                        "name": "v",
                        "format": "I"
                    },
                    {
                        "name": "interval",
                        "format": "H",
                        "output_type": "int"
                    },
                    {
                        "name": "meter_state_1",
                        "format": "B"
                    },
                    {
                        "name": "meter_state_2",
                        "format": "B",
                        "bit_fields": [
                            {
                                "name": "meter_batter_alarm",
                                "end_bit": 0,
                                "start_bit": 0,
                                "output_type": "bool"
                            },
                            {
                                "name": "empty_pipe_alarm",
                                "end_bit": 1,
                                "start_bit": 1,
                                "output_type": "bool"
                            },
                            {
                                "name": "reverse_flow_alarm",
                                "end_bit": 2,
                                "start_bit": 2,
                                "output_type": "bool"
                            },
                            {
                                "name": "over_range_alarm",
                                "end_bit": 3,
                                "start_bit": 3,
                                "output_type": "bool"
                            },
                            {
                                "name": "temp_alarm",
                                "end_bit": 4,
                                "start_bit": 4,
                                "output_type": "bool"
                            },
                            {
                                "name": "ee_error",
                                "end_bit": 5,
                                "start_bit": 5,
                                "output_type": "bool"
                            },
                            {
                                "name": "transduce_in_error",
                                "end_bit": 6,
                                "start_bit": 6,
                                "output_type": "bool"
                            },
                            {
                                "name": "transduce_out_error",
                                "end_bit": 7,
                                "start_bit": 7,
                                "output_type": "bool"
                            },
                            {
                                "name": "transduce_out_error",
                                "end_bit": 7,
                                "start_bit": 7,
                                "output_type": "bool"
                            }
                        ]
                    },
                    {
                        "name": "r1",
                        "format": "B",
                        "output_type": "int"
                    },
                    {
                        "name": "r2",
                        "format": "B",
                        "output_type": "int"
                    },
                    {
                        "name": "crc",
                        "format": "B"
                    }
                ],
                "byte_order": ">"
            }
        }
    )
    return provider


@pytest.fixture
def mb_action_push_observations(integration_type_movebank):
    return IntegrationAction.objects.create(
        integration_type=integration_type_movebank,
        type=IntegrationAction.ActionTypes.PUSH_DATA,
        name="Push Observations",
        value="push_observations",
        description="Push Tracking data to Movebank API",
        schema={
            "type": "object",
            "required": ["feed"],
            "properties": {"feed": {"type": "string"}},
        },
    )


@pytest.fixture
def destination_movebank(
        get_random_id,
        other_organization,
        integration_type_movebank,
        mb_action_push_observations,
):
    destination, _ = Integration.objects.get_or_create(
        type=integration_type_movebank,
        name=f"Movebank Site {get_random_id()}",
        owner=other_organization,
        base_url=f"https://api.test.movebank.com",
    )
    # Configure actions
    IntegrationConfiguration.objects.create(
        integration=destination,
        action=mb_action_push_observations,
        data={"feed": "gundi/earthranger"},
    )
    return destination


@pytest.fixture
def integration_type_cellstop():
    return IntegrationType.objects.create(
        name="Cellstop",
        value="cellstop",
        description="Standard integration type for Cellstop",
        service_url="https://cellstop-actions-runner-fakeurl123-uc.a.run.app"
    )


@pytest.fixture
def cellstop_action_fetch_samples(integration_type_cellstop):
    return IntegrationAction.objects.create(
        integration_type=integration_type_cellstop,
        type=IntegrationAction.ActionTypes.PULL_DATA,
        name="Fetch Samples",
        value="fetch_samples",
        description="Extract a data sample from cellstop",
    )

@pytest.fixture
def cellstop_fetch_samples_response():
    return {
        "observations_extracted": 2,
        "observations": [
            {
                "deviceId": 1234,
                "vehicleId": 5678,
                "x": 12.123456789,
                "y": -21.123456789,
                "name": "device-name-1",
                "regNo": "A12345B ",
                "iconURL": None,
                "address": "fake street 123, Somewhere",
                "alarm": None,
                "unit_msisdn": "+132456789",
                "speed": 0,
                "direction": 0,
                "time": 1713794324000,
                "timeStr": "2024-04-22T15:58:44",
                "ignOn": False
            },
            {
                "deviceId": 2345,
                "vehicleId": 6789,
                "x": 11.123456789,
                "y": -22.123456789,
                "name": "device-name-2",
                "regNo": "B45678C",
                "iconURL": None,
                "address": "fake street 456, Somewhere",
                "alarm": None,
                "unit_msisdn": "+123456789",
                "speed": 0,
                "direction": 0,
                "time": 1713794324000,
                "timeStr": "2024-04-22T15:58:44",
                "ignOn": False
            }
        ]
    }


@pytest.fixture
def cellstop_action_auth(integration_type_cellstop):
    return IntegrationAction.objects.create(
        integration_type=integration_type_cellstop,
        type=IntegrationAction.ActionTypes.AUTHENTICATION,
        name="Authenticate",
        value="auth",
        description="API Key to authenticate against Cellstop API",
        schema={
            "type": "object",
            "required": ["username", "password"],
            "properties": {
                "password": {"type": "string"},
                "username": {"type": "string"},
            },
        },
    )


@pytest.fixture
def cellstop_action_auth_response():
    return {
        "valid_credentials": True
    }


@pytest.fixture
def cellstop_integration(
        organization,
        other_organization,
        integration_type_cellstop,
        get_random_id,
        cellstop_action_auth,
        cellstop_action_fetch_samples,
):
    # Create the integration
    site_url = f"fake-{get_random_id()}.cellstopnm.com"
    integration, _ = Integration.objects.get_or_create(
        type=integration_type_cellstop,
        name=f"Cellstop Site {get_random_id()}",
        owner=organization,
        base_url=site_url,
    )
    # Configure actions
    IntegrationConfiguration.objects.create(
        integration=integration,
        action=cellstop_action_auth,
        data={
            "username": f"fake-username",
            "password": f"fake-passwd",
        },
    )
    IntegrationConfiguration.objects.create(
        integration=integration,
        action=cellstop_action_fetch_samples,
        data={},
    )
    ensure_default_route(integration=integration)
    return integration


@pytest.fixture
def integrations_list_er(
        mocker,
        settings,
        mock_get_dispatcher_defaults_from_gcp_secrets,
        organization,
        other_organization,
        integration_type_er,
        get_random_id,
        er_action_auth,
        er_action_pull_positions,
        er_action_pull_events,
        er_action_push_positions,
        er_action_push_events,
):
    # Override settings so a DispatcherDeployment is created
    settings.GCP_ENVIRONMENT_ENABLED = True
    # Mock the task to trigger the dispatcher deployment
    mocked_deployment_task = mocker.MagicMock()
    mocker.patch(
        "deployments.models.deploy_serverless_dispatcher", mocked_deployment_task
    )
    # Mock calls to external services
    mocker.patch("integrations.models.v2.models.get_dispatcher_defaults_from_gcp_secrets",
                 mock_get_dispatcher_defaults_from_gcp_secrets)
    # Patch on_commit to execute the function immediately
    mocker.patch("deployments.models.transaction.on_commit", lambda fn: fn())
    mocker.patch("integrations.models.v2.models.transaction.on_commit", lambda fn: fn())
    integrations = []
    for i in range(10):
        # Create the integration
        site_url = f"{get_random_id()}.pamdas.org"
        integration, _ = Integration.objects.get_or_create(
            type=integration_type_er,
            name=f"ER Site {get_random_id()}",
            owner=organization if i < 5 else other_organization,
            base_url=site_url,
        )
        # Configure actions
        IntegrationConfiguration.objects.create(
            integration=integration,
            action=er_action_auth,
            data={
                "username": f"eruser-{get_random_id()}",
                "password": f"passwd-{get_random_id()}",
            },
        )
        IntegrationConfiguration.objects.create(
            integration=integration,
            action=er_action_push_positions,
            data={"sensor_type": "collar"},
        )
        IntegrationConfiguration.objects.create(
            integration=integration, action=er_action_pull_positions
        )
        IntegrationConfiguration.objects.create(
            integration=integration, action=er_action_push_events
        )
        IntegrationConfiguration.objects.create(
            integration=integration, action=er_action_pull_events
        )
        integrations.append(integration)
        ensure_default_route(integration=integration)
    return integrations


@pytest.fixture
def integrations_list_smart(
        mocker,
        settings,
        mock_get_dispatcher_defaults_from_gcp_secrets_smart,
        organization,
        other_organization,
        integration_type_smart,
        get_random_id,
        smart_action_auth,
        smart_action_push_events,
):
    # Override settings so a DispatcherDeployment is created
    settings.GCP_ENVIRONMENT_ENABLED = True
    # Mock the task to trigger the dispatcher deployment
    mocked_deployment_task = mocker.MagicMock()
    mocker.patch(
        "deployments.models.deploy_serverless_dispatcher", mocked_deployment_task
    )
    # Mock calls to external services
    mocker.patch("integrations.models.v2.models.get_dispatcher_defaults_from_gcp_secrets",
                 mock_get_dispatcher_defaults_from_gcp_secrets_smart)
    # Patch on_commit to execute the function immediately
    mocker.patch("deployments.models.transaction.on_commit", lambda fn: fn())
    mocker.patch("integrations.models.v2.models.transaction.on_commit", lambda fn: fn())
    integrations = []
    for i in range(5):
        # Create the integration
        site_url = f"{get_random_id()}.smart.fakewps.org"
        integration, _ = Integration.objects.get_or_create(
            type=integration_type_smart,
            name=f"SMART Site Test {i}",
            owner=organization if i < 5 else other_organization,
            base_url=site_url,
        )
        # Configure actions
        IntegrationConfiguration.objects.create(
            integration=integration,
            action=smart_action_auth,
            data={
                "api_key": f"SMART-{get_random_id()}-KEY",
            },
        )
        IntegrationConfiguration.objects.create(
            integration=integration, action=smart_action_push_events
        )
        integrations.append(integration)
        ensure_default_route(integration=integration)
    return integrations


@pytest.fixture
def integrations_list_wpswatch(
        mocker,
        settings,
        mock_get_dispatcher_defaults_from_gcp_secrets_wps_watch,
        organization,
        integration_type_wpswatch,
        get_random_id,
        wpswatch_action_push_events
):
    # Override settings so a DispatcherDeployment is created
    settings.GCP_ENVIRONMENT_ENABLED = True
    # Mock the task to trigger the dispatcher deployment
    mocked_deployment_task = mocker.MagicMock()
    mocker.patch(
        "deployments.models.deploy_serverless_dispatcher", mocked_deployment_task
    )
    # Mock calls to external services
    mocker.patch("integrations.models.v2.models.get_dispatcher_defaults_from_gcp_secrets",
                 mock_get_dispatcher_defaults_from_gcp_secrets_wps_watch)
    # Patch on_commit to execute the function immediately
    mocker.patch("deployments.models.transaction.on_commit", lambda fn: fn())
    mocker.patch("integrations.models.v2.models.transaction.on_commit", lambda fn: fn())
    integrations = []
    for i in range(5):
        # Create the integration
        site_url = f"{get_random_id()}.wpswatch.fakewps.org"
        integration, _ = Integration.objects.get_or_create(
            type=integration_type_wpswatch,
            name=f"WPS Watch Site Test {i}",
            owner=organization,
            base_url=site_url,
        )
        IntegrationConfiguration.objects.create(
            integration=integration, action=wpswatch_action_push_events
        )
        integrations.append(integration)
        ensure_default_route(integration=integration)
    return integrations


@pytest.fixture
def make_random_sources(get_random_id):
    def _make_devices(provider, qty):
        sources = []
        configuration = SourceConfiguration.objects.create(
            name="Report every 10 minutes", data={"report_every": "10min"}
        )
        for i in range(qty):
            source, _ = Source.objects.get_or_create(
                external_id=f"device-{get_random_id()}", integration=provider
            )
            # Add a device state and a device configuration in some of them
            if i % 2:
                source.configuration = configuration
                source.save()
            else:
                SourceState.objects.create(
                    source=source, data={"last_data_received": "2023-05-17T09:52:13"}
                )
            sources.append(source)
        return sources

    return _make_devices


@pytest.fixture
def lotek_sources(
        get_random_id, organization, provider_lotek_panthera, make_random_sources
):
    return make_random_sources(provider=provider_lotek_panthera, qty=5)


@pytest.fixture
def movebank_sources(
        get_random_id, organization, provider_movebank_ewt, make_random_sources
):
    return make_random_sources(provider=provider_movebank_ewt, qty=3)


@pytest.fixture
def trap_tagger_sources(
        get_random_id, other_organization, provider_trap_tagger, make_random_sources
):
    return make_random_sources(provider=provider_trap_tagger, qty=5)


@pytest.fixture
def route_1(
        get_random_id,
        organization,
        lotek_sources,
        provider_lotek_panthera,
        integrations_list_er,
):
    rule, _ = Route.objects.get_or_create(
        name=f"Device Set to multiple destinations",
        owner=organization,
    )
    rule.data_providers.add(provider_lotek_panthera)
    rule.destinations.add(*integrations_list_er)
    # Filter data coming only from a subset of sources
    SourceFilter.objects.create(
        type=SourceFilter.SourceFilterTypes.SOURCE_LIST,
        name="Panthera Male Pumas",
        description="Select collars on male pumas in panthera reserve",
        order_number=1,
        selector=ListFilter(ids=[d.external_id for d in lotek_sources]).dict(),
        routing_rule=rule,
    )
    return rule


@pytest.fixture
def er_route_configuration_elephants():
    route_config = RouteConfiguration.objects.create(
        name="Set Elephant Subject Type", data={"subject_type": "elephant"}
    )
    return route_config


@pytest.fixture
def er_route_configuration_rangers():
    route_config = RouteConfiguration.objects.create(
        name="Set Ranger Subject Type", data={"subject_type": "ranger"}
    )
    return route_config


@pytest.fixture
def smart_route_configuration():
    route_config = RouteConfiguration.objects.create(
        name="Set Ranger Subject Type",
        data={
            "ca_uuids": ["8f7fbe1b-121a-4ef4-bda8-14f5581e44cf"],
            "transformation_rules": {"attribute_map": [], "category_map": []},
            "version": "7.5.6",
        },
    )
    return route_config


@pytest.fixture
def route_2(
        get_random_id,
        other_organization,
        movebank_sources,
        provider_movebank_ewt,
        integrations_list_er,
        er_route_configuration_elephants,
):
    route, _ = Route.objects.get_or_create(
        name=f"Device Set to single destination",
        owner=other_organization,
    )
    route.data_providers.add(provider_movebank_ewt)
    route.destinations.add(integrations_list_er[5])
    # Filter data coming only from a subset of sources
    SourceFilter.objects.create(
        type=SourceFilter.SourceFilterTypes.SOURCE_LIST,
        name="EWT Baby Elephants",
        description="Select collars on baby elephants in EWT reserve",
        order_number=1,
        selector=ListFilter(ids=[d.external_id for d in movebank_sources]).dict(),
        routing_rule=route,
    )
    # Add a custom configuration
    route.configuration = er_route_configuration_elephants
    route.save()
    return route


@pytest.fixture
def integration_type_trap_tagger():
    # Create an integration type for Trap Tagger
    integration_type = IntegrationType.objects.create(
        name="TrapTagger(Push)",
        value="trap_tagger",
        description="Standard type Trap Tagger Integration",
    )
    return integration_type


@pytest.fixture
def provider_trap_tagger(
        get_random_id,
        other_organization,
        integration_type_trap_tagger,
):
    provider, _ = Integration.objects.get_or_create(
        type=integration_type_trap_tagger,
        name=f"Trap Tagger Provider {get_random_id()}",
        owner=other_organization,
        base_url=f"https://api.test.traptagger.com",
    )
    ensure_default_route(integration=provider)
    return provider


@pytest.fixture
def keyauth_headers_trap_tagger(provider_trap_tagger):
    return {"HTTP_X_CONSUMER_USERNAME": f"integration:{str(provider_trap_tagger.id)}"}


@pytest.fixture
def keyauth_headers_lotek(provider_lotek_panthera):
    return {
        "HTTP_X_CONSUMER_USERNAME": f"integration:{str(provider_lotek_panthera.id)}"
    }


@pytest.fixture
def mock_publisher(mocker):
    return mocker.MagicMock()


@pytest.fixture
def mock_deduplication(mocker):
    mock_func = mocker.MagicMock()
    mock_func.return_value = False
    return mock_func


@pytest.fixture
def leopard_image_file():
    file_path = (
        Path(__file__)
        .resolve()
        .parent.joinpath("api/v2/tests/images/2023-07-05-1358_leopard.jpg")
    )
    return open(file_path, "rb")


@pytest.fixture
def wilddog_image_file():
    file_path = (
        Path(__file__)
        .resolve()
        .parent.joinpath("api/v2/tests/images/2023-07-05-1358_wilddog.jpg")
    )
    return open(file_path, "rb")


@pytest.fixture
def trap_tagger_event_trace(provider_trap_tagger, trap_tagger_sources):
    trace = GundiTrace(
        # We save only IDs, no sensitive data is saved
        data_provider=provider_trap_tagger,
        object_type="ev",
        source=trap_tagger_sources[0]
        # Other fields are filled in later by the routing services
    )
    trace.save()
    return trace


@pytest.fixture
def trap_tagger_event_update_trace(provider_trap_tagger, trap_tagger_sources, integrations_list_er):
    trace = GundiTrace(
        # We save only IDs, no sensitive data is saved
        data_provider=provider_trap_tagger,
        object_type="ev",
        source=trap_tagger_sources[0],
        destination_id=str(integrations_list_er[0].id),
        delivered_at="2023-07-10T19:35:34.425974Z",  # It was delivered
        external_id="c258f9f7-1a2e-4932-8d60-3acd2f59a1b2",  # ER uuid
        object_updated_at="2023-07-25T12:25:34.425974Z",  # Then the user sent an update
        # Other fields are filled in later by the routing services
    )
    trace.save()
    return trace


@pytest.fixture
def trap_tagger_to_movebank_observation_trace(provider_trap_tagger):
    trace = GundiTrace(
        # We save only IDs, no sensitive data is saved
        data_provider=provider_trap_tagger,
        object_type="obv",
        # Other fields are filled in later by the routing services
    )
    trace.save()
    return trace


@pytest.fixture
def event_delivered_trace(provider_trap_tagger, integrations_list_er):
    trace = GundiTrace(
        # We save only IDs, no sensitive data is saved
        data_provider=provider_trap_tagger,
        related_to=None,
        object_type="ev",
        destination=integrations_list_er[0],
        delivered_at="2023-07-10T19:35:34.425974Z",
        external_id="c258f9f7-1a2e-4932-8d60-3acd2f59a1b2",
    )
    trace.save()
    return trace


@pytest.fixture
def event_delivered_trace2(provider_trap_tagger, integrations_list_er):
    trace = GundiTrace(
        # We save only IDs, no sensitive data is saved
        data_provider=provider_trap_tagger,
        related_to=None,
        object_type="ev",
        destination=integrations_list_er[1],
        delivered_at="2023-07-10T19:36:15.425974Z",
        external_id="b358f9f7-1a2e-4932-8d60-3acd2f59a15f",
    )
    trace.save()
    return trace


@pytest.fixture
def attachment_delivered_trace(
        provider_trap_tagger, event_delivered_trace, integrations_list_er
):
    trace = GundiTrace(
        # We save only IDs, no sensitive data is saved
        data_provider=provider_trap_tagger,
        related_to=event_delivered_trace.object_id,
        object_type="ev",
        destination=integrations_list_er[0],
        delivered_at="2023-07-10T19:37:48.425974Z",
        external_id="c258f9f7-1a2e-4932-8d60-3acd2f59a1b2",
    )
    trace.save()
    return trace


@pytest.fixture
def mock_cloud_storage(mocker):
    mock_cloud_storage = mocker.MagicMock()
    mock_cloud_storage.save.return_value = "file.jpg"
    return mock_cloud_storage


@pytest.fixture
def trap_tagger_to_er_observation_delivered_event(
        mocker, trap_tagger_event_trace, integrations_list_er
):
    message = mocker.MagicMock()
    event_dict = {
        "event_id": "605535df-1b9b-412b-9fd5-e29b09582999",
        "timestamp": "2023-07-11 18:19:19.215459+00:00",
        "schema_version": "v1",
        "event_type": "ObservationDelivered",
        "payload": {
            "gundi_id": str(trap_tagger_event_trace.object_id),
            "related_to": None,
            "external_id": "35983ced-1216-4d43-81da-01ee90ba9b80",
            "data_provider_id": str(trap_tagger_event_trace.data_provider.id),
            "destination_id": str(integrations_list_er[0].id),
            "delivered_at": "2023-07-11 18:19:19.215015+00:00",
        },
    }
    data_bytes = json.dumps(event_dict).encode("utf-8")
    message.data = data_bytes
    return message


@pytest.fixture
def trap_tagger_to_smart_observation_delivered_event(
        mocker, trap_tagger_event_trace, integrations_list_smart
):
    message = mocker.MagicMock()
    event_dict = {
        "event_id": "605535df-1b9b-412b-9fd5-e29b09582999",
        "timestamp": "2023-07-11 18:19:19.215459+00:00",
        "schema_version": "v1",
        "event_type": "ObservationDelivered",
        "payload": {
            "gundi_id": str(trap_tagger_event_trace.object_id),
            "related_to": "",
            "external_id": str(trap_tagger_event_trace.object_id),  # gundi_id is used as id in smart
            "data_provider_id": str(trap_tagger_event_trace.data_provider.id),
            "destination_id": str(integrations_list_smart[0].id),
            "delivered_at": "2023-07-11 18:19:19.215015+00:00",
        },
    }
    data_bytes = json.dumps(event_dict).encode("utf-8")
    message.data = data_bytes
    return message


@pytest.fixture
def trap_tagger_observation_updated_event(
        mocker, trap_tagger_event_update_trace, integrations_list_er
):
    message = mocker.MagicMock()
    event_dict = {
        "event_id": "605535df-1b9b-412b-9fd5-e29b09582999",
        "timestamp": "2023-07-11 18:19:19.215459+00:00",
        "schema_version": "v1",
        "event_type": "ObservationUpdated",
        "payload": {
            "gundi_id": str(trap_tagger_event_update_trace.object_id),
            "related_to": None,
            "data_provider_id": str(trap_tagger_event_update_trace.data_provider.id),
            "destination_id": str(integrations_list_er[0].id),
            "updated_at": "2024-07-25 12:25:44.442696+00:00",
        },
    }
    data_bytes = json.dumps(event_dict).encode("utf-8")
    message.data = data_bytes
    return message


@pytest.fixture
def trap_tagger_to_movebank_observation_delivered_event(
        mocker, trap_tagger_to_movebank_observation_trace, destination_movebank
):
    message = mocker.MagicMock()
    event_dict = {
        "event_id": "605535df-1b9b-412b-9fd5-e29b09582999",
        "timestamp": "2023-07-11 18:19:19.215459+00:00",
        "schema_version": "v1",
        "event_type": "ObservationDelivered",
        "payload": {
            "gundi_id": str(trap_tagger_to_movebank_observation_trace.object_id),
            "related_to": None,
            "external_id": None,
            "data_provider_id": str(
                trap_tagger_to_movebank_observation_trace.data_provider.id
            ),
            "destination_id": str(destination_movebank.id),
            "delivered_at": "2023-07-11 18:19:19.215015+00:00",
        },
    }
    data_bytes = json.dumps(event_dict).encode("utf-8")
    message.data = data_bytes
    return message


@pytest.fixture
def trap_tagger_observation_delivered_event_two(
        mocker, trap_tagger_event_trace, integrations_list_er
):
    message = mocker.MagicMock()
    event_dict = {
        "event_id": "615535df-1b9b-412b-9fd5-e29b09582977",
        "timestamp": "2023-07-11 18:19:19.215459+00:00",
        "schema_version": "v1",
        "event_type": "ObservationDelivered",
        "payload": {
            "gundi_id": str(trap_tagger_event_trace.object_id),
            "related_to": None,
            "external_id": "46983ced-1216-4d43-81da-01ee90ba9b81",
            "data_provider_id": str(trap_tagger_event_trace.data_provider.id),
            "destination_id": str(integrations_list_er[1].id),
            "delivered_at": "2023-07-11 18:19:19.215015+00:00",
        },
    }
    data_bytes = json.dumps(event_dict).encode("utf-8")
    message.data = data_bytes
    return message


@pytest.fixture
def trap_tagger_observation_delivery_failed_event(
        mocker, trap_tagger_event_trace, integrations_list_er
):
    message = mocker.MagicMock()
    event_dict = {
        "event_id": "605535df-1b9b-412b-9fd5-e29b09582999",
        "timestamp": "2023-07-11 18:19:19.215459+00:00",
        "schema_version": "v1",
        "event_type": "ObservationDeliveryFailed",
        "payload": {
            "gundi_id": str(trap_tagger_event_trace.object_id),
            "related_to": None,
            "data_provider_id": str(trap_tagger_event_trace.data_provider.id),
            "destination_id": str(integrations_list_er[0].id),
            "delivered_at": "2023-07-11 18:19:19.215015+00:00",
        },
    }
    data_bytes = json.dumps(event_dict).encode("utf-8")
    message.data = data_bytes
    return message


@pytest.fixture
def trap_tagger_observation_delivery_failed_event_two(
        mocker, trap_tagger_event_trace, integrations_list_er
):
    message = mocker.MagicMock()
    event_dict = {
        "event_id": "705535df-1b9b-412b-9fd5-e29b09582988",
        "timestamp": "2023-07-11 18:19:19.215459+00:00",
        "schema_version": "v1",
        "event_type": "ObservationDeliveryFailed",
        "payload": {
            "gundi_id": str(trap_tagger_event_trace.object_id),
            "related_to": None,
            "data_provider_id": str(trap_tagger_event_trace.data_provider.id),
            "destination_id": str(integrations_list_er[1].id),
            "delivered_at": "2023-07-11 18:19:19.215015+00:00",
        },
    }
    data_bytes = json.dumps(event_dict).encode("utf-8")
    message.data = data_bytes
    return message


@pytest.fixture
def trap_tagger_observation_update_failed_event(
        mocker, trap_tagger_event_update_trace, integrations_list_er
):
    message = mocker.MagicMock()
    event_dict = {
        "event_id": "605535df-1b9b-412b-9fd5-e29b09582999",
        "timestamp": "2023-07-11 18:19:19.215459+00:00",
        "schema_version": "v1",
        "event_type": "ObservationUpdateFailed",
        "payload": {
            "gundi_id": str(trap_tagger_event_update_trace.object_id),
            "related_to": None,
            "data_provider_id": str(trap_tagger_event_update_trace.data_provider.id),
            "destination_id": str(integrations_list_er[0].id),
            "updated_at": "2024-07-25 12:25:44.442696+00:00",
        },
    }
    data_bytes = json.dumps(event_dict).encode("utf-8")
    message.data = data_bytes
    return message


@pytest.fixture
def mock_get_api_key():
    return PropertyMock(return_value="TestAp1k3y1234")


########################################################################################################################
# GUNDI 1.0
########################################################################################################################
class RemoteUser(NamedTuple):
    user: Any = None
    user_info: bytes = None


"""
Provisions a django user that is enrolled in the django group "Global Admin"
"""


@pytest.fixture
def global_admin_user(db, django_user_model):
    password = django_user_model.objects.make_random_password()
    user_const = dict(last_name="Owen", first_name="Harry")
    email = "harry.owen@vulcan.com"
    username = email

    user = django_user_model.objects.create_superuser(
        username, email, password, **user_const
    )

    user_info = {"sub": user.id, "username": username, "email": email}

    x_user_info = base64.b64encode(json.dumps(user_info).encode("utf-8"))

    group_name = DjangoGroups.GLOBAL_ADMIN.value
    group = Group.objects.create(name=group_name)
    user.groups.add(group)
    user.save()

    u = RemoteUser(user_info=x_user_info, user=user)

    return u


"""
Provisions a django user that is enrolled in the django group "Organization Member"
"""


@pytest.fixture
def organization_member_user(db, django_user_model):
    password = django_user_model.objects.make_random_password()
    user_const = dict(last_name="Owen", first_name="Harry")
    email = "harry.owen@vulcan.com"
    username = email

    user = django_user_model.objects.create_superuser(
        username, email, password, **user_const
    )

    user_info = {"sub": user.id, "username": username, "email": email}

    x_user_info = base64.b64encode(json.dumps(user_info).encode("utf-8"))

    group_name = DjangoGroups.ORGANIZATION_MEMBER.value
    group = Group.objects.create(name=group_name)
    user.groups.add(group)
    user.save()

    u = RemoteUser(user_info=x_user_info, user=user)

    return u


"""
Provisions a django user that simulates a service account or "client". Proper user info is added so that requests can be
made with header "HTTP_X_USERINFO" so that our middleware and backend appropriately add the client_id to the requests 
session, allowing the permissions checks to pass for IsServiceAccount. The associated client profile and 
dependent objects related to that client are also created here. 
"""


@pytest.fixture
def client_user(db, django_user_model):
    password = django_user_model.objects.make_random_password()
    user_const = dict(last_name="Owen", first_name="Harry")
    username = "service-account-test-function"
    email = "service-account-test-function@sintegrate.org"
    client_id = "test-function"

    user = django_user_model.objects.create_superuser(
        username, email, password, **user_const
    )

    user_info = {"sub": user.id, "client_id": client_id, "username": username}

    x_user_info = base64.b64encode(json.dumps(user_info).encode("utf-8"))

    u = RemoteUser(user_info=x_user_info, user=user)

    return u


@pytest.fixture
def setup_data(db, django_user_model):
    # ToDo: Review this once we start using factories
    org1 = Organization.objects.create(name="Org 1")

    org2 = Organization.objects.create(name="Org 2")

    iit1 = InboundIntegrationType.objects.create(
        name="Inbound Type 1",
        slug="inbound-type-one",
        description="Some integration type.",
    )

    iit2 = InboundIntegrationType.objects.create(
        name="Inbound Type 2",
        slug="inbound-type-two",
        description="Some integration type.",
    )

    iit3 = InboundIntegrationType.objects.create(
        name="Inbound Type 3",
        slug="inbound-type-three",
        description="Some integration type.",
        configuration_schema={"type": "object", "keys": {"test": {"type": "string"}}},
    )

    iit4 = InboundIntegrationType.objects.create(
        name="Inbound Type 4",
        slug="inbound-type-four",
        description="Some integration type.",
        configuration_schema={
            "type": "object",
            "keys": {
                "site_name": {"type": "string"},
                "email": {"type": "string", "format": "email"},
                "password": {"type": "string", "format": "password"},
            },
        },
    )

    oit1 = OutboundIntegrationType.objects.create(
        name="Outbound Type 1",
        slug="outbound-type-one",
        description="Some integration type.",
    )

    oit2 = OutboundIntegrationType.objects.create(
        name="Outbound Type 2",
        slug="outbound-type-two",
        description="Some integration type.",
    )

    oit3 = OutboundIntegrationType.objects.create(
        name="Outbound Type 3",
        slug="outbound-type-three",
        description="Some integration type.",
        configuration_schema={"type": "object", "keys": {"test": {"type": "string"}}},
    )

    oit4 = OutboundIntegrationType.objects.create(
        name="Outbound Type 4",
        slug="outbound-type-four",
        description="Some integration type.",
        configuration_schema={
            "type": "object",
            "keys": {
                "site_name": {"type": "string"},
                "email": {"type": "string", "format": "email"},
                "password": {"type": "string", "format": "password"},
            },
        },
    )

    oit_smart_connect = OutboundIntegrationType.objects.create(
        name="Smart Connect",
        slug="smart_connect",
    )

    bit1 = BridgeIntegrationType.objects.create(
        name="Bridge Type 1",
        slug="bridge-type-one",
        description="Bridge integration type 1.",
    )

    bit2 = BridgeIntegrationType.objects.create(
        name="Bridge Type 2",
        slug="bridge-type-two",
        description="Bridge integration type 2.",
        configuration_schema={"type": "object", "keys": {"test": {"type": "string"}}},
    )

    bit3 = BridgeIntegrationType.objects.create(
        name="Bridge Type 3",
        slug="bridge-type-three",
        description="Bridge integration type 3.",
        configuration_schema={
            "type": "object",
            "keys": {
                "site_name": {"type": "string"},
                "email": {"type": "string", "format": "email"},
                "password": {"type": "string", "format": "password"},
            },
        },
    )

    ii1 = InboundIntegrationConfiguration.objects.create(
        type=iit1, name="Inbound Configuration 1", owner=org1
    )

    ii2 = InboundIntegrationConfiguration.objects.create(
        type=iit2, name="Inbound Configuration 2", owner=org2
    )

    ii3 = InboundIntegrationConfiguration.objects.create(
        type=iit1, name="Inbound Configuration 3", owner=org2, enabled=False
    )

    ii4 = InboundIntegrationConfiguration.objects.create(
        type=iit2, name="Inbound Configuration 4", owner=org2, enabled=False
    )

    ii5 = InboundIntegrationConfiguration.objects.create(
        type=iit3, name="Inbound Configuration 4", owner=org2, enabled=False, state={}
    )

    oi1 = OutboundIntegrationConfiguration.objects.create(
        type=oit1, name="Outbound Configuration 1", owner=org1
    )

    oi2 = OutboundIntegrationConfiguration.objects.create(
        type=oit2, name="Outbound Configuration 2", owner=org2
    )

    oi3 = OutboundIntegrationConfiguration.objects.create(
        type=oit1, name="Outbound Configuration 3", owner=org1, enabled=False
    )

    oi4 = OutboundIntegrationConfiguration.objects.create(
        type=oit2, name="Outbound Configuration 4", owner=org2, enabled=False
    )

    oi5 = OutboundIntegrationConfiguration.objects.create(
        type=oit4, name="Outbound Configuration 4", owner=org2, enabled=False, state={}
    )

    bi1 = BridgeIntegration.objects.create(
        type=bit1, name="Bridge Integration 1", owner=org1, enabled=True
    )

    bi2 = BridgeIntegration.objects.create(
        type=bit2, name="Bridge Integration 2", owner=org2, enabled=False
    )

    bi3 = BridgeIntegration.objects.create(
        type=bit1, name="Bridge Integration 3", owner=org1, enabled=True
    )

    bi4 = BridgeIntegration.objects.create(
        type=bit2, name="Bridge Integration 4", owner=org2, enabled=False
    )

    bi5 = BridgeIntegration.objects.create(
        type=bit3,
        name="Bridge Integration 5",
        owner=org2,
        enabled=False,
        additional={"site_name": "foo"},
    )

    dg1 = DeviceGroup.objects.create(
        name="device group 1",
        owner=org1,
    )
    dg1.destinations.add(oi1)

    dg2 = DeviceGroup.objects.create(
        name="device group 2",
        owner=org2,
    )
    dg2.destinations.add(oi2)

    d1 = Device.objects.create(external_id="device-1", inbound_configuration=ii1)
    dg1.devices.add(d1)

    d2 = Device.objects.create(external_id="device-2", inbound_configuration=ii2)
    dg2.devices.add(d2)

    ds1 = DeviceState.objects.create(
        device=d1,
    )

    ds2 = DeviceState.objects.create(
        device=d2,
    )

    u1 = User.objects.create(username="user1", email="user1@sintegrate.org")
    u2 = User.objects.create(username="user2", email="user2@sintegrate.org")

    objects = {
        "org1": org1,
        "org2": org2,
        "iit1": iit1,
        "iit2": iit2,
        "iit3": iit3,
        "iit4": iit4,
        "oit1": oit1,
        "oit2": oit2,
        "oit3": oit3,
        "oit4": oit4,
        "oit_smart_connect": oit_smart_connect,  # "smart_connect" is a magic value
        "bit1": bit1,
        "bit2": bit2,
        "bit3": bit3,
        "ii1": ii1,
        "ii2": ii2,
        "ii3": ii3,
        "ii4": ii4,
        "ii5": ii5,
        "oi1": oi1,
        "oi2": oi2,
        "oi3": oi3,
        "oi4": oi4,
        "oi5": oi5,
        "bi1": bi1,
        "bi2": bi2,
        "bi3": bi3,
        "bi4": bi4,
        "bi5": bi5,
        "dg1": dg1,
        "dg2": dg2,
        "d1": d1,
        "d2": d2,
        "ds1": ds1,
        "ds2": ds2,
        "u1": u1,
        "u2": u2,
    }

    return objects


def setup_account_profile_mapping(mapping):
    for user, org, role in mapping:
        ap, created = AccountProfile.objects.get_or_create(user=user)

        apo = AccountProfileOrganization.objects.create(
            accountprofile=ap, organization=org, role=role
        )


@pytest.fixture
def mock_movebank_response():
    # Movebank's API doesn't return any content, just 200 OK.
    return ""


@pytest.fixture
def mock_movebank_client_class(mocker, mock_movebank_response):
    mocked_movebank_client_class = mocker.MagicMock()
    movebank_client_mock = mocker.MagicMock()
    movebank_client_mock.post_permissions.return_value = async_return(
        mock_movebank_response
    )
    movebank_client_mock.__aenter__.return_value = movebank_client_mock
    movebank_client_mock.__aexit__.return_value = mock_movebank_response
    movebank_client_mock.close.return_value = async_return(mock_movebank_response)
    mocked_movebank_client_class.return_value = movebank_client_mock
    return mocked_movebank_client_class


@pytest.fixture
def setup_movebank_test_data(db):
    # v1
    Organization.objects.create(name="Test Org")
    OutboundIntegrationType.objects.create(name="Movebank", slug="movebank")

    # v2
    IntegrationType.objects.create(name="Movebank", value="movebank")
    Integration.objects.create(
        type=IntegrationType.objects.first(),
        owner=Organization.objects.first(),
    )
    IntegrationAction.objects.create(
        type=IntegrationAction.ActionTypes.AUTHENTICATION,
        name="Permissions",
        value="permissions",
        integration_type=IntegrationType.objects.first(),
    )


@pytest.fixture
def setup_movebank_test_devices_sources(
        destination_movebank,
        legacy_integration_type_movebank,
        provider_lotek_panthera,
        mb_action_permissions,
        lotek_sources,
):
    # v1
    iit = InboundIntegrationType.objects.create(
        name="Inbound Type 1",
        slug="inbound-type-one",
        description="Some integration type.",
    )
    ii = InboundIntegrationConfiguration.objects.create(
        type=iit, name="Inbound Configuration 1", owner=Organization.objects.first()
    )
    oi = OutboundIntegrationConfiguration.objects.create(
        type=legacy_integration_type_movebank,
        owner=Organization.objects.first(),
        additional={
            "broker": "gcp_pubsub",
            "topic": "destination-v2-gundi-load-testing-legacy",
            "permissions": {
                "default_movebank_usernames": ["victorg"],
                "study": "gundi",
            },
        },
    )

    dg = DeviceGroup.objects.create(
        name="device group 1",
        owner=Organization.objects.first(),
    )
    dg.destinations.add(oi)

    d = Device.objects.create(external_id="device-1", inbound_configuration=ii)
    dg.devices.add(d)

    # v2
    integration_config = IntegrationConfiguration.objects.create(
        integration=destination_movebank,
        action=mb_action_permissions,
        data={
            "study": "gundi",
            "default_movebank_usernames": ["victorg"],
        },
    )
    route, _ = Route.objects.get_or_create(
        name=f"Device Set to single destination",
        owner=Organization.objects.first(),
    )
    route.data_providers.add(provider_lotek_panthera)
    route.destinations.add(destination_movebank)

    return {
        "v1": {
            "inbound": ii,
            "config": oi,
            "device_group": dg,
            "device": d,  # 1 device only for test
        },
        "v2": {
            "config": integration_config,
            "device": lotek_sources[0],  # 1 device only for test
        },
    }


@pytest.fixture
def legacy_integration_type_movebank():
    return OutboundIntegrationType.objects.create(
        name="MoveBank Legacy",
        slug="movebank",
        description="Default integration type for Movebank",
    )


@pytest.fixture
def legacy_integration_type_earthranger():
    return OutboundIntegrationType.objects.create(
        name="EarthRanger",
        slug="earth_ranger",
        description="Default integration type for Earth Ranger",
    )


@pytest.fixture
def legacy_inbound_integration_type_earthranger():
    return InboundIntegrationType.objects.create(
        name="EarthRanger",
        slug="earth_ranger",
        description="Default integration type for Earth Ranger as inbound",
    )


@pytest.fixture
def legacy_integration_type_smart():
    return OutboundIntegrationType.objects.create(
        name="SMART",
        slug="smart_connect",
        description="Default integration type for SMART",
    )


@pytest.fixture
def legacy_integration_type_wpswatch():
    return OutboundIntegrationType.objects.create(
        name="WPS Watch",
        slug="wps_watch",
        description="Default integration type for WPS Watch",
    )


@pytest.fixture
def inbound_integration_er(legacy_inbound_integration_type_earthranger, organization):
    return InboundIntegrationConfiguration.objects.create(
        name="EarthRanger Integration v1",
        type=legacy_inbound_integration_type_earthranger,
        owner=organization
    )


@pytest.fixture
def outbound_integration_er_with_kafka_dispatcher(
        legacy_integration_type_earthranger, organization,
):
    return OutboundIntegrationConfiguration.objects.create(
        name="EarthRanger Integration v1 with Kafka",
        type=legacy_integration_type_earthranger,
        endpoint="https://test0.fakepamdas.org",
        owner=organization,
        additional={
            "broker": "kafka",
        },
    )


@pytest.fixture
def outbound_integration_er_no_broker(
        legacy_integration_type_earthranger, organization,
):
    integration = OutboundIntegrationConfiguration.objects.create(
        name="EarthRanger Integration v1 no broker specified",
        endpoint="https://test1.fakepamdas.org",
        type=legacy_integration_type_earthranger,
        owner=organization
    )
    integration.additional = {}
    integration.save()
    return integration


@pytest.fixture
def outbound_integration_smart_with_kafka_dispatcher(
        legacy_integration_type_smart, organization,
):
    return OutboundIntegrationConfiguration.objects.create(
        name="SMART Integration v1 with Kafka",
        endpoint="https://test2.fakesmartconnect.com",
        type=legacy_integration_type_smart,
        owner=organization,
        additional={
            "broker": "kafka",
        },
    )


@pytest.fixture
def outbound_integration_smart(
        legacy_integration_type_smart, organization,
):
    return OutboundIntegrationConfiguration.objects.create(
        name="SMART Integration v1 with PubSub",
        endpoint="https://test2.fakesmartconnect.com",
        type=legacy_integration_type_smart,
        owner=organization
    )


@pytest.fixture
def observation_delivery_succeeded_event(provider_lotek_panthera, destination_movebank):
    return ActivityLog.objects.create(
        log_level=ActivityLog.LogLevels.DEBUG,
        log_type=ActivityLog.LogTypes.EVENT,
        origin=ActivityLog.Origin.DISPATCHER,
        integration=destination_movebank,
        value="observation_delivery_succeeded",
        title="Observation Delivered to 'https://gundi-er.pamdas.org'",
        details={
            "gundi_id": "2f7387e3-fbad-42fb-9ca9-4fb8d001e95f",
            "related_to": "",
            "external_id": None,
            "delivered_at": "2023-12-13 00:10:15.123456+00:00",
            "destination_id": str(destination_movebank.id),
            "data_provider_id": str(provider_lotek_panthera.id),
        },
        is_reversible=False,
    )


@pytest.fixture
def observation_delivery_succeeded_event_2(provider_movebank_ewt, integrations_list_er):
    destination = integrations_list_er[0]
    return ActivityLog.objects.create(
        log_level=ActivityLog.LogLevels.DEBUG,
        log_type=ActivityLog.LogTypes.EVENT,
        origin=ActivityLog.Origin.DISPATCHER,
        integration=destination,
        value="observation_delivery_succeeded",
        title="Observation Delivered to 'https://test.movebank.mpg.de'",
        details={
            "gundi_id": "1f7387e3-fbad-42fb-9ca9-4fb8d001e95e",
            "related_to": "",
            "external_id": None,
            "delivered_at": "2023-12-14 00:16:51.949252+00:00",
            "destination_id": str(destination.id),
            "data_provider_id": str(provider_movebank_ewt.id),
        },
        is_reversible=False,
    )


@pytest.fixture
def observation_delivery_failed_event(provider_lotek_panthera, destination_movebank):
    return ActivityLog.objects.create(
        log_level=ActivityLog.LogLevels.ERROR,
        log_type=ActivityLog.LogTypes.EVENT,
        origin=ActivityLog.Origin.DISPATCHER,
        integration=destination_movebank,
        value="observation_delivery_failed",
        title=f"Error Delivering observation to '{destination_movebank.base_url}'",
        details={
            "gundi_id": "3e7387e3-fbad-42fb-9ca9-4fb8d001e84c",
            "related_to": "",
            "external_id": None,
            "delivered_at": "2023-12-14 00:16:51.949252+00:00",
            "destination_id": str(destination_movebank.id),
            "data_provider_id": str(provider_lotek_panthera.id),
        },
        is_reversible=False,
    )


@pytest.fixture
def observation_delivery_failed_event_2(provider_lotek_panthera, integrations_list_er):
    destination = integrations_list_er[1]
    return ActivityLog.objects.create(
        log_level=ActivityLog.LogLevels.ERROR,
        log_type=ActivityLog.LogTypes.EVENT,
        origin=ActivityLog.Origin.DISPATCHER,
        integration=destination,
        value="observation_delivery_failed",
        title=f"Error Delivering observation to '{destination.base_url}'",
        details={
            "gundi_id": "2f7387e3-fbad-42fb-9ca9-4fb8d001e85a",
            "related_to": "",
            "external_id": None,
            "delivered_at": "2023-12-14 00:16:51.949252+00:00",
            "destination_id": str(destination.id),
            "data_provider_id": str(provider_lotek_panthera.id),
        },
        is_reversible=False,
    )


@pytest.fixture
def pull_observations_action_started_event(mocker, provider_lotek_panthera):
    message = mocker.MagicMock()
    event_dict = {
        "event_id": "cedd4805-7595-487a-9221-02286ed3048f",
        "timestamp": "2024-02-05 14:46:28.065161+00:00",
        "schema_version": "v1",
        "payload": {
            "integration_id": str(provider_lotek_panthera.id),
            "action_id": "pull_observations",
            "config_data": {"start_date": "2024-02-05"},
        },
        "event_type": "IntegrationActionStarted",
    }
    data_bytes = json.dumps(event_dict).encode("utf-8")
    message.data = data_bytes
    return message


@pytest.fixture
def pull_observations_action_complete_event(mocker, provider_lotek_panthera):
    message = mocker.MagicMock()
    event_dict = {
        "event_id": "d71b99ad-d047-42b9-b5bc-49d2cfb1259a",
        "timestamp": "2024-02-05 14:46:29.041589+00:00",
        "schema_version": "v1",
        "payload": {
            "integration_id": str(provider_lotek_panthera.id),
            "action_id": "pull_observations",
            "config_data": {"start_date": "2024-02-05"},
            "result": {"observations_extracted": 10},
        },
        "event_type": "IntegrationActionComplete",
    }
    data_bytes = json.dumps(event_dict).encode("utf-8")
    message.data = data_bytes
    return message


@pytest.fixture
def pull_observations_action_failed_event(mocker, provider_lotek_panthera):
    message = mocker.MagicMock()
    event_dict = {
        "event_id": "3c8a0759-c34c-4ad3-960a-398a17a50d31",
        "timestamp": "2024-02-05 15:11:02.139794+00:00",
        "schema_version": "v1",
        "payload": {
            "integration_id": str(provider_lotek_panthera.id),
            "action_id": "pull_observations",
            "config_data": {"start_date": "2024-02-05"},
            "error": "Error connecting to provider.",
        },
        "event_type": "IntegrationActionFailed",
    }
    data_bytes = json.dumps(event_dict).encode("utf-8")
    message.data = data_bytes
    return message


@pytest.fixture
def pull_observations_action_custom_log_event(mocker, provider_lotek_panthera):
    message = mocker.MagicMock()
    event_dict = {
        "event_id": "649aa769-5c65-45ff-ae80-40f0f2fedeb3",
        "timestamp": "2024-02-05 14:46:28.478350+00:00",
        "schema_version": "v1",
        "payload": {
            "integration_id": str(provider_lotek_panthera.id),
            "action_id": "pull_observations",
            "config_data": {"start_date": "2024-02-05"},
            "title": "Extracting observations with filter {'start_date': '2024-02-05'}",
            "level": 20,
            "data": {"start_date": "2024-01-01", "end_date": "2024-01-31"},
        },
        "event_type": "IntegrationActionCustomLog",
    }
    data_bytes = json.dumps(event_dict).encode("utf-8")
    message.data = data_bytes
    return message


@pytest.fixture
def webhook_started_event_pubsub(mocker, provider_liquidtech_with_webhook_config):
    pubsub_message = mocker.MagicMock()
    event = IntegrationWebhookStarted(
        payload=WebhookExecutionStarted(
            integration_id=str(provider_liquidtech_with_webhook_config.id),
            webhook_id='liquidtech_webhook',
            config_data={
                'json_schema': {'type': 'object', 'properties': {'received_at': {'type': 'string', 'format': 'date-time'}, 'end_device_ids': {'type': 'object', 'properties': {'dev_eui': {'type': 'string'}, 'dev_addr': {'type': 'string'}, 'device_id': {'type': 'string'}, 'application_ids': {'type': 'object', 'properties': {'application_id': {'type': 'string'}}, 'additionalProperties': False}}, 'additionalProperties': False}, 'uplink_message': {'type': 'object', 'properties': {'f_cnt': {'type': 'integer'}, 'f_port': {'type': 'integer'}, 'settings': {'type': 'object', 'properties': {'time': {'type': 'string', 'format': 'date-time'}, 'data_rate': {'type': 'object', 'properties': {'lora': {'type': 'object', 'properties': {'bandwidth': {'type': 'integer'}, 'coding_rate': {'type': 'string'}, 'spreading_factor': {'type': 'integer'}}, 'additionalProperties': False}}, 'additionalProperties': False}, 'frequency': {'type': 'string'}, 'timestamp': {'type': 'integer'}}, 'additionalProperties': False}, 'locations': {'type': 'object', 'properties': {'frm-payload': {'type': 'object', 'properties': {'source': {'type': 'string'}, 'latitude': {'type': 'number'}, 'longitude': {'type': 'number'}}, 'additionalProperties': False}}, 'additionalProperties': False}, 'frm_payload': {'type': 'string'}, 'network_ids': {'type': 'object', 'properties': {'ns_id': {'type': 'string'}, 'net_id': {'type': 'string'}, 'tenant_id': {'type': 'string'}, 'cluster_id': {'type': 'string'}, 'tenant_address': {'type': 'string'}, 'cluster_address': {'type': 'string'}}, 'additionalProperties': False}, 'received_at': {'type': 'string', 'format': 'date-time'}, 'rx_metadata': {'type': 'array', 'items': {'type': 'object', 'properties': {'snr': {'type': 'number'}, 'rssi': {'type': 'integer'}, 'time': {'type': 'string', 'format': 'date-time'}, 'gps_time': {'type': 'string', 'format': 'date-time'}, 'timestamp': {'type': 'integer'}, 'gateway_ids': {'type': 'object', 'properties': {'eui': {'type': 'string'}, 'gateway_id': {'type': 'string'}}, 'additionalProperties': False}, 'received_at': {'type': 'string', 'format': 'date-time'}, 'channel_rssi': {'type': 'integer'}, 'uplink_token': {'type': 'string'}, 'channel_index': {'type': 'integer'}}, 'additionalProperties': False}}, 'decoded_payload': {'type': 'object', 'properties': {'gps': {'type': 'string'}, 'latitude': {'type': 'number'}, 'longitude': {'type': 'number'}, 'batterypercent': {'type': 'integer'}}, 'additionalProperties': False}, 'consumed_airtime': {'type': 'string'}}, 'additionalProperties': False}, 'correlation_ids': {'type': 'array', 'items': {'type': 'string'}}}, 'additionalProperties': False},
                'jq_filter': '{"source": .end_device_ids.device_id, "source_name": .end_device_ids.device_id, "type": .uplink_message.locations."frm-payload".source, "recorded_at": .uplink_message.settings.time, "location": { "lat": .uplink_message.locations."frm-payload".latitude, "lon": .uplink_message.locations."frm-payload".longitude}, "additional": {"application_id": .end_device_ids.application_ids.application_id, "dev_eui": .end_device_ids.dev_eui, "dev_addr": .end_device_ids.dev_addr, "batterypercent": .uplink_message.decoded_payload.batterypercent, "gps": .uplink_message.decoded_payload.gps}}',
                'output_type': 'obv'
            }
        )
    )
    pubsub_message.data = json.dumps(event.dict(), default=str).encode("utf-8")
    return pubsub_message


@pytest.fixture
def webhook_complete_event_pubsub(mocker, provider_liquidtech_with_webhook_config):
    pubsub_message = mocker.MagicMock()
    event = IntegrationWebhookComplete(
        payload=WebhookExecutionComplete(
            integration_id=str(provider_liquidtech_with_webhook_config.id),
            webhook_id='liquidtech_webhook',
            config_data={
                'json_schema': {'type': 'object', 'properties': {'received_at': {'type': 'string', 'format': 'date-time'}, 'end_device_ids': {'type': 'object', 'properties': {'dev_eui': {'type': 'string'}, 'dev_addr': {'type': 'string'}, 'device_id': {'type': 'string'}, 'application_ids': {'type': 'object', 'properties': {'application_id': {'type': 'string'}}, 'additionalProperties': False}}, 'additionalProperties': False}, 'uplink_message': {'type': 'object', 'properties': {'f_cnt': {'type': 'integer'}, 'f_port': {'type': 'integer'}, 'settings': {'type': 'object', 'properties': {'time': {'type': 'string', 'format': 'date-time'}, 'data_rate': {'type': 'object', 'properties': {'lora': {'type': 'object', 'properties': {'bandwidth': {'type': 'integer'}, 'coding_rate': {'type': 'string'}, 'spreading_factor': {'type': 'integer'}}, 'additionalProperties': False}}, 'additionalProperties': False}, 'frequency': {'type': 'string'}, 'timestamp': {'type': 'integer'}}, 'additionalProperties': False}, 'locations': {'type': 'object', 'properties': {'frm-payload': {'type': 'object', 'properties': {'source': {'type': 'string'}, 'latitude': {'type': 'number'}, 'longitude': {'type': 'number'}}, 'additionalProperties': False}}, 'additionalProperties': False}, 'frm_payload': {'type': 'string'}, 'network_ids': {'type': 'object', 'properties': {'ns_id': {'type': 'string'}, 'net_id': {'type': 'string'}, 'tenant_id': {'type': 'string'}, 'cluster_id': {'type': 'string'}, 'tenant_address': {'type': 'string'}, 'cluster_address': {'type': 'string'}}, 'additionalProperties': False}, 'received_at': {'type': 'string', 'format': 'date-time'}, 'rx_metadata': {'type': 'array', 'items': {'type': 'object', 'properties': {'snr': {'type': 'number'}, 'rssi': {'type': 'integer'}, 'time': {'type': 'string', 'format': 'date-time'}, 'gps_time': {'type': 'string', 'format': 'date-time'}, 'timestamp': {'type': 'integer'}, 'gateway_ids': {'type': 'object', 'properties': {'eui': {'type': 'string'}, 'gateway_id': {'type': 'string'}}, 'additionalProperties': False}, 'received_at': {'type': 'string', 'format': 'date-time'}, 'channel_rssi': {'type': 'integer'}, 'uplink_token': {'type': 'string'}, 'channel_index': {'type': 'integer'}}, 'additionalProperties': False}}, 'decoded_payload': {'type': 'object', 'properties': {'gps': {'type': 'string'}, 'latitude': {'type': 'number'}, 'longitude': {'type': 'number'}, 'batterypercent': {'type': 'integer'}}, 'additionalProperties': False}, 'consumed_airtime': {'type': 'string'}}, 'additionalProperties': False}, 'correlation_ids': {'type': 'array', 'items': {'type': 'string'}}}, 'additionalProperties': False},
                'jq_filter': '{"source": .end_device_ids.device_id, "source_name": .end_device_ids.device_id, "type": .uplink_message.locations."frm-payload".source, "recorded_at": .uplink_message.settings.time, "location": { "lat": .uplink_message.locations."frm-payload".latitude, "lon": .uplink_message.locations."frm-payload".longitude}, "additional": {"application_id": .end_device_ids.application_ids.application_id, "dev_eui": .end_device_ids.dev_eui, "dev_addr": .end_device_ids.dev_addr, "batterypercent": .uplink_message.decoded_payload.batterypercent, "gps": .uplink_message.decoded_payload.gps}}',
                'output_type': 'obv'
            },
            result={'data_points_qty': 1}
        )
    )
    pubsub_message.data = json.dumps(event.dict(), default=str).encode("utf-8")
    return pubsub_message


@pytest.fixture
def webhook_failed_event_pubsub(mocker, provider_liquidtech_with_webhook_config):
    pubsub_message = mocker.MagicMock()
    event = IntegrationWebhookFailed(
        payload=WebhookExecutionFailed(
            integration_id=str(provider_liquidtech_with_webhook_config.id),
            webhook_id='liquidtech_webhook',
            config_data={
                'json_schema': {'type': 'object', 'properties': {'received_at': {'type': 'string', 'format': 'date-time'}, 'end_device_ids': {'type': 'object', 'properties': {'dev_eui': {'type': 'string'}, 'dev_addr': {'type': 'string'}, 'device_id': {'type': 'string'}, 'application_ids': {'type': 'object', 'properties': {'application_id': {'type': 'string'}}, 'additionalProperties': False}}, 'additionalProperties': False}, 'uplink_message': {'type': 'object', 'properties': {'f_cnt': {'type': 'integer'}, 'f_port': {'type': 'integer'}, 'settings': {'type': 'object', 'properties': {'time': {'type': 'string', 'format': 'date-time'}, 'data_rate': {'type': 'object', 'properties': {'lora': {'type': 'object', 'properties': {'bandwidth': {'type': 'integer'}, 'coding_rate': {'type': 'string'}, 'spreading_factor': {'type': 'integer'}}, 'additionalProperties': False}}, 'additionalProperties': False}, 'frequency': {'type': 'string'}, 'timestamp': {'type': 'integer'}}, 'additionalProperties': False}, 'locations': {'type': 'object', 'properties': {'frm-payload': {'type': 'object', 'properties': {'source': {'type': 'string'}, 'latitude': {'type': 'number'}, 'longitude': {'type': 'number'}}, 'additionalProperties': False}}, 'additionalProperties': False}, 'frm_payload': {'type': 'string'}, 'network_ids': {'type': 'object', 'properties': {'ns_id': {'type': 'string'}, 'net_id': {'type': 'string'}, 'tenant_id': {'type': 'string'}, 'cluster_id': {'type': 'string'}, 'tenant_address': {'type': 'string'}, 'cluster_address': {'type': 'string'}}, 'additionalProperties': False}, 'received_at': {'type': 'string', 'format': 'date-time'}, 'rx_metadata': {'type': 'array', 'items': {'type': 'object', 'properties': {'snr': {'type': 'number'}, 'rssi': {'type': 'integer'}, 'time': {'type': 'string', 'format': 'date-time'}, 'gps_time': {'type': 'string', 'format': 'date-time'}, 'timestamp': {'type': 'integer'}, 'gateway_ids': {'type': 'object', 'properties': {'eui': {'type': 'string'}, 'gateway_id': {'type': 'string'}}, 'additionalProperties': False}, 'received_at': {'type': 'string', 'format': 'date-time'}, 'channel_rssi': {'type': 'integer'}, 'uplink_token': {'type': 'string'}, 'channel_index': {'type': 'integer'}}, 'additionalProperties': False}}, 'decoded_payload': {'type': 'object', 'properties': {'gps': {'type': 'string'}, 'latitude': {'type': 'number'}, 'longitude': {'type': 'number'}, 'batterypercent': {'type': 'integer'}}, 'additionalProperties': False}, 'consumed_airtime': {'type': 'string'}}, 'additionalProperties': False}, 'correlation_ids': {'type': 'array', 'items': {'type': 'string'}}}, 'additionalProperties': False},
                'jq_filter': '{"source": .end_device_ids.device_id, "source_name": .end_device_ids.device_id, "type": .uplink_message.locations."frm-payload".source, "recorded_at": .uplink_message.settings.time, "location": { "lat": .uplink_message.locations."frm-payload".latitude, "lon": .uplink_message.locations."frm-payload".longitude}, "additional": {"application_id": .end_device_ids.application_ids.application_id, "dev_eui": .end_device_ids.dev_eui, "dev_addr": .end_device_ids.dev_addr, "batterypercent": .uplink_message.decoded_payload.batterypercent, "gps": .uplink_message.decoded_payload.gps}}',
                'output_type': 'patrol'
            },
            error='Invalid output type: patrol. Please review the configuration.'
        )
    )
    pubsub_message.data = json.dumps(event.dict(), default=str).encode("utf-8")
    return pubsub_message


@pytest.fixture
def webhook_custom_activity_log_event(mocker, provider_liquidtech_with_webhook_config):
    pubsub_message = mocker.MagicMock()
    event = IntegrationWebhookCustomLog(
        payload=CustomWebhookLog(
            integration_id=str(provider_liquidtech_with_webhook_config.id),
            webhook_id='liquidtech_webhook',
            config_data={},
            title='Webhook data transformed successfully',
            level=LogLevel.DEBUG,
            data={
                'transformed_data': [
                    {
                        'source': 'test-webhooks-mm',
                        'source_name': 'test-webhooks-mm',
                        'type': 'SOURCE_GPS',
                        'recorded_at': '2024-06-07T15:08:19.841Z',
                        'location': {'lat': -4.1234567, 'lon': 32.01234567890123},
                        'additional': {
                            'application_id': 'lt10-globalsat',
                            'dev_eui': '123456789ABCDEF0',  # pragma: allowlist secret
                            'dev_addr': '12345ABC',
                            'batterypercent': 100,
                            'gps': '3D fix'
                        }
                    }
                ]
            }
        )
    )
    pubsub_message.data = json.dumps(event.dict(), default=str).encode("utf-8")
    return pubsub_message


@pytest.fixture
def mock_dispatcher_secrets_er(dispatcher_source_release_1):
    return {'env_vars': {'REDIS_HOST': '127.0.0.1', 'BUCKET_NAME': 'cdip-files-dev', 'LOGGING_LEVEL': 'INFO',
                         'GCP_PROJECT_ID': 'cdip-test-proj', 'KEYCLOAK_REALM': 'cdip-test',
                         'KEYCLOAK_ISSUER': 'https://cdip-test.pamdas.org/auth/realms/cdip-dev',
                         'KEYCLOAK_SERVER': 'https://cdip-test.pamdas.org', 'PORTAL_AUTH_TTL': '300',
                         'DEAD_LETTER_TOPIC': 'dispatchers-dead-letter-dev', 'KEYCLOAK_AUDIENCE': 'cdip-test',
                         'TRACE_ENVIRONMENT': 'dev', 'CLOUD_STORAGE_TYPE': 'google',
                         'GUNDI_API_BASE_URL': 'https://api.dev.gundiservice.org', 'KEYCLOAK_CLIENT_ID': 'cdip-test-id',
                         'CDIP_ADMIN_ENDPOINT': 'https://cdip-prod01.pamdas.org',
                         'KEYCLOAK_CLIENT_UUID': 'test1234-5b2c-474b-99b1-aa85b8e6dabc',
                         'MAX_EVENT_AGE_SECONDS': '86400',
                         'KEYCLOAK_CLIENT_SECRET': 'test1234-d163-11ab-22b1-8f97f875e123',
                         'DISPATCHER_EVENTS_TOPIC': 'dispatcher-events-dev'},
            'deployment_settings': {'cpu': '1', 'region': 'us-central1', 'bucket_name': 'dispatchers-code-dev',
                                    'concurrency': 4, 'max_instances': 2, 'min_instances': 0,
                                    'vpc_connector': 'cdip-cloudrun-connector',
                                    'service_account': 'er-serverless-dispatchers@cdip-78ca.iam.gserviceaccount.com',
                                    'source_code_path': dispatcher_source_release_1}}


@pytest.fixture
def mock_dispatcher_secrets_smart(dispatcher_source_release_1):
    return {'env_vars': {'REDIS_HOST': '127.0.0.1', 'BUCKET_NAME': 'cdip-files-dev', 'LOGGING_LEVEL': 'INFO',
                         'GCP_PROJECT_ID': 'cdip-test-proj', 'KEYCLOAK_REALM': 'cdip-test',
                         'KEYCLOAK_ISSUER': 'https://cdip-test.pamdas.org/auth/realms/cdip-dev',
                         'KEYCLOAK_SERVER': 'https://cdip-test.pamdas.org', 'PORTAL_AUTH_TTL': '300',
                         'DEAD_LETTER_TOPIC': 'dispatchers-dead-letter-dev', 'KEYCLOAK_AUDIENCE': 'cdip-test',
                         'TRACE_ENVIRONMENT': 'dev', 'CLOUD_STORAGE_TYPE': 'google',
                         'GUNDI_API_BASE_URL': 'https://api.dev.gundiservice.org', 'KEYCLOAK_CLIENT_ID': 'cdip-test-id',
                         'CDIP_ADMIN_ENDPOINT': 'https://cdip-prod01.pamdas.org',
                         'KEYCLOAK_CLIENT_UUID': 'test1234-5b2c-474b-99b1-aa85b8e6dabc',
                         'MAX_EVENT_AGE_SECONDS': '86400',
                         'KEYCLOAK_CLIENT_SECRET': 'test1234-d163-11ab-22b1-8f97f875e123',
                         'DISPATCHER_EVENTS_TOPIC': 'dispatcher-events-dev'},
            'deployment_settings': {'cpu': '1', 'region': 'us-central1', 'bucket_name': 'dispatchers-code-dev',
                                    'concurrency': 4, 'max_instances': 2, 'min_instances': 0,
                                    'vpc_connector': 'cdip-cloudrun-connector',
                                    'service_account': 'er-serverless-dispatchers@cdip-78ca.iam.gserviceaccount.com',
                                    'docker_image_url': dispatcher_source_release_1}}


@pytest.fixture
def mock_dispatcher_secrets_wps_watch(dispatcher_source_release_1):
    return {'env_vars': {'REDIS_HOST': '127.0.0.1', 'BUCKET_NAME': 'cdip-files-dev', 'LOGGING_LEVEL': 'INFO',
                         'GCP_PROJECT_ID': 'cdip-test-proj', 'KEYCLOAK_REALM': 'cdip-test',
                         'KEYCLOAK_ISSUER': 'https://cdip-test.pamdas.org/auth/realms/cdip-dev',
                         'KEYCLOAK_SERVER': 'https://cdip-test.pamdas.org', 'PORTAL_AUTH_TTL': '300',
                         'DEAD_LETTER_TOPIC': 'dispatchers-dead-letter-dev', 'KEYCLOAK_AUDIENCE': 'cdip-test',
                         'TRACE_ENVIRONMENT': 'dev', 'CLOUD_STORAGE_TYPE': 'google',
                         'GUNDI_API_BASE_URL': 'https://api.dev.gundiservice.org', 'KEYCLOAK_CLIENT_ID': 'cdip-test-id',
                         'CDIP_ADMIN_ENDPOINT': 'https://cdip-prod01.pamdas.org',
                         'KEYCLOAK_CLIENT_UUID': 'test1234-5b2c-474b-99b1-aa85b8e6dabc',
                         'MAX_EVENT_AGE_SECONDS': '86400',
                         'KEYCLOAK_CLIENT_SECRET': 'test1234-d163-11ab-22b1-8f97f875e123',
                         'DISPATCHER_EVENTS_TOPIC': 'dispatcher-events-dev'},
            'deployment_settings': {'cpu': '1', 'region': 'us-central1', 'bucket_name': 'dispatchers-code-dev',
                                    'concurrency': 4, 'max_instances': 2, 'min_instances': 0,
                                    'vpc_connector': 'cdip-cloudrun-connector',
                                    'service_account': 'er-serverless-dispatchers@cdip-78ca.iam.gserviceaccount.com',
                                    'docker_image_url': dispatcher_source_release_1}}


@pytest.fixture
def mock_get_dispatcher_defaults_from_gcp_secrets(mocker, mock_dispatcher_secrets_er):
    mock = mocker.MagicMock()
    mock.return_value = mock_dispatcher_secrets_er
    return mock


@pytest.fixture
def mock_get_dispatcher_defaults_from_gcp_secrets_smart(mocker, mock_dispatcher_secrets_smart):
    mock = mocker.MagicMock()
    mock.return_value = mock_dispatcher_secrets_smart
    return mock


@pytest.fixture
def mock_get_dispatcher_defaults_from_gcp_secrets_wps_watch(mocker, mock_dispatcher_secrets_wps_watch):
    mock = mocker.MagicMock()
    mock.return_value = mock_dispatcher_secrets_wps_watch
    return mock


@pytest.fixture
def das_client_events_response():
    today = datetime.now().strftime('%Y-%m-%d')
    return [
        {'id': '537466c0-f4a8-400a-91ae-b7da981ecfd5', 'location': {'latitude': -41.145026, 'longitude': -71.261822},
         'time': f'{today}T07:37:59-06:00', 'end_time': None, 'serial_number': 49575, 'message': '', 'provenance': '',
         'event_type': '169361d0-62b8-411d-a8e6-019823805016_humanactivity_shelterorcamp', 'priority': 0,
         'priority_label': 'Gray', 'attributes': {}, 'comment': None, 'title': None,
         'reported_by': {'content_type': 'observations.subject', 'id': 'f9f4a3dd-fae2-4147-8259-0551ff5691e6',
                         'name': 'Mariano Martinez', 'subject_type': 'person', 'subject_subtype': 'ranger',
                         'common_name': None, 'additional': {}, 'created_at': '2024-03-13T11:07:40.684181-06:00',
                         'updated_at': '2024-03-13T11:07:40.777391-06:00', 'is_active': True,
                         'user': {'id': '3f29bdb1-395c-4a29-9c64-5bd79109765c'}, 'tracks_available': False,
                         'image_url': '/static/ranger-black.svg'}, 'state': 'active', 'is_contained_in': [],
         'sort_at': f'{today}T07:38:04.287767-06:00', 'patrol_segments': [], 'geometry': None,
         'updated_at': f'{today}T07:38:04.287767-06:00', 'created_at': f'{today}T07:38:00.730106-06:00',
         'icon_id': '169361d0-62b8-411d-a8e6-019823805016_humanactivity_shelterorcamp',
         'event_details': {'updates': []}, 'files': [{'id': '84ed5275-7c9f-451c-a726-c559fc90e808', 'comment': '',
                                                      'created_at': f'{today}T07:38:04.250161-06:00',
                                                      'updated_at': f'{today}T07:38:04.250249-06:00', 'updates': [
                {'message': 'File Added: 2024-04-12_10-37-55_shelter_camp_observ....jpg',
                 'time': f'{today}T13:38:04.270018+00:00', 'text': '',
                 'user': {'username': 'marianom', 'first_name': 'Mariano', 'last_name': 'Martinez',
                          'id': '3f29bdb1-395c-4a29-9c64-5bd79109765c', 'content_type': 'accounts.user'},
                 'type': 'add_eventfile'}],
                                                      'url': 'https://gundi-er.pamdas.org/api/v1.0/activity/event/537466c0-f4a8-400a-91ae-b7da981ecfd5/file/84ed5275-7c9f-451c-a726-c559fc90e808/',
                                                      'images': {
                                                          'original': 'https://gundi-er.pamdas.org/api/v1.0/activity/event/537466c0-f4a8-400a-91ae-b7da981ecfd5/file/84ed5275-7c9f-451c-a726-c559fc90e808/original/2024-04-12_10-37-55_shelter_camp_observ....jpg',
                                                          'icon': 'https://gundi-er.pamdas.org/api/v1.0/activity/event/537466c0-f4a8-400a-91ae-b7da981ecfd5/file/84ed5275-7c9f-451c-a726-c559fc90e808/icon/2024-04-12_10-37-55_shelter_camp_observ....jpg',
                                                          'thumbnail': 'https://gundi-er.pamdas.org/api/v1.0/activity/event/537466c0-f4a8-400a-91ae-b7da981ecfd5/file/84ed5275-7c9f-451c-a726-c559fc90e808/thumbnail/2024-04-12_10-37-55_shelter_camp_observ....jpg',
                                                          'large': 'https://gundi-er.pamdas.org/api/v1.0/activity/event/537466c0-f4a8-400a-91ae-b7da981ecfd5/file/84ed5275-7c9f-451c-a726-c559fc90e808/large/2024-04-12_10-37-55_shelter_camp_observ....jpg',
                                                          'xlarge': 'https://gundi-er.pamdas.org/api/v1.0/activity/event/537466c0-f4a8-400a-91ae-b7da981ecfd5/file/84ed5275-7c9f-451c-a726-c559fc90e808/xlarge/2024-04-12_10-37-55_shelter_camp_observ....jpg'},
                                                      'filename': f'{today}_10-37-55_shelter_camp_observ....jpg',
                                                      'file_type': 'image',
                                                      'icon_url': 'https://gundi-er.pamdas.org/api/v1.0/activity/event/537466c0-f4a8-400a-91ae-b7da981ecfd5/file/84ed5275-7c9f-451c-a726-c559fc90e808/icon/2024-04-12_10-37-55_shelter_camp_observ....jpg'}],
         'related_subjects': [], 'event_category': 'smart',
         'url': 'https://gundi-er.pamdas.org/api/v1.0/activity/event/537466c0-f4a8-400a-91ae-b7da981ecfd5',
         'image_url': 'https://gundi-er.pamdas.org/static/generic-gray.svg',
         'geojson': {'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [-71.261822, -41.145026]},
                     'properties': {'message': '', 'datetime': f'{today}T13:37:59+00:00',
                                    'image': 'https://gundi-er.pamdas.org/static/generic-gray.svg',
                                    'icon': {'iconUrl': 'https://gundi-er.pamdas.org/static/generic-gray.svg',
                                             'iconSize': [25, 25], 'iconAncor': [12, 12], 'popupAncor': [0, -13],
                                             'className': 'dot'}}}, 'is_collection': False, 'updates': [
            {'message': 'Changed State: new → active', 'time': f'{today}T13:38:04.303464+00:00',
             'user': {'username': 'marianom', 'first_name': 'Mariano', 'last_name': 'Martinez',
                      'id': '3f29bdb1-395c-4a29-9c64-5bd79109765c', 'content_type': 'accounts.user'}, 'type': 'read'},
            {'message': 'File Added: 2024-04-12_10-37-55_shelter_camp_observ....jpg',
             'time': f'{today}T13:38:04.270018+00:00', 'text': '',
             'user': {'username': 'marianom', 'first_name': 'Mariano', 'last_name': 'Martinez',
                      'id': '3f29bdb1-395c-4a29-9c64-5bd79109765c', 'content_type': 'accounts.user'},
             'type': 'add_eventfile'}, {'message': 'Created', 'time': f'{today}T13:38:00.816986+00:00',
                                        'user': {'username': 'marianom', 'first_name': 'Mariano',
                                                 'last_name': 'Martinez', 'id': '3f29bdb1-395c-4a29-9c64-5bd79109765c',
                                                 'content_type': 'accounts.user'}, 'type': 'add_event'}],
         'patrols': []},
        {'id': 'ecaf94dc-1a75-4163-9795-784db8cbf29e', 'location': {'latitude': -41.145139, 'longitude': -71.262131},
         'time': f'{today}T06:58:32-06:00', 'end_time': None, 'serial_number': 49574, 'message': '', 'provenance': '',
         'event_type': '169361d0-62b8-411d-a8e6-019823805016_animals', 'priority': 0, 'priority_label': 'Gray',
         'attributes': {}, 'comment': None, 'title': None,
         'reported_by': {'content_type': 'observations.subject', 'id': 'f9f4a3dd-fae2-4147-8259-0551ff5691e6',
                         'name': 'Mariano Martinez', 'subject_type': 'person', 'subject_subtype': 'ranger',
                         'common_name': None, 'additional': {}, 'created_at': '2024-03-13T11:07:40.684181-06:00',
                         'updated_at': '2024-03-13T11:07:40.777391-06:00', 'is_active': True,
                         'user': {'id': '3f29bdb1-395c-4a29-9c64-5bd79109765c'}, 'tracks_available': False,
                         'image_url': '/static/ranger-black.svg'}, 'state': 'active', 'is_contained_in': [],
         'sort_at': f'{today}T06:58:35.476603-06:00', 'patrol_segments': [], 'geometry': None,
         'updated_at': f'{today}T06:58:35.476603-06:00', 'created_at': f'{today}T06:58:33.372986-06:00',
         'icon_id': '169361d0-62b8-411d-a8e6-019823805016_animals', 'event_details': {'updates': []}, 'files': [
            {'id': '73be60b8-19fb-4e3c-ab66-bada9fcae6c6', 'comment': '',
             'created_at': f'{today}T06:58:35.432821-06:00', 'updated_at': f'{today}T06:58:35.432852-06:00',
             'updates': [
                 {'message': 'File Added: 2024-04-12_09-58-23_wildlife.jpg', 'time': f'{today}T12:58:35.457115+00:00',
                  'text': '', 'user': {'username': 'marianom', 'first_name': 'Mariano', 'last_name': 'Martinez',
                                       'id': '3f29bdb1-395c-4a29-9c64-5bd79109765c', 'content_type': 'accounts.user'},
                  'type': 'add_eventfile'}],
             'url': 'https://gundi-er.pamdas.org/api/v1.0/activity/event/ecaf94dc-1a75-4163-9795-784db8cbf29e/file/73be60b8-19fb-4e3c-ab66-bada9fcae6c6/',
             'images': {
                 'original': 'https://gundi-er.pamdas.org/api/v1.0/activity/event/ecaf94dc-1a75-4163-9795-784db8cbf29e/file/73be60b8-19fb-4e3c-ab66-bada9fcae6c6/original/2024-04-12_09-58-23_wildlife.jpg',
                 'icon': 'https://gundi-er.pamdas.org/api/v1.0/activity/event/ecaf94dc-1a75-4163-9795-784db8cbf29e/file/73be60b8-19fb-4e3c-ab66-bada9fcae6c6/icon/2024-04-12_09-58-23_wildlife.jpg',
                 'thumbnail': 'https://gundi-er.pamdas.org/api/v1.0/activity/event/ecaf94dc-1a75-4163-9795-784db8cbf29e/file/73be60b8-19fb-4e3c-ab66-bada9fcae6c6/thumbnail/2024-04-12_09-58-23_wildlife.jpg',
                 'large': 'https://gundi-er.pamdas.org/api/v1.0/activity/event/ecaf94dc-1a75-4163-9795-784db8cbf29e/file/73be60b8-19fb-4e3c-ab66-bada9fcae6c6/large/2024-04-12_09-58-23_wildlife.jpg',
                 'xlarge': 'https://gundi-er.pamdas.org/api/v1.0/activity/event/ecaf94dc-1a75-4163-9795-784db8cbf29e/file/73be60b8-19fb-4e3c-ab66-bada9fcae6c6/xlarge/2024-04-12_09-58-23_wildlife.jpg'},
             'filename': f'{today}_09-58-23_wildlife.jpg', 'file_type': 'image',
             'icon_url': 'https://gundi-er.pamdas.org/api/v1.0/activity/event/ecaf94dc-1a75-4163-9795-784db8cbf29e/file/73be60b8-19fb-4e3c-ab66-bada9fcae6c6/icon/2024-04-12_09-58-23_wildlife.jpg'}],
         'related_subjects': [], 'event_category': 'smart',
         'url': 'https://gundi-er.pamdas.org/api/v1.0/activity/event/ecaf94dc-1a75-4163-9795-784db8cbf29e',
         'image_url': 'https://gundi-er.pamdas.org/static/generic-gray.svg',
         'geojson': {'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [-71.262131, -41.145139]},
                     'properties': {'message': '', 'datetime': f'{today}T12:58:32+00:00',
                                    'image': 'https://gundi-er.pamdas.org/static/generic-gray.svg',
                                    'icon': {'iconUrl': 'https://gundi-er.pamdas.org/static/generic-gray.svg',
                                             'iconSize': [25, 25], 'iconAncor': [12, 12], 'popupAncor': [0, -13],
                                             'className': 'dot'}}}, 'is_collection': False, 'updates': [
            {'message': 'Changed State: new → active', 'time': f'{today}T12:58:35.495824+00:00',
             'user': {'username': 'marianom', 'first_name': 'Mariano', 'last_name': 'Martinez',
                      'id': '3f29bdb1-395c-4a29-9c64-5bd79109765c', 'content_type': 'accounts.user'}, 'type': 'read'},
            {'message': 'File Added: 2024-04-12_09-58-23_wildlife.jpg', 'time': f'{today}T12:58:35.457115+00:00',
             'text': '', 'user': {'username': 'marianom', 'first_name': 'Mariano', 'last_name': 'Martinez',
                                  'id': '3f29bdb1-395c-4a29-9c64-5bd79109765c', 'content_type': 'accounts.user'},
             'type': 'add_eventfile'}, {'message': 'Created', 'time': f'{today}T12:58:33.432933+00:00',
                                        'user': {'username': 'marianom', 'first_name': 'Mariano',
                                                 'last_name': 'Martinez', 'id': '3f29bdb1-395c-4a29-9c64-5bd79109765c',
                                                 'content_type': 'accounts.user'}, 'type': 'add_event'}],
         'patrols': []},
        {'id': 'e74fd6de-bfa9-44a8-b878-9689afd53079', 'location': {'latitude': -41.145106, 'longitude': -71.26202},
         'time': f'{today}T06:30:19-06:00', 'end_time': None, 'serial_number': 49573, 'message': '', 'provenance': '',
         'event_type': '169361d0-62b8-411d-a8e6-019823805016_humanactivity_weaponsequipment', 'priority': 0,
         'priority_label': 'Gray', 'attributes': {}, 'comment': None, 'title': None,
         'reported_by': {'content_type': 'observations.subject', 'id': 'f9f4a3dd-fae2-4147-8259-0551ff5691e6',
                         'name': 'Mariano Martinez', 'subject_type': 'person', 'subject_subtype': 'ranger',
                         'common_name': None, 'additional': {}, 'created_at': '2024-03-13T11:07:40.684181-06:00',
                         'updated_at': '2024-03-13T11:07:40.777391-06:00', 'is_active': True,
                         'user': {'id': '3f29bdb1-395c-4a29-9c64-5bd79109765c'}, 'tracks_available': False,
                         'image_url': '/static/ranger-black.svg'}, 'state': 'active', 'is_contained_in': [],
         'sort_at': f'{today}T06:30:22.850273-06:00', 'patrol_segments': [], 'geometry': None,
         'updated_at': f'{today}T06:30:22.850273-06:00', 'created_at': f'{today}T06:30:20.768199-06:00',
         'icon_id': '169361d0-62b8-411d-a8e6-019823805016_humanactivity_weaponsequipment',
         'event_details': {'numberofweaponorgear': 1, 'actiontakenweaponorgar': 'confiscated',
                           'typeofevidentmaterials': 'other', 'updates': []}, 'files': [
            {'id': 'cbfe2a06-aba3-489a-bf6d-e4690d1f0c3f', 'comment': '',
             'created_at': f'{today}T06:30:22.811731-06:00', 'updated_at': f'{today}T06:30:22.811771-06:00',
             'updates': [{'message': 'File Added: 2024-04-12_09-29-39_weapons_and_gear_se....jpg',
                          'time': f'{today}T12:30:22.832590+00:00', 'text': '',
                          'user': {'username': 'marianom', 'first_name': 'Mariano', 'last_name': 'Martinez',
                                   'id': '3f29bdb1-395c-4a29-9c64-5bd79109765c', 'content_type': 'accounts.user'},
                          'type': 'add_eventfile'}],
             'url': 'https://gundi-er.pamdas.org/api/v1.0/activity/event/e74fd6de-bfa9-44a8-b878-9689afd53079/file/cbfe2a06-aba3-489a-bf6d-e4690d1f0c3f/',
             'images': {
                 'original': 'https://gundi-er.pamdas.org/api/v1.0/activity/event/e74fd6de-bfa9-44a8-b878-9689afd53079/file/cbfe2a06-aba3-489a-bf6d-e4690d1f0c3f/original/2024-04-12_09-29-39_weapons_and_gear_se....jpg',
                 'icon': 'https://gundi-er.pamdas.org/api/v1.0/activity/event/e74fd6de-bfa9-44a8-b878-9689afd53079/file/cbfe2a06-aba3-489a-bf6d-e4690d1f0c3f/icon/2024-04-12_09-29-39_weapons_and_gear_se....jpg',
                 'thumbnail': 'https://gundi-er.pamdas.org/api/v1.0/activity/event/e74fd6de-bfa9-44a8-b878-9689afd53079/file/cbfe2a06-aba3-489a-bf6d-e4690d1f0c3f/thumbnail/2024-04-12_09-29-39_weapons_and_gear_se....jpg',
                 'large': 'https://gundi-er.pamdas.org/api/v1.0/activity/event/e74fd6de-bfa9-44a8-b878-9689afd53079/file/cbfe2a06-aba3-489a-bf6d-e4690d1f0c3f/large/2024-04-12_09-29-39_weapons_and_gear_se....jpg',
                 'xlarge': 'https://gundi-er.pamdas.org/api/v1.0/activity/event/e74fd6de-bfa9-44a8-b878-9689afd53079/file/cbfe2a06-aba3-489a-bf6d-e4690d1f0c3f/xlarge/2024-04-12_09-29-39_weapons_and_gear_se....jpg'},
             'filename': f'{today}_09-29-39_weapons_and_gear_se....jpg', 'file_type': 'image',
             'icon_url': 'https://gundi-er.pamdas.org/api/v1.0/activity/event/e74fd6de-bfa9-44a8-b878-9689afd53079/file/cbfe2a06-aba3-489a-bf6d-e4690d1f0c3f/icon/2024-04-12_09-29-39_weapons_and_gear_se....jpg'}],
         'related_subjects': [], 'event_category': 'smart',
         'url': 'https://gundi-er.pamdas.org/api/v1.0/activity/event/e74fd6de-bfa9-44a8-b878-9689afd53079',
         'image_url': 'https://gundi-er.pamdas.org/static/generic-gray.svg',
         'geojson': {'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [-71.26202, -41.145106]},
                     'properties': {'message': '', 'datetime': f'{today}T12:30:19+00:00',
                                    'image': 'https://gundi-er.pamdas.org/static/generic-gray.svg',
                                    'icon': {'iconUrl': 'https://gundi-er.pamdas.org/static/generic-gray.svg',
                                             'iconSize': [25, 25], 'iconAncor': [12, 12], 'popupAncor': [0, -13],
                                             'className': 'dot'}}}, 'is_collection': False, 'updates': [
            {'message': 'Changed State: new → active', 'time': f'{today}T12:30:22.871420+00:00',
             'user': {'username': 'marianom', 'first_name': 'Mariano', 'last_name': 'Martinez',
                      'id': '3f29bdb1-395c-4a29-9c64-5bd79109765c', 'content_type': 'accounts.user'}, 'type': 'read'},
            {'message': 'File Added: 2024-04-12_09-29-39_weapons_and_gear_se....jpg',
             'time': f'{today}T12:30:22.832590+00:00', 'text': '',
             'user': {'username': 'marianom', 'first_name': 'Mariano', 'last_name': 'Martinez',
                      'id': '3f29bdb1-395c-4a29-9c64-5bd79109765c', 'content_type': 'accounts.user'},
             'type': 'add_eventfile'}, {'message': 'Created', 'time': f'{today}T12:30:20.821637+00:00',
                                        'user': {'username': 'marianom', 'first_name': 'Mariano',
                                                 'last_name': 'Martinez', 'id': '3f29bdb1-395c-4a29-9c64-5bd79109765c',
                                                 'content_type': 'accounts.user'}, 'type': 'add_event'}],
         'patrols': []},
        {'id': 'ede43c88-f282-46eb-ae63-227da082c2b4', 'location': {'latitude': -41.145032, 'longitude': -71.261906},
         'time': f'{today}T06:22:11-06:00', 'end_time': None, 'serial_number': 49572, 'message': '', 'provenance': '',
         'event_type': '169361d0-62b8-411d-a8e6-019823805016_humanactivity_poaching', 'priority': 0,
         'priority_label': 'Gray', 'attributes': {}, 'comment': None, 'title': None,
         'reported_by': {'content_type': 'observations.subject', 'id': 'f9f4a3dd-fae2-4147-8259-0551ff5691e6',
                         'name': 'Mariano Martinez', 'subject_type': 'person', 'subject_subtype': 'ranger',
                         'common_name': None, 'additional': {}, 'created_at': '2024-03-13T11:07:40.684181-06:00',
                         'updated_at': '2024-03-13T11:07:40.777391-06:00', 'is_active': True,
                         'user': {'id': '3f29bdb1-395c-4a29-9c64-5bd79109765c'}, 'tracks_available': False,
                         'image_url': '/static/ranger-black.svg'}, 'state': 'new', 'is_contained_in': [],
         'sort_at': f'{today}T06:22:12.044902-06:00', 'patrol_segments': [], 'geometry': None,
         'updated_at': f'{today}T06:22:12.044902-06:00', 'created_at': f'{today}T06:22:12.046247-06:00',
         'icon_id': '169361d0-62b8-411d-a8e6-019823805016_humanactivity_poaching',
         'event_details': {'animalpoached': 'carcass', 'targetspecies': 'birds.greategret', 'numberofanimalpoached': 1,
                           'updates': []}, 'files': [], 'related_subjects': [], 'event_category': 'smart',
         'url': 'https://gundi-er.pamdas.org/api/v1.0/activity/event/ede43c88-f282-46eb-ae63-227da082c2b4',
         'image_url': 'https://gundi-er.pamdas.org/static/generic-gray.svg',
         'geojson': {'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [-71.261906, -41.145032]},
                     'properties': {'message': '', 'datetime': f'{today}T12:22:11+00:00',
                                    'image': 'https://gundi-er.pamdas.org/static/generic-gray.svg',
                                    'icon': {'iconUrl': 'https://gundi-er.pamdas.org/static/generic-gray.svg',
                                             'iconSize': [25, 25], 'iconAncor': [12, 12], 'popupAncor': [0, -13],
                                             'className': 'dot'}}}, 'is_collection': False, 'updates': [
            {'message': 'Created', 'time': f'{today}T12:22:12.123550+00:00',
             'user': {'username': 'marianom', 'first_name': 'Mariano', 'last_name': 'Martinez',
                      'id': '3f29bdb1-395c-4a29-9c64-5bd79109765c', 'content_type': 'accounts.user'},
             'type': 'add_event'}], 'patrols': []},
        {'id': '5becfebb-1d4d-4096-89f1-737521e23f92', 'location': {'latitude': -41.145088, 'longitude': -71.261973},
         'time': '2024-04-11T16:04:50-06:00', 'end_time': None, 'serial_number': 49571, 'message': '', 'provenance': '',
         'event_type': '169361d0-62b8-411d-a8e6-019823805016_humanactivity_transportation', 'priority': 0,
         'priority_label': 'Gray', 'attributes': {}, 'comment': None, 'title': None,
         'reported_by': {'content_type': 'observations.subject', 'id': 'f9f4a3dd-fae2-4147-8259-0551ff5691e6',
                         'name': 'Mariano Martinez', 'subject_type': 'person', 'subject_subtype': 'ranger',
                         'common_name': None, 'additional': {}, 'created_at': '2024-03-13T11:07:40.684181-06:00',
                         'updated_at': '2024-03-13T11:07:40.777391-06:00', 'is_active': True,
                         'user': {'id': '3f29bdb1-395c-4a29-9c64-5bd79109765c'}, 'tracks_available': False,
                         'image_url': '/static/ranger-black.svg'}, 'state': 'new', 'is_contained_in': [],
         'sort_at': '2024-04-11T16:04:50.943795-06:00', 'patrol_segments': [], 'geometry': None,
         'updated_at': '2024-04-11T16:04:50.943795-06:00', 'created_at': '2024-04-11T16:04:50.944835-06:00',
         'icon_id': '169361d0-62b8-411d-a8e6-019823805016_humanactivity_transportation',
         'event_details': {'updates': []}, 'files': [], 'related_subjects': [], 'event_category': 'smart',
         'url': 'https://gundi-er.pamdas.org/api/v1.0/activity/event/5becfebb-1d4d-4096-89f1-737521e23f92',
         'image_url': 'https://gundi-er.pamdas.org/static/generic-gray.svg',
         'geojson': {'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [-71.261973, -41.145088]},
                     'properties': {'message': '', 'datetime': '2024-04-11T22:04:50+00:00',
                                    'image': 'https://gundi-er.pamdas.org/static/generic-gray.svg',
                                    'icon': {'iconUrl': 'https://gundi-er.pamdas.org/static/generic-gray.svg',
                                             'iconSize': [25, 25], 'iconAncor': [12, 12], 'popupAncor': [0, -13],
                                             'className': 'dot'}}}, 'is_collection': False, 'updates': [
            {'message': 'Created', 'time': '2024-04-11T22:04:50.985980+00:00',
             'user': {'username': 'marianom', 'first_name': 'Mariano', 'last_name': 'Martinez',
                      'id': '3f29bdb1-395c-4a29-9c64-5bd79109765c', 'content_type': 'accounts.user'},
             'type': 'add_event'}], 'patrols': []},
        {'id': 'f7401f43-d10e-4979-8bd9-60c32a4b1c23', 'location': {'latitude': -41.145088, 'longitude': -71.261973},
         'time': '2024-04-11T15:42:22-06:00', 'end_time': None, 'serial_number': 49570, 'message': '', 'provenance': '',
         'event_type': '169361d0-62b8-411d-a8e6-019823805016_features_waterhole', 'priority': 0,
         'priority_label': 'Gray', 'attributes': {}, 'comment': None, 'title': None,
         'reported_by': {'content_type': 'observations.subject', 'id': 'f9f4a3dd-fae2-4147-8259-0551ff5691e6',
                         'name': 'Mariano Martinez', 'subject_type': 'person', 'subject_subtype': 'ranger',
                         'common_name': None, 'additional': {}, 'created_at': '2024-03-13T11:07:40.684181-06:00',
                         'updated_at': '2024-03-13T11:07:40.777391-06:00', 'is_active': True,
                         'user': {'id': '3f29bdb1-395c-4a29-9c64-5bd79109765c'}, 'tracks_available': False,
                         'image_url': '/static/ranger-black.svg'}, 'state': 'new', 'is_contained_in': [],
         'sort_at': '2024-04-11T15:42:22.950275-06:00', 'patrol_segments': [], 'geometry': None,
         'updated_at': '2024-04-11T15:42:22.950275-06:00', 'created_at': '2024-04-11T15:42:22.951102-06:00',
         'icon_id': '169361d0-62b8-411d-a8e6-019823805016_features_waterhole', 'event_details': {'updates': []},
         'files': [], 'related_subjects': [], 'event_category': 'smart',
         'url': 'https://gundi-er.pamdas.org/api/v1.0/activity/event/f7401f43-d10e-4979-8bd9-60c32a4b1c23',
         'image_url': 'https://gundi-er.pamdas.org/static/generic-gray.svg',
         'geojson': {'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [-71.261973, -41.145088]},
                     'properties': {'message': '', 'datetime': '2024-04-11T21:42:22+00:00',
                                    'image': 'https://gundi-er.pamdas.org/static/generic-gray.svg',
                                    'icon': {'iconUrl': 'https://gundi-er.pamdas.org/static/generic-gray.svg',
                                             'iconSize': [25, 25], 'iconAncor': [12, 12], 'popupAncor': [0, -13],
                                             'className': 'dot'}}}, 'is_collection': False, 'updates': [
            {'message': 'Created', 'time': '2024-04-11T21:42:22.961648+00:00',
             'user': {'username': 'marianom', 'first_name': 'Mariano', 'last_name': 'Martinez',
                      'id': '3f29bdb1-395c-4a29-9c64-5bd79109765c', 'content_type': 'accounts.user'},
             'type': 'add_event'}], 'patrols': []},
        {'id': 'bad79581-12d1-48b6-bd26-5f8a0ad97427', 'location': {'latitude': -41.145001, 'longitude': -71.26194},
         'time': '2024-04-11T15:38:00-06:00', 'end_time': None, 'serial_number': 49569, 'message': '', 'provenance': '',
         'event_type': '169361d0-62b8-411d-a8e6-019823805016_animals', 'priority': 0, 'priority_label': 'Gray',
         'attributes': {}, 'comment': None, 'title': None,
         'reported_by': {'content_type': 'observations.subject', 'id': 'f9f4a3dd-fae2-4147-8259-0551ff5691e6',
                         'name': 'Mariano Martinez', 'subject_type': 'person', 'subject_subtype': 'ranger',
                         'common_name': None, 'additional': {}, 'created_at': '2024-03-13T11:07:40.684181-06:00',
                         'updated_at': '2024-03-13T11:07:40.777391-06:00', 'is_active': True,
                         'user': {'id': '3f29bdb1-395c-4a29-9c64-5bd79109765c'}, 'tracks_available': False,
                         'image_url': '/static/ranger-black.svg'}, 'state': 'new', 'is_contained_in': [],
         'sort_at': '2024-04-11T15:38:00.530146-06:00', 'patrol_segments': [], 'geometry': None,
         'updated_at': '2024-04-11T15:38:00.530146-06:00', 'created_at': '2024-04-11T15:38:00.531426-06:00',
         'icon_id': '169361d0-62b8-411d-a8e6-019823805016_animals', 'event_details': {'updates': []}, 'files': [],
         'related_subjects': [], 'event_category': 'smart',
         'url': 'https://gundi-er.pamdas.org/api/v1.0/activity/event/bad79581-12d1-48b6-bd26-5f8a0ad97427',
         'image_url': 'https://gundi-er.pamdas.org/static/generic-gray.svg',
         'geojson': {'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [-71.26194, -41.145001]},
                     'properties': {'message': '', 'datetime': '2024-04-11T21:38:00+00:00',
                                    'image': 'https://gundi-er.pamdas.org/static/generic-gray.svg',
                                    'icon': {'iconUrl': 'https://gundi-er.pamdas.org/static/generic-gray.svg',
                                             'iconSize': [25, 25], 'iconAncor': [12, 12], 'popupAncor': [0, -13],
                                             'className': 'dot'}}}, 'is_collection': False, 'updates': [
            {'message': 'Created', 'time': '2024-04-11T21:38:00.617275+00:00',
             'user': {'username': 'marianom', 'first_name': 'Mariano', 'last_name': 'Martinez',
                      'id': '3f29bdb1-395c-4a29-9c64-5bd79109765c', 'content_type': 'accounts.user'},
             'type': 'add_event'}], 'patrols': []}
    ]


@pytest.fixture
def das_client_patrols_response():
    today = datetime.now().strftime('%Y-%m-%d')
    return [
        {'id': 'd0e3542d-6346-4f5d-9d47-805add57f8be', 'priority': 0, 'state': 'open', 'objective': None,
         'serial_number': 24, 'title': None, 'files': [], 'notes': [], 'patrol_segments': [
            {'id': '159ac2d7-2b49-4435-b18d-1233017c80b7', 'patrol_type': 'routine_patrol',
             'leader': {'content_type': 'observations.subject', 'id': '73624ad7-7337-47bd-9a31-8d6d03eb133e',
                        'name': 'Admin One (SMART)', 'subject_type': 'person', 'subject_subtype': 'ranger',
                        'common_name': None, 'additional': {'ca_uuid': '169361d0-62b8-411d-a8e6-019823805016',
                                                            'smart_member_id': '088da485de3c4175b6eaf645d0ac4796'},
                        'created_at': '2024-03-07T14:59:26.608485-06:00',
                        'updated_at': '2024-03-07T14:59:26.608510-06:00', 'is_active': True, 'user': None,
                        'tracks_available': False, 'image_url': '/static/ranger-black.svg'},
             'scheduled_start': f'{today}T12:09:02.760000-06:00', 'scheduled_end': None,
             'time_range': {'start_time': f'{today}T12:09:13.182000-06:00', 'end_time': None},
             'start_location': {'latitude': 25.46380455676075, 'longitude': -106.17172113020978}, 'end_location': None,
             'events': [], 'image_url': 'https://gundi-er.pamdas.org/static/sprite-src/routine-patrol-icon.svg',
             'icon_id': 'routine-patrol-icon', 'updates': [
                {'message': 'Updated fields: Start Time', 'time': f'{today}T18:09:13.339878+00:00',
                 'user': {'username': 'victorl', 'first_name': 'Victor', 'last_name': 'Lujan',
                          'id': '9f90cd67-c355-4168-9a45-99eec559004c', 'content_type': 'accounts.user'},
                 'type': 'update_segment'}]}], 'updates': [
            {'message': 'Patrol Added', 'time': f'{today}T18:09:11.808969+00:00',
             'user': {'username': 'victorl', 'first_name': 'Victor', 'last_name': 'Lujan',
                      'id': '9f90cd67-c355-4168-9a45-99eec559004c', 'content_type': 'accounts.user'},
             'type': 'add_patrol'}]},
        {'id': 'e541b97f-7936-476f-bbdf-8cbc413af658', 'priority': 0, 'state': 'open', 'objective': None,
         'serial_number': 23, 'title': None, 'files': [], 'notes': [], 'patrol_segments': [
            {'id': '142eca77-79c2-4cc7-acab-728c2ad82989', 'patrol_type': 'routine_patrol',
             'leader': {'content_type': 'observations.subject', 'id': '33458b5b-10df-494a-9d2d-bb808d602de0',
                        'name': 'Antony Lynam (SMART)', 'subject_type': 'person', 'subject_subtype': 'ranger',
                        'common_name': None, 'additional': {'ca_uuid': '169361d0-62b8-411d-a8e6-019823805016',
                                                            'smart_member_id': '9f9cbc580fce4db1ae6a080c8816dcb1'},
                        'created_at': '2024-03-07T14:59:33.833433-06:00',
                        'updated_at': '2024-03-07T14:59:33.833460-06:00', 'is_active': True, 'user': None,
                        'tracks_available': False, 'image_url': '/static/ranger-black.svg'},
             'scheduled_start': f'{today}T11:45:16.796000-06:00', 'scheduled_end': None,
             'time_range': {'start_time': f'{today}T11:47:29.077000-06:00', 'end_time': None},
             'start_location': {'latitude': 25.35092637406109, 'longitude': -106.04704163232911},
             'end_location': None, 'events': [],
             'image_url': 'https://gundi-er.pamdas.org/static/sprite-src/routine-patrol-icon.svg',
             'icon_id': 'routine-patrol-icon', 'updates': [
                {'message': 'Updated fields: Start Time', 'time': f'{today}T17:47:29.571873+00:00',
                 'user': {'username': 'victorl', 'first_name': 'Victor', 'last_name': 'Lujan',
                          'id': '9f90cd67-c355-4168-9a45-99eec559004c', 'content_type': 'accounts.user'},
                 'type': 'update_segment'}]}], 'updates': [
            {'message': 'Patrol Added', 'time': f'{today}T17:45:33.457184+00:00',
             'user': {'username': 'victorl', 'first_name': 'Victor', 'last_name': 'Lujan',
                      'id': '9f90cd67-c355-4168-9a45-99eec559004c', 'content_type': 'accounts.user'},
             'type': 'add_patrol'}]},
        {'id': 'c3c54188-aae5-414f-bf95-ec0500078d2d', 'priority': 0, 'state': 'open', 'objective': None,
         'serial_number': 25, 'title': None, 'files': [], 'notes': [], 'patrol_segments': [
            {'id': 'e36587a7-2fc6-4d75-9a7f-504169e9d926', 'patrol_type': 'routine_patrol',
             'leader': {'content_type': 'observations.subject', 'id': '97ca29f0-f3c0-4693-b1c8-b0d00cc068f1',
                        'name': 'Bos Pin បោះ ពិន (SMART)', 'subject_type': 'person', 'subject_subtype': 'ranger',
                        'common_name': None, 'additional': {'ca_uuid': '169361d0-62b8-411d-a8e6-019823805016',
                                                            'smart_member_id': '788207bc93974cb0a1a445ab232140eb'},
                        'created_at': '2024-03-07T14:59:25.786875-06:00',
                        'updated_at': '2024-03-07T14:59:25.786909-06:00', 'is_active': True, 'user': None,
                        'tracks_available': False, 'image_url': '/static/ranger-black.svg'},
             'scheduled_start': f'{today}T12:09:17.655000-06:00', 'scheduled_end': None,
             'time_range': {'start_time': f'{today}T12:09:30.147000-06:00', 'end_time': None},
             'start_location': {'latitude': 28.01653928410248, 'longitude': -107.91184126931785},
             'end_location': None, 'events': [],
             'image_url': 'https://gundi-er.pamdas.org/static/sprite-src/routine-patrol-icon.svg',
             'icon_id': 'routine-patrol-icon', 'updates': [
                {'message': 'Updated fields: Start Time', 'time': f'{today}T18:09:30.309659+00:00',
                 'user': {'username': 'victorl', 'first_name': 'Victor', 'last_name': 'Lujan',
                          'id': '9f90cd67-c355-4168-9a45-99eec559004c', 'content_type': 'accounts.user'},
                 'type': 'update_segment'}]}], 'updates': [
            {'message': 'Patrol Added', 'time': f'{today}T18:09:28.626462+00:00',
             'user': {'username': 'victorl', 'first_name': 'Victor', 'last_name': 'Lujan',
                      'id': '9f90cd67-c355-4168-9a45-99eec559004c', 'content_type': 'accounts.user'},
             'type': 'add_patrol'}]},
        {'id': 'c423ed79-eaa3-4aad-8ecc-11a5f1fb820c', 'priority': 0, 'state': 'open', 'objective': None,
         'serial_number': 26, 'title': None, 'files': [], 'notes': [], 'patrol_segments': [
            {'id': '527ec2c1-a0f2-40e2-a887-362bcba2e704', 'patrol_type': 'routine_patrol',
             'leader': {'content_type': 'observations.subject', 'id': '97ca29f0-f3c0-4693-b1c8-b0d00cc068f1',
                        'name': 'Bos Pin បោះ ពិន (SMART)', 'subject_type': 'person', 'subject_subtype': 'ranger',
                        'common_name': None, 'additional': {'ca_uuid': '169361d0-62b8-411d-a8e6-019823805016',
                                                            'smart_member_id': '788207bc93974cb0a1a445ab232140eb'},
                        'created_at': '2024-03-07T14:59:25.786875-06:00',
                        'updated_at': '2024-03-07T14:59:25.786909-06:00', 'is_active': True, 'user': None,
                        'tracks_available': False, 'image_url': '/static/ranger-black.svg'},
             'scheduled_start': f'{today}T12:22:37.505000-06:00', 'scheduled_end': None,
             'time_range': {'start_time': f'{today}T12:22:48.829000-06:00', 'end_time': None},
             'start_location': {'latitude': 24.901369994330622, 'longitude': -104.92882719106991},
             'end_location': None, 'events': [],
             'image_url': 'https://gundi-er.pamdas.org/static/sprite-src/routine-patrol-icon.svg',
             'icon_id': 'routine-patrol-icon', 'updates': [
                {'message': 'Updated fields: Start Time', 'time': f'{today}T18:22:49.164268+00:00',
                 'user': {'username': 'victorl', 'first_name': 'Victor', 'last_name': 'Lujan',
                          'id': '9f90cd67-c355-4168-9a45-99eec559004c', 'content_type': 'accounts.user'},
                 'type': 'update_segment'}]}], 'updates': [
            {'message': 'Patrol Added', 'time': f'{today}T18:22:46.466459+00:00',
             'user': {'username': 'victorl', 'first_name': 'Victor', 'last_name': 'Lujan',
                      'id': '9f90cd67-c355-4168-9a45-99eec559004c', 'content_type': 'accounts.user'},
             'type': 'add_patrol'}]},
        {'id': 'dbead27b-0039-4349-9099-ad3c448a1d88', 'priority': 0, 'state': 'open', 'objective': None,
         'serial_number': 27, 'title': None, 'files': [], 'notes': [], 'patrol_segments': [
            {'id': '7b359f9f-8433-42e5-8393-5e1993c98428', 'patrol_type': 'routine_patrol',
             'leader': {'content_type': 'observations.subject', 'id': '90bb173d-9a7b-444a-82ac-41d3e88b931c',
                        'name': 'Drew Cronin (SMART)', 'subject_type': 'person', 'subject_subtype': 'ranger',
                        'common_name': None, 'additional': {'ca_uuid': '169361d0-62b8-411d-a8e6-019823805016',
                                                            'smart_member_id': '6ac37ce1098140c690af85b20dffc791'},
                        'created_at': '2024-03-07T14:59:26.347917-06:00',
                        'updated_at': '2024-03-07T14:59:26.347941-06:00', 'is_active': True, 'user': None,
                        'tracks_available': False, 'image_url': '/static/ranger-black.svg'},
             'scheduled_start': f'{today}T12:26:17.671000-06:00', 'scheduled_end': None,
             'time_range': {'start_time': f'{today}T12:26:32.961000-06:00', 'end_time': None},
             'start_location': {'latitude': 23.31206200043364, 'longitude': -104.43094585906033},
             'end_location': None, 'events': [],
             'image_url': 'https://gundi-er.pamdas.org/static/sprite-src/routine-patrol-icon.svg',
             'icon_id': 'routine-patrol-icon', 'updates': [
                {'message': 'Updated fields: Start Time', 'time': f'{today}T18:26:33.304716+00:00',
                 'user': {'username': 'victorl', 'first_name': 'Victor', 'last_name': 'Lujan',
                          'id': '9f90cd67-c355-4168-9a45-99eec559004c', 'content_type': 'accounts.user'},
                 'type': 'update_segment'}]}], 'updates': [
            {'message': 'Patrol Added', 'time': f'{today}T18:26:31.304513+00:00',
             'user': {'username': 'victorl', 'first_name': 'Victor', 'last_name': 'Lujan',
                      'id': '9f90cd67-c355-4168-9a45-99eec559004c', 'content_type': 'accounts.user'},
             'type': 'add_patrol'}]}
    ]


@pytest.fixture
def das_client_observations_response():
    return []


@pytest.fixture
def mock_das_client(mocker, das_client_events_response, das_client_patrols_response, das_client_observations_response):
    mock_client = mocker.MagicMock()
    mock_client.get_events.return_value = das_client_events_response
    mock_client.get_patrols.return_value = das_client_patrols_response
    mock_client.get_subject_observations.return_value = das_client_observations_response
    return mock_client


@pytest.fixture
def mock_smart_client(mocker):
    mock_client = mocker.MagicMock()
    mock_client.version = '7.5.7'
    return mock_client


@pytest.fixture
def mock_pubsub_publisher(mocker):
    mock_client = mocker.MagicMock()
    return mock_client


@pytest.fixture
def mock_last_poll(mocker):
    mock_last_poll = mocker.MagicMock()
    mock_last_poll.return_value.patrol_last_poll_at = None
    return mock_last_poll

@pytest.fixture
def eula_v1():
    return EULA.objects.create(
        version="Gundi_EULA_2024-05-03",
        eula_url="https://projectgundi.org/Legal-Pages/User-Agreement"
    )

@pytest.fixture
def eula_v2():
    return EULA.objects.create(
        version="Gundi_EULA_2024-05-05",
        eula_url="https://projectgundi.org/Legal-Pages/User-Agreement"
    )

@pytest.fixture
def dispatcher_source_release_1():
    return "release-20231218"


@pytest.fixture
def dispatcher_source_release_2():
    return "release-20240510"


@pytest.fixture
def outbound_integrations_list_er(
        mocker, settings, mock_get_dispatcher_defaults_from_gcp_secrets,
        organization, legacy_integration_type_earthranger
):
    # Override settings so a DispatcherDeployment is created
    settings.GCP_ENVIRONMENT_ENABLED = True
    # Mock the task to trigger the dispatcher deployment
    mocked_deployment_task = mocker.MagicMock()
    mocker.patch(
        "deployments.models.deploy_serverless_dispatcher", mocked_deployment_task
    )
    # Mock calls to external services
    mocker.patch("integrations.models.v1.models.get_dispatcher_defaults_from_gcp_secrets", mock_get_dispatcher_defaults_from_gcp_secrets)
    # Patch on_commit to execute the function immediately
    mocker.patch("deployments.models.transaction.on_commit", lambda fn: fn())
    mocker.patch("integrations.models.v1.models.transaction.on_commit", lambda fn: fn())
    integrations = []
    for i in range(5):
        integration = OutboundIntegrationConfiguration.objects.create(
            name=f"EarthRanger Integration v1 Test {i}",
            endpoint=f"https://test{i}.fakepamdas.org",
            type=legacy_integration_type_earthranger,
            owner=organization
        )
        integrations.append(integration)
    return integrations


@pytest.fixture
def outbound_integrations_list_smart(
        mocker, settings, mock_get_dispatcher_defaults_from_gcp_secrets_smart,
        organization, legacy_integration_type_smart
):
    # Override settings so a DispatcherDeployment is created
    settings.GCP_ENVIRONMENT_ENABLED = True
    # Mock the task to trigger the dispatcher deployment
    mocked_deployment_task = mocker.MagicMock()
    mocker.patch(
        "deployments.models.deploy_serverless_dispatcher", mocked_deployment_task
    )
    # Mock calls to external services
    mocker.patch(
        "integrations.models.v1.models.get_dispatcher_defaults_from_gcp_secrets",
        mock_get_dispatcher_defaults_from_gcp_secrets_smart
    )
    # Patch on_commit to execute the function immediately
    mocker.patch("deployments.models.transaction.on_commit", lambda fn: fn())
    mocker.patch("integrations.models.v1.models.transaction.on_commit", lambda fn: fn())
    integrations = []
    for i in range(5):
        integration = OutboundIntegrationConfiguration.objects.create(
            name=f"SMART Integration v1 Test {i}",
            endpoint=f"https://test{i}.fakesmartconnect.com",
            type=legacy_integration_type_smart,
            owner=organization
        )
        integrations.append(integration)
    return integrations


@pytest.fixture
def outbound_integrations_list_wpswatch(
        mocker, settings, mock_get_dispatcher_defaults_from_gcp_secrets_wps_watch,
        organization, legacy_integration_type_wpswatch
):
    # Override settings so a DispatcherDeployment is created
    settings.GCP_ENVIRONMENT_ENABLED = True
    # Mock the task to trigger the dispatcher deployment
    mocked_deployment_task = mocker.MagicMock()
    mocker.patch(
        "deployments.models.deploy_serverless_dispatcher", mocked_deployment_task
    )
    # Mock calls to external services
    mocker.patch(
        "integrations.models.v1.models.get_dispatcher_defaults_from_gcp_secrets",
        mock_get_dispatcher_defaults_from_gcp_secrets_wps_watch
    )
    # Patch on_commit to execute the function immediately
    mocker.patch("deployments.models.transaction.on_commit", lambda fn: fn())
    mocker.patch("integrations.models.v1.models.transaction.on_commit", lambda fn: fn())
    integrations = []
    for i in range(5):
        integration = OutboundIntegrationConfiguration.objects.create(
            name=f"WPS Watch Integration v1 Test {i}",
            endpoint=f"https://test{i}.fakeswpswatch.com",
            type=legacy_integration_type_wpswatch,
            owner=organization
        )
        integrations.append(integration)
    return integrations
