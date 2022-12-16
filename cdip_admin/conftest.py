import base64
import pytest
import random
from typing import NamedTuple, Any
from django.contrib.auth.models import User, Group
from rest_framework.utils import json
from rest_framework.test import APIClient
from accounts.models import AccountProfile, AccountProfileOrganization
from core.enums import DjangoGroups
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
)
from organizations.models import Organization


@pytest.fixture
def api_client():
    """
    Use this client to test API endpoints.
    It'll take care of dict-to-json serialization among other things.
    https://www.django-rest-framework.org/api-guide/testing/#apiclient
    """
    return APIClient()


@pytest.fixture
def get_device_id():
    """
    A helper function that generates a ramdom alphanumeric id, to be used as external_id of Devices
    """

    def _make_device_id():
        return "".join(random.sample([chr(x) for x in range(97, 97 + 26)], 12))

    return _make_device_id


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
