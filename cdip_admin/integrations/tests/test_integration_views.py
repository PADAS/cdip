import json
from typing import List
from django.http import QueryDict
from django.urls import reverse
from conftest import setup_account_profile_mapping
from core.enums import RoleChoices
from integrations import models
from integrations.models import (
    InboundIntegrationType,
    InboundIntegrationConfiguration,
    OutboundIntegrationConfiguration,
    OutboundIntegrationType,
    BridgeIntegration,
    Device,
    DeviceGroup,

)
from organizations.models import Organization
from urllib.parse import urlencode


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


def _test_basic_config_data_is_rendered(configurations: List, rendered_screen: str):
    # Helper function to check that the minimal data for each configuration is shown in the screen
    for config in configurations:
        assert str(config.name) in rendered_screen
        assert str(config.type) in rendered_screen
        assert str(config.owner) in rendered_screen


def test_get_inbound_integration_configuration_list_filter_by_enabled_true(
        client, global_admin_user, setup_data
):
    # Request the configurations filtering by enabled=True
    client.force_login(global_admin_user.user)
    response = client.get(
        reverse("inbound_integration_configuration_list"),
        data={"enabled": True},
        HTTP_X_USERINFO=global_admin_user.user_info,
    )

    # Check the request response
    assert response.status_code == 200
    # Check result set is filtered
    enabled_configurations = InboundIntegrationConfiguration.objects.filter(enabled=True).order_by("id")
    assert list(response.context["inboundintegrationconfiguration_list"]) == list(enabled_configurations)
    # Check that at least the minimal data for each configuration is seen in the screen
    rendered_screen = response.content.decode("utf-8")
    _test_basic_config_data_is_rendered(enabled_configurations, rendered_screen)


def test_get_inbound_integration_configuration_list_filter_by_enabled_false(
        client, global_admin_user, setup_data
):
    # Request the configurations filtering by enabled=False
    client.force_login(global_admin_user.user)
    response = client.get(
        reverse("inbound_integration_configuration_list"),
        data={"enabled": False},
        HTTP_X_USERINFO=global_admin_user.user_info,
    )

    # Check the request response
    assert response.status_code == 200
    # Check result set is filtered
    disabled_configurations = InboundIntegrationConfiguration.objects.filter(enabled=False).order_by("id")
    assert list(response.context["inboundintegrationconfiguration_list"]) == list(disabled_configurations)
    # Check that at least the minimal data for each configuration is seen in the screen
    rendered_screen = response.content.decode("utf-8")
    _test_basic_config_data_is_rendered(disabled_configurations, rendered_screen)


def test_get_inbound_integration_configuration_list_filter_by_enabled_unset(
        client, global_admin_user, setup_data
):
    # Request the configurations filtering by enabled=False
    client.force_login(global_admin_user.user)
    response = client.get(
        reverse("inbound_integration_configuration_list"),
        data={"enabled": ""},
        HTTP_X_USERINFO=global_admin_user.user_info,
    )

    # Check the request response
    assert response.status_code == 200
    # Check result set in NOT filtered by the enabled field
    all_configurations = InboundIntegrationConfiguration.objects.all().order_by("id")
    assert list(response.context["inboundintegrationconfiguration_list"]) == list(all_configurations)
    # Check that at least the minimal data for each configuration is seen in the screen
    rendered_screen = response.content.decode("utf-8")
    _test_basic_config_data_is_rendered(all_configurations, rendered_screen)


# ToDo: Mock external dependencies. This test fails when Kong isn't available / reachable
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


def test_inbound_integration_update_form_save(
    client, global_admin_user, setup_data
):
    client.force_login(global_admin_user.user)
    org2 = setup_data["org2"]
    iit3 = setup_data["iit3"]
    iit4 = setup_data["iit4"]
    ii = InboundIntegrationConfiguration.objects.create(
        type=iit3, name="Inbound Configuration Original", owner=org2, enabled=False,
        state={"test": "foo"}
    )
    new_state_value = {
        "email": "test@email.com",  # Required
        "password": "password",  # Required
        "site_name": "new site name",  # Required
        "test": "new state config"
    }
    ii_request_post = {
        "type": str(iit4.id),
        "owner": str(org2.id),
        "name": "Inbound EDITED",
        "state": json.dumps(new_state_value),
        "enabled": True
    }
    urlencoded_data = urlencode(ii_request_post)
    response = client.post(
        reverse("inbound_integration_configuration_update", kwargs={"configuration_id": ii.id}),
        follow=True,
        data=urlencoded_data,
        HTTP_X_USERINFO=global_admin_user.user_info,
        content_type="application/x-www-form-urlencoded"
    )
    assert response.status_code == 200
    ii.refresh_from_db()
    assert ii.name == ii_request_post["name"]
    assert str(ii.type.id) == ii_request_post["type"]
    assert str(ii.owner.id) == ii_request_post["owner"]
    assert ii.state == new_state_value
    assert ii.enabled == ii_request_post["enabled"]


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
        OutboundIntegrationConfiguration.objects.filter(owner=org1).order_by("id")
    )


def test_get_outbound_integration_configuration_list_filter_by_enabled_true(
        client, global_admin_user, setup_data
):
    # Request the configurations filtering by enabled=True
    client.force_login(global_admin_user.user)
    response = client.get(
        reverse("outbound_integration_configuration_list"),
        data={"enabled": True},
        HTTP_X_USERINFO=global_admin_user.user_info,
    )

    # Check the request response
    assert response.status_code == 200
    # Check result set is filtered
    enabled_configurations = OutboundIntegrationConfiguration.objects.filter(enabled=True).order_by("id")
    assert list(response.context["outboundintegrationconfiguration_list"]) == list(enabled_configurations)
    # Check that at least the minimal data for each configuration is seen in the screen
    rendered_screen = response.content.decode("utf-8")
    _test_basic_config_data_is_rendered(enabled_configurations, rendered_screen)


def test_get_outbound_integration_configuration_list_filter_by_enabled_false(
        client, global_admin_user, setup_data
):
    # Request the configurations filtering by enabled=True
    client.force_login(global_admin_user.user)
    response = client.get(
        reverse("outbound_integration_configuration_list"),
        data={"enabled": False},
        HTTP_X_USERINFO=global_admin_user.user_info,
    )

    # Check the request response
    assert response.status_code == 200
    # Check result set is filtered
    disabled_configurations = OutboundIntegrationConfiguration.objects.filter(enabled=False).order_by("id")
    assert list(response.context["outboundintegrationconfiguration_list"]) == list(disabled_configurations)
    # Check that at least the minimal data for each configuration is seen in the screen
    rendered_screen = response.content.decode("utf-8")
    _test_basic_config_data_is_rendered(disabled_configurations, rendered_screen)


def test_get_outbound_integration_configuration_list_filter_by_enabled_unset(
        client, global_admin_user, setup_data
):
    # Request the configurations filtering by enabled=True
    client.force_login(global_admin_user.user)
    response = client.get(
        reverse("outbound_integration_configuration_list"),
        data={"enabled": ""},
        HTTP_X_USERINFO=global_admin_user.user_info,
    )

    # Check the request response
    assert response.status_code == 200
    # Check result set is filtered
    all_configurations = OutboundIntegrationConfiguration.objects.all().order_by("id")
    assert list(response.context["outboundintegrationconfiguration_list"]) == list(all_configurations)
    # Check that at least the minimal data for each configuration is seen in the screen
    rendered_screen = response.content.decode("utf-8")
    _test_basic_config_data_is_rendered(all_configurations, rendered_screen)


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


def test_outbound_integration_update_form(
    client, global_admin_user, setup_data
):
    client.force_login(global_admin_user.user)
    org2 = setup_data["org2"]
    oit3 = setup_data["oit3"]
    oit4 = setup_data["oit4"]
    oi = OutboundIntegrationConfiguration.objects.create(
        type=oit3, name="Outbound Configuration Original", owner=org2, enabled=False,
        state={"test": "foo"}
    )
    new_state_value = {
        "email": "test@email.com",  # Required
        "password": "password",  # Required
        "site_name": "new site name",  # Required
        "test": "new state config"
    }
    oi_request_post = {
        "type": str(oit4.id),
        "owner": str(org2.id),
        "name": "Outbound EDITED",
        "state": json.dumps(new_state_value),
        "enabled": True
    }
    urlencoded_data = urlencode(oi_request_post)
    response = client.post(
        reverse("outbound_integration_configuration_update", kwargs={"configuration_id": oi.id}),
        follow=True,
        data=urlencoded_data,
        HTTP_X_USERINFO=global_admin_user.user_info,
        content_type="application/x-www-form-urlencoded"
    )
    assert response.status_code == 200
    oi.refresh_from_db()
    assert oi.name == oi_request_post["name"]
    assert str(oi.type.id) == oi_request_post["type"]
    assert str(oi.owner.id) == oi_request_post["owner"]
    assert oi.state == new_state_value
    assert oi.enabled == oi_request_post["enabled"]


# TODO: OutboundIntegrationConfigurationUpdateView


# Bridge Integration Tests
def test_get_bridge_integration_configuration_list_filter_by_enabled_true(
        client, global_admin_user, setup_data
):
    # Request the configurations filtering by enabled=True
    client.force_login(global_admin_user.user)
    response = client.get(
        reverse("bridge_integration_list"),
        data={"enabled": True},
        HTTP_X_USERINFO=global_admin_user.user_info,
    )

    # Check the request response
    assert response.status_code == 200
    # Check result set is filtered
    enabled_configurations = BridgeIntegration.objects.filter(enabled=True).order_by("name")
    assert list(response.context["bridgeintegration_list"]) == list(enabled_configurations)
    # Check that at least the minimal data for each configuration is seen in the screen
    rendered_screen = response.content.decode("utf-8")
    _test_basic_config_data_is_rendered(enabled_configurations, rendered_screen)


def test_get_bridge_integration_configuration_list_filter_by_enabled_false(
        client, global_admin_user, setup_data
):
    # Request the configurations filtering by enabled=True
    client.force_login(global_admin_user.user)
    response = client.get(
        reverse("bridge_integration_list"),
        data={"enabled": False},
        HTTP_X_USERINFO=global_admin_user.user_info,
    )

    # Check the request response
    assert response.status_code == 200
    # Check result set is filtered
    disabled_configurations = BridgeIntegration.objects.filter(enabled=False).order_by("name")
    assert list(response.context["bridgeintegration_list"]) == list(disabled_configurations)
    # Check that at least the minimal data for each configuration is seen in the screen
    rendered_screen = response.content.decode("utf-8")
    _test_basic_config_data_is_rendered(disabled_configurations, rendered_screen)


def test_get_bridge_integration_configuration_list_filter_by_enabled_unset(
        client, global_admin_user, setup_data
):
    # Request the configurations filtering by enabled=True
    client.force_login(global_admin_user.user)
    response = client.get(
        reverse("bridge_integration_list"),
        data={"enabled": ""},
        HTTP_X_USERINFO=global_admin_user.user_info,
    )

    # Check the request response
    assert response.status_code == 200
    # Check result set is filtered
    all_configurations = BridgeIntegration.objects.all().order_by("name")
    assert list(response.context["bridgeintegration_list"]) == list(all_configurations)
    # Check that at least the minimal data for each configuration is seen in the screen
    rendered_screen = response.content.decode("utf-8")
    _test_basic_config_data_is_rendered(all_configurations, rendered_screen)


def test_get_bridge_integration_update_page_load(
        client, global_admin_user, setup_data
):
    client.force_login(global_admin_user.user)
    b1 = setup_data["bi1"]

    response = client.get(
        reverse("bridge_integration_update", kwargs={"id": b1.id}),
        HTTP_X_USERINFO=global_admin_user.user_info,
    )

    assert response.status_code == 200


def test_dynamic_form_div_bridge_update_form(
        client, global_admin_user, setup_data
):
    client.force_login(global_admin_user.user)
    b1 = setup_data["bi1"]

    response = client.get(
        reverse("bridge_integration_update", kwargs={"id": b1.id}),
        HTTP_X_USERINFO=global_admin_user.user_info,
    )

    assert "id_additional_jsonform" in response.rendered_content


def test_bridge_update_form_save(
        client, global_admin_user, setup_data
):
    client.force_login(global_admin_user.user)
    org2 = setup_data["org2"]
    bit2 = setup_data["bit2"]
    bit3 = setup_data["bit3"]
    bi = BridgeIntegration.objects.create(
        type=bit2, name="Bridge Integration Original", owner=org2, enabled=False,
        additional={"test": "foo"}
    )
    new_additional_value = {
        "email": "test@email.com",     # Required
        "password": "pasword",         # Required
        "site_name": "new site name",  # Required
        "test": "new additional config"
    }
    bi_request_post = {
        "type": str(bit3.id),
        "owner": str(org2.id),
        "name": "Bridge Update Test EDITED",
        "additional": json.dumps(new_additional_value),
        "enabled": True
    }
    urlencoded_data = urlencode(bi_request_post)
    response = client.post(
        reverse("bridge_integration_update", kwargs={"id": bi.id}),
        follow=True,
        data=urlencoded_data,
        HTTP_X_USERINFO=global_admin_user.user_info,
        content_type="application/x-www-form-urlencoded"
    )
    assert response.status_code == 200
    bi.refresh_from_db()
    assert bi.name == bi_request_post["name"]
    assert str(bi.type.id) == bi_request_post["type"]
    assert str(bi.owner.id) == bi_request_post["owner"]
    assert bi.additional == new_additional_value
    assert bi.enabled == bi_request_post["enabled"]


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
