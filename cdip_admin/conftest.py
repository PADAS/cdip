import base64
import pytest
import random
from typing import NamedTuple, Any
from django.contrib.auth.models import User, Group
from rest_framework.utils import json
from rest_framework.test import APIClient
from accounts.models import AccountProfile, AccountProfileOrganization
from core.enums import DjangoGroups, RoleChoices
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
    SourceConfiguration, ensure_default_route, RouteConfiguration, GundiTrace
)
from organizations.models import Organization
from pathlib import Path
from google.cloud import pubsub_v1


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
        is_superuser=True
    )
    return user


@pytest.fixture
def org_admin_user(organization, org_members_group):
    email = "orgadmin@gundiservice.org"
    user, _ = User.objects.get_or_create(
        username=email,
        email=email,
        first_name="Caroline",
        last_name="West"
    )
    user.groups.add(org_members_group.id)
    account_profile, _ = AccountProfile.objects.get_or_create(
        user_id=user.id,
    )
    AccountProfileOrganization.objects.get_or_create(
        accountprofile_id=account_profile.id,
        organization_id=organization.id,
        role=RoleChoices.ADMIN.value
    )
    return user


@pytest.fixture
def org_admin_user_2(other_organization, org_members_group):
    email = "orgadmin2@gundiservice.org"
    user, _ = User.objects.get_or_create(
        username=email,
        email=email,
        first_name="Jack",
        last_name="Pearson"
    )
    user.groups.add(org_members_group.id)
    account_profile, _ = AccountProfile.objects.get_or_create(
        user_id=user.id,
    )
    AccountProfileOrganization.objects.get_or_create(
        accountprofile_id=account_profile.id,
        organization_id=other_organization.id,
        role=RoleChoices.ADMIN.value
    )
    return user


@pytest.fixture
def org_viewer_user(organization, org_members_group):
    email = "orgviewer@gundiservice.org"
    user, _ = User.objects.get_or_create(
        username=email,
        email=email,
        first_name="Colin",
        last_name="Gray"
    )
    user.groups.add(org_members_group.id)
    account_profile, _ = AccountProfile.objects.get_or_create(
        user_id=user.id,
    )
    AccountProfileOrganization.objects.get_or_create(
        accountprofile_id=account_profile.id,
        organization_id=organization.id,
        role=RoleChoices.VIEWER.value
    )
    return user


@pytest.fixture
def org_viewer_user_2(other_organization, org_members_group):
    email = "orgaviewer2@gundiservice.org"
    user, _ = User.objects.get_or_create(
        username=email,
        email=email,
        first_name="Phill",
        last_name="Wane"
    )
    user.groups.add(org_members_group.id)
    account_profile, _ = AccountProfile.objects.get_or_create(
        user_id=user.id,
    )
    AccountProfileOrganization.objects.get_or_create(
        accountprofile_id=account_profile.id,
        organization_id=other_organization.id,
        role=RoleChoices.VIEWER.value
    )
    return user


@pytest.fixture
def new_random_user(new_user_email, org_members_group):
    def _make_random_user():
        email = new_user_email()
        user = User.objects.create(
            username=email,
            email=email
        )
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
        description="A reserve in Africa"
    )
    return org


@pytest.fixture
def other_organization(get_random_id):
    org, _ = Organization.objects.get_or_create(
        name=f"Test Organization EWT {get_random_id()}",
        description="A different reserve in Africa"
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
            role=RoleChoices.VIEWER.value
        )
        members_apo_list.append(apo)
    return members_apo_list


@pytest.fixture
def organizations_list(get_random_id, organization):
    orgs = [organization]  # Organization having an admin and a viewer
    for i in range(10):
        org, _ = Organization.objects.get_or_create(
            name=f"Test Organization {get_random_id()}",
            description="A reserve in Africa"
        )
        orgs.append(org)
    return orgs


@pytest.fixture
def org_members_group():
    group, _ = Group.objects.get_or_create(
        name=DjangoGroups.ORGANIZATION_MEMBER.value
    )
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
        description="Standard inbound integration type for pulling data from Lotek API."
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
            "required": [
                "username",
                "password"
            ],
            "properties": {
                "password": {
                    "type": "string"
                },
                "username": {
                    "type": "string"
                }
            }
        }
    )


@pytest.fixture
def lotek_action_pull_positions(integration_type_lotek):
    return IntegrationAction.objects.create(
        integration_type=integration_type_lotek,
        type=IntegrationAction.ActionTypes.PULL_DATA,
        name="Pull Positions",
        value="pull_positions",
        description="Pull Tracking data from Move Bank API",
        schema={
            "type": "object",
            "required": [
                "start_time"
            ],
            "properties": {
                "max_records_per_individual": {
                    "type": "string"
                }
            }
        }
    )


@pytest.fixture
def integration_type_movebank():
    return IntegrationType.objects.create(
        name="Move Bank",
        value="movebank",
        description="Standard Integration type for Move Bank API."
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
            "required": [
                "email",
                "password"
            ],
            "properties": {
                "password": {
                    "type": "string"
                },
                "email": {
                    "type": "string"
                }
            }
        }
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
            "required": [
                "max_records_per_individual"
            ],
            "properties": {
                "max_records_per_individual": {
                    "type": "integer"
                }
            }
        }
    )


@pytest.fixture
def integration_type_er():
    # Create an integration type for Earth Ranger
    integration_type = IntegrationType.objects.create(
        name="EarthRanger",
        value="earth_ranger",
        description="Standard type for distributing data to EarthRanger sites."
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
            "required": [
                "username",
                "password"
            ],
            "properties": {
                "password": {
                    "type": "string"
                },
                "username": {
                    "type": "string"
                }
            }
        }
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
            "required": [
                "sensor_type"
            ],
            "properties": {
                "sensor_type": {
                    "type": "string"
                }
            }
        }
    )


@pytest.fixture
def er_action_push_events(integration_type_er):
    return IntegrationAction.objects.create(
        integration_type=integration_type_er,
        type=IntegrationAction.ActionTypes.PUSH_DATA,
        name="Push Events",
        value="push_events",
        description="Push Event data to Earth Ranger API"
    )


@pytest.fixture
def er_action_pull_positions(integration_type_er):
    return IntegrationAction.objects.create(
        integration_type=integration_type_er,
        type=IntegrationAction.ActionTypes.PULL_DATA,
        name="Pull Positions",
        value="pull_positions",
        description="Pull Tracking data from Earth Ranger API"
    )


@pytest.fixture
def er_action_pull_events(integration_type_er):
    return IntegrationAction.objects.create(
        integration_type=integration_type_er,
        type=IntegrationAction.ActionTypes.PULL_DATA,
        name="Pull Events",
        value="pull_events",
        description="Pull Event data from Earth Ranger API"
    )


@pytest.fixture
def integration_type_smart():
    return IntegrationType.objects.create(
        name="SMART",
        value="smart",
        description="Standard integration type for pushing data to SMART Cloud."
    )


@pytest.fixture
def smart_action_push_events(integration_type_smart):
    return IntegrationAction.objects.create(
        integration_type=integration_type_smart,
        type=IntegrationAction.ActionTypes.PUSH_DATA,
        name="Push Events",
        value="push_events",
        description="Push Event data to SMART Cloud API"
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
            "required": [
                "api_key"
            ],
            "properties": {
                "api_key": {
                    "type": "string"
                }
            }
        }
    )


@pytest.fixture
def smart_integration(
        organization, other_organization, integration_type_smart, get_random_id,
        smart_action_auth, smart_action_push_events
):
    # Create the integration
    site_url = f"{get_random_id()}.smart.wps.org"
    integration, _ = Integration.objects.get_or_create(
        type=integration_type_smart,
        name=f"SMART Site {get_random_id()}",
        owner=other_organization,
        base_url=site_url
    )
    # Configure actions
    IntegrationConfiguration.objects.create(
        integration=integration,
        action=smart_action_auth,
        data={
            "api_key": f"SMART-{get_random_id()}-KEY",
        }
    )
    ensure_default_route(integration=integration)
    return integration


@pytest.fixture
def provider_lotek_panthera(
        get_random_id, organization, integration_type_lotek, lotek_action_auth, lotek_action_pull_positions
):
    provider, _ = Integration.objects.get_or_create(
        type=integration_type_lotek,
        name=f"Lotek Provider For Panthera {get_random_id()}",
        owner=organization,
        base_url=f"api.test.lotek.com"
    )
    # Configure actions
    IntegrationConfiguration.objects.create(
        integration=provider,
        action=lotek_action_auth,
        data={
            "username": f"user-{get_random_id()}@lotek.com",
            "password": f"passwd-{get_random_id()}"
        }
    )
    IntegrationConfiguration.objects.create(
        integration=provider,
        action=lotek_action_pull_positions,
        data={
            "start_time": "2023-01-01T00:00:00Z"
        }
    )
    ensure_default_route(integration=provider)
    return provider


@pytest.fixture
def provider_movebank_ewt(
        get_random_id, other_organization, integration_type_movebank, mb_action_auth, mb_action_pull_positions
):
    provider, _ = Integration.objects.get_or_create(
        type=integration_type_movebank,
        name=f"Movebank Provider For EWT {get_random_id()}",
        owner=other_organization,
        base_url=f"https://api.test.movebank.com"
    )
    # Configure actions
    IntegrationConfiguration.objects.create(
        integration=provider,
        action=mb_action_auth,
        data={
            "email": f"user-{get_random_id()}@movebank.com",
            "password": f"passwd-{get_random_id()}"
        }
    )
    IntegrationConfiguration.objects.create(
        integration=provider,
        action=mb_action_pull_positions,
        data={
            "max_records_per_individual": 20000
        }
    )
    ensure_default_route(integration=provider)
    return provider


@pytest.fixture
def integrations_list(
        organization, other_organization, integration_type_er, get_random_id,
        er_action_auth, er_action_pull_positions, er_action_pull_events, er_action_push_positions, er_action_push_events
):
    integrations = []
    for i in range(10):
        # Create the integration
        site_url = f"{get_random_id()}.pamdas.org"
        integration, _ = Integration.objects.get_or_create(
            type=integration_type_er,
            name=f"ER Site {get_random_id()}",
            owner=organization if i < 5 else other_organization,
            base_url=site_url
        )
        # Configure actions
        IntegrationConfiguration.objects.create(
            integration=integration,
            action=er_action_auth,
            data={
                "username": f"eruser-{get_random_id()}",
                "password": f"passwd-{get_random_id()}"
            }
        )
        IntegrationConfiguration.objects.create(
            integration=integration,
            action=er_action_push_positions,
            data={
                "sensor_type": "collar"
            }
        )
        IntegrationConfiguration.objects.create(
            integration=integration,
            action=er_action_pull_positions
        )
        IntegrationConfiguration.objects.create(
            integration=integration,
            action=er_action_push_events
        )
        IntegrationConfiguration.objects.create(
            integration=integration,
            action=er_action_pull_events
        )
        integrations.append(integration)
        ensure_default_route(integration=integration)
    return integrations


@pytest.fixture
def make_random_sources(get_random_id):
    def _make_devices(provider, qty):
        sources = []
        configuration = SourceConfiguration.objects.create(
            name="Report every 10 minutes",
            data={
                "report_every": "10min"
            }
        )
        for i in range(qty):
            source, _ = Source.objects.get_or_create(
                external_id=f"device-{get_random_id()}",
                integration=provider
            )
            # Add a device state and a device configuration in some of them
            if i % 2:
                source.configuration = configuration
                source.save()
            else:
                SourceState.objects.create(
                    source=source,
                    data={
                        "last_data_received": "2023-05-17T09:52:13"
                    }
                )
            sources.append(source)
        return sources

    return _make_devices


@pytest.fixture
def lotek_sources(get_random_id, organization, provider_lotek_panthera, make_random_sources):
    return make_random_sources(provider=provider_lotek_panthera, qty=5)


@pytest.fixture
def movebank_sources(get_random_id, organization, provider_movebank_ewt, make_random_sources):
    return make_random_sources(provider=provider_movebank_ewt, qty=3)


@pytest.fixture
def route_1(get_random_id, organization, lotek_sources, provider_lotek_panthera, integrations_list):
    rule, _ = Route.objects.get_or_create(
        name=f"Device Set to multiple destinations",
        owner=organization,
    )
    rule.data_providers.add(provider_lotek_panthera)
    rule.destinations.add(*integrations_list)
    # Filter data coming only from a subset of sources
    SourceFilter.objects.create(
        type=SourceFilter.SourceFilterTypes.SOURCE_LIST,
        name="Panthera Male Pumas",
        description="Select collars on male pumas in panthera reserve",
        order_number=1,
        selector=ListFilter(
            ids=[d.external_id for d in lotek_sources]
        ).dict(),
        routing_rule=rule
    )
    return rule


@pytest.fixture
def er_route_configuration_elephants():
    route_config = RouteConfiguration.objects.create(
        name="Set Elephant Subject Type",
        data={
            "subject_type": "elephant"
        }
    )
    return route_config


@pytest.fixture
def er_route_configuration_rangers():
    route_config = RouteConfiguration.objects.create(
        name="Set Ranger Subject Type",
        data={
            "subject_type": "ranger"
        }
    )
    return route_config


@pytest.fixture
def smart_route_configuration():
    route_config = RouteConfiguration.objects.create(
        name="Set Ranger Subject Type",
        data={
            "ca_uuids": [
                "8f7fbe1b-121a-4ef4-bda8-14f5581e44cf"
            ],
            "transformation_rules": {
                "attribute_map": [],
                "category_map": []
            },
            "version": "7.5.6"
        }
    )
    return route_config


@pytest.fixture
def route_2(
        get_random_id, other_organization, movebank_sources, provider_movebank_ewt,
        integrations_list, er_route_configuration_elephants
):
    route, _ = Route.objects.get_or_create(
        name=f"Device Set to single destination",
        owner=other_organization,
    )
    route.data_providers.add(provider_movebank_ewt)
    route.destinations.add(integrations_list[5])
    # Filter data coming only from a subset of sources
    SourceFilter.objects.create(
        type=SourceFilter.SourceFilterTypes.SOURCE_LIST,
        name="EWT Baby Elephants",
        description="Select collars on baby elephants in EWT reserve",
        order_number=1,
        selector=ListFilter(
            ids=[d.external_id for d in movebank_sources]
        ).dict(),
        routing_rule=route
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
        description="Standard type Trap Tagger Integration"
    )
    return integration_type


@pytest.fixture
def provider_trap_tagger(
        get_random_id, other_organization, integration_type_trap_tagger,
):
    provider, _ = Integration.objects.get_or_create(
        type=integration_type_trap_tagger,
        name=f"Trap Tagger Provider {get_random_id()}",
        owner=other_organization,
        base_url=f"https://api.test.traptagger.com"
    )
    ensure_default_route(integration=provider)
    return provider


@pytest.fixture
def keyauth_headers_trap_tagger(provider_trap_tagger):
    return {
        "HTTP_X_CONSUMER_USERNAME": f"integration:{str(provider_trap_tagger.id)}"
    }


@pytest.fixture
def mock_get_publisher(mocker):
    return mocker.MagicMock()


@pytest.fixture
def mock_deduplication(mocker):
    mock_func = mocker.MagicMock()
    mock_func.return_value = False
    return mock_func


@pytest.fixture
def leopard_image_file():
    file_path = Path(__file__).resolve().parent.joinpath(
        "api/v2/tests/images/2023-07-05-1358_leopard.jpg"
    )
    return open(file_path, "rb")


@pytest.fixture
def wilddog_image_file():
    file_path = Path(__file__).resolve().parent.joinpath(
        "api/v2/tests/images/2023-07-05-1358_wilddog.jpg"
    )
    return open(file_path, "rb")


@pytest.fixture
def trap_tagger_event_trace(provider_trap_tagger):
    trace = GundiTrace(
        # We save only IDs, no sensitive data is saved
        data_provider=provider_trap_tagger,
        object_type="ev",
        # Other fields are filled in later by the routing services
    )
    trace.save()
    return trace


@pytest.fixture
def mock_cloud_storage(mocker):
    mock_cloud_storage = mocker.MagicMock()
    mock_cloud_storage.save.return_value = "file.jpg"
    return mock_cloud_storage


@pytest.fixture
def trap_tagger_observation_delivered_event(mocker, trap_tagger_event_trace, integrations_list):
    message = mocker.MagicMock()
    event_dict = {
        "event_id": "605535df-1b9b-412b-9fd5-e29b09582999", "timestamp": "2023-07-11 18:19:19.215459+00:00",
        "schema_version": "v1",
        "event_type": "ObservationDelivered",
        "payload": {
            "gundi_id": str(trap_tagger_event_trace.object_id),
            "related_to": None,
            "external_id": "35983ced-1216-4d43-81da-01ee90ba9b80",
            "data_provider_id": str(trap_tagger_event_trace.data_provider.id),
            "destination_id":  str(integrations_list[0].id),
            "delivered_at": "2023-07-11 18:19:19.215015+00:00"
        }
    }
    data_bytes = json.dumps(event_dict).encode('utf-8')
    message.data = data_bytes
    return message


@pytest.fixture
def trap_tagger_observation_delivered_event_two(mocker, trap_tagger_event_trace, integrations_list):
    message = mocker.MagicMock()
    event_dict = {
        "event_id": "505535df-1b9b-412b-9fd5-e29b09582910", "timestamp": "2023-07-11 18:19:19.215459+00:00",
        "schema_version": "v1",
        "event_type": "ObservationDelivered",
        "payload": {
            "gundi_id": str(trap_tagger_event_trace.object_id),
            "related_to": None,
            "external_id": "45983ced-1216-4d43-81da-01ee90ba9b81",
            "data_provider_id": str(trap_tagger_event_trace.data_provider.id),
            "destination_id":  str(integrations_list[1].id),
            "delivered_at": "2023-07-11 18:19:19.215015+00:00"
        }
    }
    data_bytes = json.dumps(event_dict).encode('utf-8')
    message.data = data_bytes
    return message


@pytest.fixture
def trap_tagger_observation_delivery_failed_event(mocker, trap_tagger_event_trace, integrations_list):
    message = mocker.MagicMock()
    event_dict = {
        "event_id": "605535df-1b9b-412b-9fd5-e29b09582999", "timestamp": "2023-07-11 18:19:19.215459+00:00",
        "schema_version": "v1",
        "event_type": "ObservationDeliveryFailed",
        "payload": {
            "gundi_id": str(trap_tagger_event_trace.object_id),
            "related_to": None,
            "data_provider_id": str(trap_tagger_event_trace.data_provider.id),
            "destination_id":  str(integrations_list[0].id),
            "delivered_at": "2023-07-11 18:19:19.215015+00:00"
        }
    }
    data_bytes = json.dumps(event_dict).encode('utf-8')
    message.data = data_bytes
    return message


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
        configuration_schema={
            "type": "object",
            "keys": {
                "test": {
                    "type": "string"
                }
            }
        }
    )

    iit4 = InboundIntegrationType.objects.create(
        name="Inbound Type 4",
        slug="inbound-type-four",
        description="Some integration type.",
        configuration_schema={
            "type": "object",
            "keys": {
                "site_name": {
                    "type": "string"
                },
                "email": {
                    "type": "string",
                    "format": "email"
                },
                "password": {
                    "type": "string",
                    "format": "password"
                }
            }
        }
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
        configuration_schema={
            "type": "object",
            "keys": {
                "test": {
                    "type": "string"
                }
            }
        }
    )

    oit4 = OutboundIntegrationType.objects.create(
        name="Outbound Type 4",
        slug="outbound-type-four",
        description="Some integration type.",
        configuration_schema={
            "type": "object",
            "keys": {
                "site_name": {
                    "type": "string"
                },
                "email": {
                    "type": "string",
                    "format": "email"
                },
                "password": {
                    "type": "string",
                    "format": "password"
                }
            }
        }
    )

    oit_smart_connect = OutboundIntegrationType.objects.create(
        name="Smart Connect",
        slug='smart_connect',
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
        configuration_schema={
            "type": "object",
            "keys": {
                "test": {
                    "type": "string"
                }
            }
        }
    )

    bit3 = BridgeIntegrationType.objects.create(
        name="Bridge Type 3",
        slug="bridge-type-three",
        description="Bridge integration type 3.",
        configuration_schema={
            "type": "object",
            "keys": {
                "site_name": {
                    "type": "string"
                },
                "email": {
                    "type": "string",
                    "format": "email"
                },
                "password": {
                    "type": "string",
                    "format": "password"
                }
            }
        }
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
        type=iit3, name="Inbound Configuration 4", owner=org2, enabled=False,
        state={}
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
        type=oit4, name="Outbound Configuration 4", owner=org2, enabled=False,
        state={}
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
        type=bit3, name="Bridge Integration 5", owner=org2, enabled=False,
        additional={"site_name": "foo"}
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
