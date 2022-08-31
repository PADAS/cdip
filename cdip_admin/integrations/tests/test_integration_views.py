from django.http import QueryDict
from django.urls import reverse
from rest_framework.utils import json

from accounts.models import AccountProfile, AccountProfileOrganization
from conftest import setup_account_profile_mapping
from core.enums import DjangoGroups, RoleChoices
from integrations import models
from integrations.models import (
    InboundIntegrationType,
    InboundIntegrationConfiguration,
    OutboundIntegrationConfiguration,
    OutboundIntegrationType,
    Device,
    DeviceGroup,
)
from organizations.models import Organization

# Inbound Integration Tests
def test_get_inbound_integration_type_list_global_admin(client, global_admin_user):

    client.force_login(global_admin_user.user)

    response = client.get(
        reverse("inboundintegrationtype_list"),
        HTTP_X_USERINFO=global_admin_user.user_info,
    )

    assert response.status_code == 200

    response = response.json()

    assert len(response) == InboundIntegrationType.objects.count()


def test_get_inbound_integration_type_list_organization_member(
    client, organization_member_user
):

    client.force_login(organization_member_user.user)

    response = client.get(
        reverse("inboundintegrationtype_list"),
        HTTP_X_USERINFO=organization_member_user.user_info,
    )

    assert response.status_code == 200

    response = response.json()

    assert len(response) == InboundIntegrationType.objects.count()


def test_get_inbound_integration_type_detail_global_admin(
    client, global_admin_user, setup_data
):

    iit = setup_data["iit1"]

    client.force_login(global_admin_user.user)

    response = client.get(
        reverse("inbound_integration_type_detail", kwargs={"module_id": iit.id}),
        HTTP_X_USERINFO=global_admin_user.user_info,
    )

    assert response.status_code == 200

    response.context["module"].id == iit.id


def test_get_inbound_integration_type_detail_organization_member(
    client, organization_member_user, setup_data
):

    iit = setup_data["iit1"]

    client.force_login(organization_member_user.user)

    response = client.get(
        reverse("inbound_integration_type_detail", kwargs={"module_id": iit.id}),
        HTTP_X_USERINFO=organization_member_user.user_info,
    )

    assert response.status_code == 200

    response.context["module"].id == iit.id


def test_get_inbound_integration_configuration_list_global_admin(
    client, global_admin_user
):

    client.force_login(global_admin_user.user)

    response = client.get(
        reverse("inbound_integration_configuration_list"),
        HTTP_X_USERINFO=global_admin_user.user_info,
    )

    assert response.status_code == 200

    # confirm result set is unfiltered
    assert list(response.context["inboundintegrationconfiguration_list"]) == list(
        InboundIntegrationConfiguration.objects.all()
    )


def test_get_inbound_integration_configuration_list_organization_member_viewer(
    client, organization_member_user, setup_data
):
    org1 = setup_data["org1"]

    account_profile_mapping = {(organization_member_user.user, org1, RoleChoices.ADMIN)}
    setup_account_profile_mapping(account_profile_mapping)

    client.force_login(organization_member_user.user)

    response = client.get(
        reverse("inbound_integration_configuration_list"),
        follow=True,
        HTTP_X_USERINFO=organization_member_user.user_info,
    )

    assert response.status_code == 200

    # confirm result set is filtered queryset based on organization profile
    assert list(response.context["inboundintegrationconfiguration_list"]) == list(
        InboundIntegrationConfiguration.objects.filter(owner=org1)
    )


def test_get_inbound_integration_configurations_detail_organization_member_hybrid(
    client, organization_member_user, setup_data
):

    org1 = setup_data["org1"]
    org2 = setup_data["org2"]
    ii = setup_data["ii1"]
    o_ii = setup_data["ii2"]

    account_profile_mapping = {
        (organization_member_user.user, org1, RoleChoices.VIEWER),
        (organization_member_user.user, org2, RoleChoices.ADMIN),
    }
    setup_account_profile_mapping(account_profile_mapping)

    client.force_login(organization_member_user.user)

    # Get inbound integration configuration detail
    response = client.get(
        reverse("inbound_integration_configuration_detail", kwargs={"id": ii.id}),
        HTTP_X_USERINFO=organization_member_user.user_info,
    )

    # confirm viewer role passes object permission check
    assert response.status_code == 200

    assert response.context["module"].id == ii.id

    # Get inbound integration configuration detail for other type
    response = client.get(
        reverse("inbound_integration_configuration_detail", kwargs={"id": o_ii.id}),
        HTTP_X_USERINFO=organization_member_user.user_info,
    )

    # confirm admin role passes object permission check
    assert response.status_code == 200

    assert response.context["module"].id == o_ii.id


# TODO: InboundIntegrationConfigurationAddView

# TODO: InboundIntegrationConfigurationUpdateView

# Outbound Integration Tests
def test_get_outbound_integration_type_list_global_admin(client, global_admin_user):

    client.force_login(global_admin_user.user)

    response = client.get(
        reverse("outboundintegrationtype_list"),
        HTTP_X_USERINFO=global_admin_user.user_info,
    )

    assert response.status_code == 200

    response = response.json()

    assert len(response) == OutboundIntegrationType.objects.count()


def test_get_outbound_integration_type_list_organization_member(
    client, organization_member_user
):

    client.force_login(organization_member_user.user)

    response = client.get(
        reverse("outboundintegrationtype_list"),
        HTTP_X_USERINFO=organization_member_user.user_info,
    )

    assert response.status_code == 200

    response = response.json()

    assert len(response) == OutboundIntegrationType.objects.count()


def test_get_outbound_integration_type_detail_global_admin(
    client, global_admin_user, setup_data
):

    oit = setup_data["oit1"]

    client.force_login(global_admin_user.user)

    response = client.get(
        reverse("outbound_integration_type_detail", kwargs={"module_id": oit.id}),
        HTTP_X_USERINFO=global_admin_user.user_info,
    )

    assert response.status_code == 200

    response.context["module"].id == oit.id


def test_get_outbound_integration_type_detail_organization_member(
    client, organization_member_user, setup_data
):

    oit = setup_data["oit1"]

    client.force_login(organization_member_user.user)

    response = client.get(
        reverse("outbound_integration_type_detail", kwargs={"module_id": oit.id}),
        HTTP_X_USERINFO=organization_member_user.user_info,
    )

    assert response.status_code == 200

    response.context["module"].id == oit.id


def test_get_outbound_integration_configuration_list_global_admin(
    client, global_admin_user
):

    client.force_login(global_admin_user.user)

    response = client.get(
        reverse("outbound_integration_configuration_list"),
        HTTP_X_USERINFO=global_admin_user.user_info,
    )

    assert response.status_code == 200

    # confirm result set is unfiltered
    assert list(response.context["outboundintegrationconfiguration_list"]) == list(
        OutboundIntegrationConfiguration.objects.all()
    )


def test_get_outbound_integration_configuration_list_organization_member_viewer(
    client, organization_member_user, setup_data
):
    org1 = setup_data["org1"]

    account_profile_mapping = {
        (organization_member_user.user, org1, RoleChoices.VIEWER)
    }
    setup_account_profile_mapping(account_profile_mapping)

    client.force_login(organization_member_user.user)

    response = client.get(
        reverse("outbound_integration_configuration_list"),
        follow=True,
        HTTP_X_USERINFO=organization_member_user.user_info,
    )

    assert response.status_code == 200

    # confirm result set is filtered queryset based on organization profile
    assert list(response.context["outboundintegrationconfiguration_list"]) == list(
        OutboundIntegrationConfiguration.objects.filter(owner=org1)
    )


# TODO: Get Post Working
def test_add_outbound_integration_configuration_organization_member_hybrid(
    client, organization_member_user, setup_data
):
    org1 = setup_data["org1"]
    org2 = setup_data["org2"]
    oit = setup_data["oit1"]

    account_profile_mapping = {
        (organization_member_user.user, org1, RoleChoices.VIEWER),
        (organization_member_user.user, org2, RoleChoices.ADMIN),
    }
    setup_account_profile_mapping(account_profile_mapping)

    client.force_login(organization_member_user.user)

    response = client.get(
        reverse("outbound_integration_configuration_add"),
        follow=True,
        HTTP_X_USERINFO=organization_member_user.user_info,
    )

    assert response.status_code == 200

    # confirm result set is filtered queryset based on organization profile
    assert list(response.context["form"].fields["owner"].queryset) == list(
        Organization.objects.filter(id=org2.id)
    )

    oi = models.OutboundIntegrationConfiguration(
        type=oit, owner=org2, name="Add Outbound Test"
    )

    oi_request_post = {
        "type": str(oit.id),
        "owner": str(org2.id),
        "name": "Test Add Outbound",
        "state": "null",
        "endpoint": "",
        "login": "",
        "password": "",
        "token": "",
        "additional": "{}",
        "initial-additional": "{}",
        "enabled": "on",
    }

    query_dict = QueryDict("", mutable=True)
    query_dict.update(oi_request_post)

    response = client.post(
        reverse("outbound_integration_configuration_add"),
        follow=True,
        data=query_dict,
        HTTP_X_USERINFO=organization_member_user.user_info,
    )

    # assert response.status_code == 200
    #
    # assert OutboundIntegrationConfiguration.objects.filter(name=oi.name).exists()


# TODO: OutboundIntegrationConfigurationUpdateView

# Device Tests


def test_get_device_detail_global_admin(client, global_admin_user, setup_data):

    d = setup_data["d1"]

    client.force_login(global_admin_user.user)

    response = client.get(
        reverse("device_detail", kwargs={"module_id": d.id}),
        HTTP_X_USERINFO=global_admin_user.user_info,
    )

    assert response.status_code == 200

    response.context["device"].id == d.id


def test_get_device_detail_organization_member(
    client, organization_member_user, setup_data
):

    d = setup_data["d1"]

    client.force_login(organization_member_user.user)

    response = client.get(
        reverse("device_detail", kwargs={"module_id": d.id}),
        HTTP_X_USERINFO=organization_member_user.user_info,
    )

    assert response.status_code == 200

    response.context["device"].id == d.id


def test_device_list_global_admin(client, global_admin_user):

    client.force_login(global_admin_user.user)

    response = client.get(
        reverse("device_list"), HTTP_X_USERINFO=global_admin_user.user_info
    )

    assert response.status_code == 200

    # confirm result set is unfiltered
    assert list(response.context["device_list"]) == list(Device.objects.all())


def test_device_group_list_global_admin(client, global_admin_user):

    client.force_login(global_admin_user.user)

    response = client.get(
        reverse("device_group_list"),
        follow=True,
        HTTP_X_USERINFO=global_admin_user.user_info,
    )

    assert response.status_code == 200

    assert list(response.context["filter"].qs) == list(DeviceGroup.objects.all())


def test_device_group_list_organization_member_viewer(
    client, organization_member_user, setup_data
):
    org1 = setup_data["org1"]

    account_profile_mapping = {
        (organization_member_user.user, org1, RoleChoices.VIEWER)
    }
    setup_account_profile_mapping(account_profile_mapping)

    client.force_login(organization_member_user.user)

    response = client.get(
        reverse("device_group_list"),
        follow=True,
        HTTP_X_USERINFO=organization_member_user.user_info,
    )

    assert response.status_code == 200

    # confirm result set is filtered queryset based on organization profile
    assert list(response.context["filter"].qs) == list(
        DeviceGroup.objects.filter(owner=org1)
    )
