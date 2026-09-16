import json
from io import StringIO

from unittest.mock import Mock, patch

import pytest
import requests
from django.core.management import call_command
from django.core.management.base import CommandError

from integrations.management.commands.convert_bridge_integration import MARKER_KEY
from integrations.models import (
    BridgeIntegration,
    BridgeIntegrationType,
    Integration,
    IntegrationAction,
    IntegrationType,
    IntegrationWebhook,
    Route,
)


pytestmark = pytest.mark.django_db


ER_SITE = "test-site.pamdas.org"
ER_TOKEN = "test-er-token-0000"
INREACH_URL = "https://inreach-gateway.example.com"
INREACH_USERNAME = "test-ipc-inbound"
INREACH_PASSWORD = "test-inreach-password"
ER_SOURCE_PROVIDER = "gundi_everywhere_inreach"
BRIDGE_NAME = "Test Bridge Integration"

COMMAND_MODULE = (
    "integrations.management.commands.convert_bridge_integration"
)


# --- Fixtures -------------------------------------------------------------
#
# The IntegrationType catalog below mirrors the production rows (slugs, action
# values and webhook values) rather than conftest's generic v2 fixtures, since
# the command looks types up by slug and would silently diverge otherwise.


@pytest.fixture
def integration_types_for_conversion():
    inreach = IntegrationType.objects.create(
        name="Garmin InReach", value="inreach"
    )
    IntegrationAction.objects.create(
        integration_type=inreach,
        type=IntegrationAction.ActionTypes.AUTHENTICATION,
        name="Auth",
        value="auth",
    )
    IntegrationAction.objects.create(
        integration_type=inreach,
        type=IntegrationAction.ActionTypes.PUSH_DATA,
        name="Push Messages",
        value="push_messages",
    )
    IntegrationWebhook.objects.create(
        integration_type=inreach, name="Inreach Webhook", value="inreach_webhook"
    )

    earth_ranger = IntegrationType.objects.create(
        name="EarthRanger", value="earth_ranger"
    )
    IntegrationAction.objects.create(
        integration_type=earth_ranger,
        type=IntegrationAction.ActionTypes.AUTHENTICATION,
        name="Auth",
        value="auth",
    )
    for value, name in (
        ("push_observations", "Push Observations"),
        ("push_events", "Push Events"),
    ):
        IntegrationAction.objects.create(
            integration_type=earth_ranger,
            type=IntegrationAction.ActionTypes.PUSH_DATA,
            name=name,
            value=value,
        )

    api_push = IntegrationType.objects.create(name="API", value="api_push")
    IntegrationAction.objects.create(
        integration_type=api_push,
        type=IntegrationAction.ActionTypes.PULL_DATA,
        name="Generic API Push Pull",
        value="receive_data",
    )

    generic_webhooks = IntegrationType.objects.create(
        name="Webhook", value="generic_webhooks"
    )
    IntegrationWebhook.objects.create(
        integration_type=generic_webhooks,
        name="Generic JSON Webhook",
        value="generic_json_webhook",
    )

    return {
        "inreach": inreach,
        "earth_ranger": earth_ranger,
        "api_push": api_push,
        "generic_webhooks": generic_webhooks,
    }


@pytest.fixture
def bridge_integration(organization):
    # Migration 0047 already seeds the 'er_inreach' type, so get_or_create
    # rather than create.
    bridge_type, _ = BridgeIntegrationType.objects.get_or_create(
        slug="er_inreach", defaults={"name": "ER InReach"}
    )
    return BridgeIntegration.objects.create(
        type=bridge_type,
        owner=organization,
        name=BRIDGE_NAME,
        additional={
            "er_site": ER_SITE,
            "er_token": ER_TOKEN,
            "inreach_url": INREACH_URL,
            "inreach_password": INREACH_PASSWORD,
            "inreach_username": INREACH_USERNAME,
            "er_source_provider": ER_SOURCE_PROVIDER,
            "append_recipients_to_message": True,
        },
    )


def run_conversion(bridge_integration, *args):
    """Run the command and return its raw stdout."""
    stdout = StringIO()
    call_command(
        "convert_bridge_integration",
        str(bridge_integration.id),
        *args,
        stdout=stdout,
        stderr=StringIO(),
    )
    return stdout.getvalue()


def run_conversion_json(bridge_integration, *args):
    """Run the command and return its stdout parsed as JSON."""
    return json.loads(run_conversion(bridge_integration, *args))


# --- Tests ----------------------------------------------------------------


def test_creates_one_integration_per_type(
    bridge_integration, integration_types_for_conversion
):
    run_conversion(bridge_integration)

    created_types = sorted(
        Integration.objects.values_list("type__value", flat=True)
    )
    assert created_types == [
        "api_push",
        "earth_ranger",
        "generic_webhooks",
        "inreach",
    ]


def integration_of_type(type_value):
    return Integration.objects.get(type__value=type_value)


def test_inreach_integration_takes_bridge_name_and_inreach_url(
    bridge_integration, integration_types_for_conversion
):
    run_conversion(bridge_integration)

    inreach = integration_of_type("inreach")
    assert inreach.name == BRIDGE_NAME
    assert inreach.base_url == INREACH_URL
    assert inreach.owner == bridge_integration.owner


def test_earth_ranger_integration_base_url_is_normalized(
    bridge_integration, integration_types_for_conversion
):
    run_conversion(bridge_integration)

    earth_ranger = integration_of_type("earth_ranger")
    assert earth_ranger.name == ER_SITE
    assert earth_ranger.base_url == f"https://{ER_SITE}/"


def test_inbound_only_integrations_have_blank_base_url(
    bridge_integration, integration_types_for_conversion
):
    run_conversion(bridge_integration)

    assert integration_of_type("api_push").name == f"ER Messages from {ER_SITE}"
    assert integration_of_type("api_push").base_url == ""
    assert integration_of_type("generic_webhooks").name == "Everywhere Hub Alerts"
    assert integration_of_type("generic_webhooks").base_url == ""


def test_inreach_auth_configuration_carries_credentials(
    bridge_integration, integration_types_for_conversion
):
    run_conversion(bridge_integration)

    config = integration_of_type("inreach").configurations.get(action__value="auth")
    assert config.data == {
        "api_url": INREACH_URL,
        "username": INREACH_USERNAME,
        "password": INREACH_PASSWORD,
    }


def test_inreach_push_messages_configuration_carries_append_recipients(
    bridge_integration, integration_types_for_conversion
):
    run_conversion(bridge_integration)

    config = integration_of_type("inreach").configurations.get(
        action__value="push_messages"
    )
    assert config.data == {"append_recipients_to_message": True}


def test_earth_ranger_auth_configuration_uses_token(
    bridge_integration, integration_types_for_conversion
):
    run_conversion(bridge_integration)

    config = integration_of_type("earth_ranger").configurations.get(
        action__value="auth"
    )
    assert config.data == {"authentication_type": "token", "token": ER_TOKEN}


def test_every_action_gets_a_configuration_row(
    bridge_integration, integration_types_for_conversion
):
    run_conversion(bridge_integration)

    earth_ranger = integration_of_type("earth_ranger")
    assert sorted(
        earth_ranger.configurations.values_list("action__value", flat=True)
    ) == ["auth", "push_events", "push_observations"]


def test_inreach_webhook_configuration_enables_both_streams(
    bridge_integration, integration_types_for_conversion
):
    run_conversion(bridge_integration)

    webhook_config = integration_of_type("inreach").webhook_configuration
    assert webhook_config.webhook.value == "inreach_webhook"
    assert webhook_config.data == {
        "include_messages": True,
        "include_observations": True,
    }


def test_everywhere_hub_webhook_configuration_emits_events(
    bridge_integration, integration_types_for_conversion
):
    run_conversion(bridge_integration)

    webhook_config = integration_of_type("generic_webhooks").webhook_configuration
    assert webhook_config.webhook.value == "generic_json_webhook"
    assert webhook_config.data["output_type"] == "ev"
    # The jq filter maps Everywhere Hub alert types onto ER event types.
    assert "ew_check_in_im_ok" in webhook_config.data["jq_filter"]
    assert "EMERGENCY ENTERED" in webhook_config.data["jq_filter"]
    assert sorted(webhook_config.data["json_schema"]["properties"]) == [
        "alertType",
        "createTimeMs",
        "description",
        "deviceAlias",
        "deviceName",
        "fenceId",
        "location",
        "processedMessageId",
    ]


def test_creates_three_routes_owned_by_the_bridge_owner(
    bridge_integration, integration_types_for_conversion
):
    run_conversion(bridge_integration)

    routes = Route.objects.all()
    assert routes.count() == 3
    assert all(route.owner == bridge_integration.owner for route in routes)


def test_inreach_route_delivers_to_earth_ranger(
    bridge_integration, integration_types_for_conversion
):
    run_conversion(bridge_integration)

    route = Route.objects.get(data_providers=integration_of_type("inreach"))
    assert list(route.destinations.all()) == [integration_of_type("earth_ranger")]


def test_inreach_route_maps_provider_key_for_observations(
    bridge_integration, integration_types_for_conversion
):
    run_conversion(bridge_integration)

    inreach = integration_of_type("inreach")
    earth_ranger = integration_of_type("earth_ranger")
    route = Route.objects.get(data_providers=inreach)

    assert route.configuration.data["field_mappings"] == {
        str(inreach.id): {
            "obv": {
                str(earth_ranger.id): {
                    "destination_field": "provider_key",
                    "default": ER_SOURCE_PROVIDER,
                }
            }
        }
    }


def test_api_push_route_delivers_messages_to_inreach(
    bridge_integration, integration_types_for_conversion
):
    run_conversion(bridge_integration)

    route = Route.objects.get(data_providers=integration_of_type("api_push"))
    assert list(route.destinations.all()) == [integration_of_type("inreach")]
    assert route.configuration is None


def test_webhook_route_delivers_alerts_to_earth_ranger(
    bridge_integration, integration_types_for_conversion
):
    run_conversion(bridge_integration)

    route = Route.objects.get(
        data_providers=integration_of_type("generic_webhooks")
    )
    assert list(route.destinations.all()) == [integration_of_type("earth_ranger")]
    assert route.configuration is None


def test_json_output_lists_every_created_object(
    bridge_integration, integration_types_for_conversion
):
    output = run_conversion_json(bridge_integration)

    assert output["bridge_integration"]["id"] == str(bridge_integration.id)
    created = output["created"]
    assert len(created["integrations"]) == 4
    assert len(created["routes"]) == 3
    assert len(created["route_configurations"]) == 1
    assert len(created["webhook_configurations"]) == 2
    assert {c["action"] for c in created["integration_configurations"]} == {
        "auth",
        "push_messages",
        "push_events",
        "push_observations",
        "receive_data",
    }


def test_json_output_identifies_integrations_by_id_and_type(
    bridge_integration, integration_types_for_conversion
):
    output = run_conversion_json(bridge_integration)

    inreach = integration_of_type("inreach")
    entry = next(
        i for i in output["created"]["integrations"] if i["type"] == "inreach"
    )
    assert entry["id"] == str(inreach.id)
    assert entry["name"] == inreach.name
    assert entry["base_url"] == INREACH_URL


def test_credentials_are_redacted_from_json_output_by_default(
    bridge_integration, integration_types_for_conversion
):
    output = run_conversion(bridge_integration)

    assert ER_TOKEN not in output
    assert INREACH_PASSWORD not in output
    assert "***" in output
    # Non-secret configuration is still reported verbatim.
    assert INREACH_USERNAME in output


def test_show_secrets_flag_reports_credentials_verbatim(
    bridge_integration, integration_types_for_conversion
):
    output = run_conversion(bridge_integration, "--show-secrets")

    assert ER_TOKEN in output
    assert INREACH_PASSWORD in output


def test_redaction_does_not_reach_the_database(
    bridge_integration, integration_types_for_conversion
):
    run_conversion(bridge_integration)

    config = integration_of_type("earth_ranger").configurations.get(
        action__value="auth"
    )
    assert config.data["token"] == ER_TOKEN


def test_progress_messages_stay_out_of_stdout(
    bridge_integration, integration_types_for_conversion
):
    stdout, stderr = StringIO(), StringIO()
    call_command(
        "convert_bridge_integration",
        str(bridge_integration.id),
        stdout=stdout,
        stderr=stderr,
    )

    json.loads(stdout.getvalue())  # stdout is pure JSON
    assert stderr.getvalue().strip()  # progress went somewhere


# --- Guards ---------------------------------------------------------------


def test_unknown_bridge_integration_id_is_rejected(integration_types_for_conversion):
    with pytest.raises(CommandError, match="not found"):
        call_command(
            "convert_bridge_integration",
            "1d9f4a6e-0000-0000-0000-000000000000",
            stdout=StringIO(),
            stderr=StringIO(),
        )


def test_malformed_bridge_integration_id_is_rejected(
    integration_types_for_conversion,
):
    with pytest.raises(CommandError, match="not found"):
        call_command(
            "convert_bridge_integration",
            "not-a-uuid",
            stdout=StringIO(),
            stderr=StringIO(),
        )


def test_every_missing_configuration_key_is_reported_at_once(
    bridge_integration, integration_types_for_conversion
):
    bridge_integration.additional.pop("er_token")
    bridge_integration.additional.pop("inreach_username")
    bridge_integration.save()

    with pytest.raises(CommandError) as excinfo:
        run_conversion(bridge_integration)

    message = str(excinfo.value)
    assert "er_token" in message
    assert "inreach_username" in message


def test_missing_integration_type_is_reported_by_slug(bridge_integration):
    IntegrationType.objects.create(name="Garmin InReach", value="inreach")

    with pytest.raises(CommandError) as excinfo:
        run_conversion(bridge_integration)

    message = str(excinfo.value)
    assert "earth_ranger" in message
    assert "api_push" in message
    assert "generic_webhooks" in message
    assert "inreach" not in message.replace("Garmin InReach", "")


def test_created_integrations_record_the_bridge_they_came_from(
    bridge_integration, integration_types_for_conversion
):
    run_conversion(bridge_integration)

    markers = {
        i.additional.get("converted_from_bridge_integration")
        for i in Integration.objects.all()
    }
    assert markers == {str(bridge_integration.id)}


def test_converting_the_same_bridge_twice_is_refused(
    bridge_integration, integration_types_for_conversion
):
    run_conversion(bridge_integration)

    with pytest.raises(CommandError, match="already been converted"):
        run_conversion(bridge_integration)

    assert Integration.objects.count() == 4


def test_force_flag_converts_an_already_converted_bridge(
    bridge_integration, integration_types_for_conversion
):
    run_conversion(bridge_integration)

    output = run_conversion_json(bridge_integration, "--force")

    # A forced second run builds a fresh set, but the ER destination from the
    # first run is a valid candidate for the same site and gets reused rather
    # than duplicated.
    assert len(output["created"]["integrations"]) == 3
    assert len(output["reused"]["integrations"]) == 1
    assert Integration.objects.count() == 7


def test_force_with_no_reuse_er_duplicates_the_destination_too(
    bridge_integration, integration_types_for_conversion
):
    run_conversion(bridge_integration)

    run_conversion(bridge_integration, "--force", "--no-reuse-er")

    assert Integration.objects.count() == 8


def test_a_failure_part_way_through_leaves_nothing_behind(
    bridge_integration, integration_types_for_conversion
):
    # The Everywhere Hub integration is built last; removing its webhook makes
    # the command fail after the other three integrations already exist.
    IntegrationWebhook.objects.get(value="generic_json_webhook").delete()

    with pytest.raises(CommandError):
        run_conversion(bridge_integration)

    assert Integration.objects.count() == 0
    assert Route.objects.count() == 0


def test_dry_run_reports_the_conversion_without_writing_it(
    bridge_integration, integration_types_for_conversion
):
    output = run_conversion_json(bridge_integration, "--dry-run")

    assert len(output["created"]["integrations"]) == 4
    assert len(output["created"]["routes"]) == 3
    assert Integration.objects.count() == 0
    assert Route.objects.count() == 0


# --- Reusing an existing EarthRanger integration ---------------------------


@pytest.fixture
def existing_er_factory(organization, integration_types_for_conversion):
    def make(auth_data, owner=None, enabled=True, base_url=f"https://{ER_SITE}"):
        integration = Integration.objects.create(
            type=integration_types_for_conversion["earth_ranger"],
            owner=owner or organization,
            name="Existing EarthRanger",
            base_url=base_url,
            enabled=enabled,
        )
        integration.create_missing_configurations()
        config = integration.configurations.get(action__value="auth")
        config.data = auth_data
        config.save()
        return integration

    return make


def token_auth(token):
    return {"authentication_type": "token", "token": token}


def er_user_response(username):
    response = Mock()
    response.status_code = 200
    response.json.return_value = {"data": {"username": username}}
    return response


def test_existing_er_integration_with_the_same_token_is_reused(
    bridge_integration, existing_er_factory
):
    existing = existing_er_factory(token_auth(ER_TOKEN))

    run_conversion(bridge_integration)

    assert Integration.objects.filter(type__value="earth_ranger").count() == 1
    route = Route.objects.get(data_providers=integration_of_type("inreach"))
    assert list(route.destinations.all()) == [existing]


def test_a_reused_integration_is_reported_separately_from_created_ones(
    bridge_integration, existing_er_factory
):
    existing = existing_er_factory(token_auth(ER_TOKEN))

    output = run_conversion_json(bridge_integration)

    assert len(output["created"]["integrations"]) == 3
    assert [i["id"] for i in output["reused"]["integrations"]] == [str(existing.id)]


def test_a_reused_integration_is_not_stamped_or_modified(
    bridge_integration, existing_er_factory
):
    existing = existing_er_factory(token_auth(ER_TOKEN))

    run_conversion(bridge_integration)

    existing.refresh_from_db()
    assert MARKER_KEY not in existing.additional
    assert existing.name == "Existing EarthRanger"


def test_different_token_for_the_same_er_user_is_reused(
    bridge_integration, existing_er_factory
):
    existing = existing_er_factory(token_auth("a-different-token"))

    with patch(f"{COMMAND_MODULE}.requests.get") as get:
        get.return_value = er_user_response("gundi_service_account")
        run_conversion(bridge_integration)

    assert get.call_count == 2
    assert Integration.objects.filter(type__value="earth_ranger").count() == 1
    assert list(
        Route.objects.get(
            data_providers=integration_of_type("inreach")
        ).destinations.all()
    ) == [existing]


def test_different_token_for_a_different_er_user_is_refused(
    bridge_integration, existing_er_factory
):
    existing_er_factory(token_auth("a-different-token"))

    with patch(f"{COMMAND_MODULE}.requests.get") as get:
        get.side_effect = [
            er_user_response("bridge_account"),
            er_user_response("someone_else"),
        ]
        with pytest.raises(CommandError) as excinfo:
            run_conversion(bridge_integration)

    message = str(excinfo.value)
    assert "bridge_account" in message
    assert "someone_else" in message
    assert Integration.objects.count() == 1  # only the pre-existing one


def test_username_password_integration_is_matched_against_the_er_user(
    bridge_integration, existing_er_factory
):
    existing = existing_er_factory(
        {"authentication_type": "username_password", "username": "shared_account"}
    )

    with patch(f"{COMMAND_MODULE}.requests.get") as get:
        get.return_value = er_user_response("shared_account")
        run_conversion(bridge_integration)

    # Only the bridge's own token needs looking up in this case.
    assert get.call_count == 1
    assert Integration.objects.filter(type__value="earth_ranger").count() == 1


def test_an_unreachable_er_site_refuses_rather_than_guessing(
    bridge_integration, existing_er_factory
):
    existing_er_factory(token_auth("a-different-token"))

    with patch(f"{COMMAND_MODULE}.requests.get") as get:
        get.side_effect = requests.ConnectionError("no route to host")
        with pytest.raises(CommandError, match="Could not verify"):
            run_conversion(bridge_integration)


def test_rejected_credentials_report_the_status_code(
    bridge_integration, existing_er_factory
):
    existing_er_factory(token_auth("a-different-token"))

    unauthorized = Mock()
    unauthorized.status_code = 401
    with patch(f"{COMMAND_MODULE}.requests.get") as get:
        get.return_value = unauthorized
        with pytest.raises(CommandError, match="401"):
            run_conversion(bridge_integration)


def test_er_credentials_never_appear_in_a_verification_error(
    bridge_integration, existing_er_factory
):
    existing_er_factory(token_auth("a-different-token"))

    with patch(f"{COMMAND_MODULE}.requests.get") as get:
        get.side_effect = requests.ConnectionError("boom")
        with pytest.raises(CommandError) as excinfo:
            run_conversion(bridge_integration)

    assert ER_TOKEN not in str(excinfo.value)


def test_several_matching_er_integrations_are_refused(
    bridge_integration, existing_er_factory
):
    first = existing_er_factory(token_auth(ER_TOKEN))
    second = existing_er_factory(token_auth(ER_TOKEN))

    with pytest.raises(CommandError) as excinfo:
        run_conversion(bridge_integration)

    message = str(excinfo.value)
    assert str(first.id) in message
    assert str(second.id) in message


def test_er_integration_flag_chooses_among_several_candidates(
    bridge_integration, existing_er_factory
):
    existing_er_factory(token_auth(ER_TOKEN))
    chosen = existing_er_factory(token_auth(ER_TOKEN))

    run_conversion(bridge_integration, "--er-integration", str(chosen.id))

    route = Route.objects.get(data_providers=integration_of_type("inreach"))
    assert list(route.destinations.all()) == [chosen]


def test_no_reuse_er_flag_creates_a_fresh_destination(
    bridge_integration, existing_er_factory
):
    existing_er_factory(token_auth(ER_TOKEN))

    run_conversion(bridge_integration, "--no-reuse-er")

    assert Integration.objects.filter(type__value="earth_ranger").count() == 2


def test_a_disabled_er_integration_is_not_reused(
    bridge_integration, existing_er_factory
):
    existing_er_factory(token_auth(ER_TOKEN), enabled=False)

    with pytest.raises(CommandError, match="disabled"):
        run_conversion(bridge_integration)


def test_an_er_integration_owned_by_another_organization_is_not_reused(
    bridge_integration, existing_er_factory, other_organization
):
    existing_er_factory(token_auth(ER_TOKEN), owner=other_organization)

    with pytest.raises(CommandError, match="owned by"):
        run_conversion(bridge_integration)


def test_an_er_integration_without_credentials_is_not_reused(
    bridge_integration, existing_er_factory
):
    existing_er_factory({})

    with pytest.raises(CommandError, match="no auth configuration"):
        run_conversion(bridge_integration)


def test_an_er_integration_for_a_different_site_is_not_a_candidate(
    bridge_integration, existing_er_factory
):
    existing_er_factory(token_auth(ER_TOKEN), base_url="https://elsewhere.pamdas.org")

    run_conversion(bridge_integration)

    assert Integration.objects.filter(type__value="earth_ranger").count() == 2
