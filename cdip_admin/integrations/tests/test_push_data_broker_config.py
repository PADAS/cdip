from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from integrations.models import Integration, IntegrationAction, RouteDestination


pytestmark = pytest.mark.django_db

EXPECTED_TOPIC = "genericwebhooks-push-data-topic"


def _reload(integration):
    return Integration.objects.get(pk=integration.pk)


def _clear_additional(integration, additional=None):
    Integration.objects.filter(pk=integration.pk).update(additional=additional or {})
    return _reload(integration)


@pytest.fixture
def er_destination_without_topic(other_organization, integration_type_er, er_action_push_events):
    integration = Integration.objects.create(
        type=integration_type_er,
        name="ER Site",
        owner=other_organization,
        base_url="https://test.pamdas.org",
    )
    return _clear_additional(integration)


@pytest.fixture
def integration_without_push_action(other_organization, integration_type_generic_webhooks):
    return Integration.objects.create(
        type=integration_type_generic_webhooks,
        name="Inbound Only",
        owner=other_organization,
    )


def test_integration_predating_push_action_has_no_topic(generic_webhooks_integration_predating_push_action):
    assert "topic" not in generic_webhooks_integration_predating_push_action.additional


@pytest.mark.parametrize(
    "additional,expected_missing",
    [
        ({}, {"topic": EXPECTED_TOPIC, "broker": "gcp_pubsub"}),
        ({"topic": "", "broker": None}, {"topic": EXPECTED_TOPIC, "broker": "gcp_pubsub"}),
        ({"topic": None}, {"topic": EXPECTED_TOPIC, "broker": "gcp_pubsub"}),
        ({"topic": "custom-topic"}, {"broker": "gcp_pubsub"}),
        ({"broker": "gcp_pubsub"}, {"topic": EXPECTED_TOPIC}),
        ({"topic": "custom-topic", "broker": "gcp_pubsub"}, {}),
    ],
)
def test_missing_push_data_broker_config(generic_webhooks_integration_predating_push_action, additional, expected_missing):
    integration = _clear_additional(generic_webhooks_integration_predating_push_action, additional)

    assert integration.missing_push_data_broker_config() == expected_missing
    assert _reload(integration).additional == additional


def test_missing_push_data_broker_config_skips_dispatcher_deployed_types(er_destination_without_topic):
    assert er_destination_without_topic.missing_push_data_broker_config() == {}


def test_missing_push_data_broker_config_skips_types_without_push_action(integration_without_push_action):
    assert integration_without_push_action.missing_push_data_broker_config() == {}


def test_ensure_push_data_broker_config_keeps_other_keys(generic_webhooks_integration_predating_push_action):
    integration = _clear_additional(generic_webhooks_integration_predating_push_action, {"topic": "custom", "other": 1})

    assert integration.ensure_push_data_broker_config() == {"broker": "gcp_pubsub"}
    assert _reload(integration).additional == {"topic": "custom", "other": 1, "broker": "gcp_pubsub"}


def test_adding_destination_to_route_sets_topic_and_broker(
    generic_webhooks_integration_predating_push_action, empty_route_other_org
):
    empty_route_other_org.destinations.add(generic_webhooks_integration_predating_push_action)

    additional = _reload(generic_webhooks_integration_predating_push_action).additional
    assert additional["topic"] == EXPECTED_TOPIC
    assert additional["broker"] == "gcp_pubsub"


def test_adding_route_to_destination_reverse_accessor_sets_topic(
    generic_webhooks_integration_predating_push_action, empty_route_other_org
):
    generic_webhooks_integration_predating_push_action.routing_rules_by_destination.add(empty_route_other_org)

    assert _reload(generic_webhooks_integration_predating_push_action).additional["topic"] == EXPECTED_TOPIC


def test_creating_route_destination_row_sets_topic(
    generic_webhooks_integration_predating_push_action, empty_route_other_org
):
    RouteDestination.objects.create(
        integration=generic_webhooks_integration_predating_push_action, route=empty_route_other_org
    )

    assert _reload(generic_webhooks_integration_predating_push_action).additional["topic"] == EXPECTED_TOPIC


def test_adding_destination_never_overwrites_existing_topic(
    generic_webhooks_integration_predating_push_action, empty_route_other_org
):
    integration = _clear_additional(
        generic_webhooks_integration_predating_push_action, {"topic": "custom-topic", "broker": "gcp_pubsub"}
    )

    empty_route_other_org.destinations.add(integration)

    assert _reload(integration).additional == {"topic": "custom-topic", "broker": "gcp_pubsub"}


def test_adding_dispatcher_deployed_destination_leaves_additional_untouched(
    er_destination_without_topic, empty_route_other_org
):
    empty_route_other_org.destinations.add(er_destination_without_topic)

    assert _reload(er_destination_without_topic).additional == {}


def test_adding_destination_without_push_action_leaves_additional_untouched(
    integration_without_push_action, empty_route_other_org
):
    before = _reload(integration_without_push_action).additional

    empty_route_other_org.destinations.add(integration_without_push_action)

    assert _reload(integration_without_push_action).additional == before


def test_new_integration_of_push_type_still_gets_topic_on_create(
    other_organization, integration_type_generic_webhooks, generic_webhooks_integration_predating_push_action
):
    integration = Integration.objects.create(
        type=integration_type_generic_webhooks, name="Created after push action", owner=other_organization,
    )

    assert integration.additional == {"topic": EXPECTED_TOPIC, "broker": "gcp_pubsub"}


def _call_backfill(*args):
    out = StringIO()
    call_command("ensure_push_data_topics", *args, stdout=out)
    return out.getvalue()


def test_backfill_dry_run_lists_without_saving(generic_webhooks_integration_predating_push_action):
    output = _call_backfill("--dry-run")

    assert str(generic_webhooks_integration_predating_push_action.id) in output
    assert "1 integration(s) would be updated" in output
    assert "topic" not in _reload(generic_webhooks_integration_predating_push_action).additional


def test_backfill_sets_missing_topic_and_broker(generic_webhooks_integration_predating_push_action):
    output = _call_backfill()

    assert "1 integration(s) updated" in output
    additional = _reload(generic_webhooks_integration_predating_push_action).additional
    assert additional == {"topic": EXPECTED_TOPIC, "broker": "gcp_pubsub"}


def test_backfill_is_idempotent(generic_webhooks_integration_predating_push_action):
    _call_backfill()
    after_first_run = _reload(generic_webhooks_integration_predating_push_action).additional

    output = _call_backfill()

    assert "0 integration(s) updated" in output
    assert _reload(generic_webhooks_integration_predating_push_action).additional == after_first_run


def test_backfill_never_overwrites_existing_topic(generic_webhooks_integration_predating_push_action):
    integration = _clear_additional(generic_webhooks_integration_predating_push_action, {"topic": "custom-topic"})

    _call_backfill()

    assert _reload(integration).additional == {"topic": "custom-topic", "broker": "gcp_pubsub"}


def test_backfill_skips_dispatcher_deployed_and_non_push_types(
    er_destination_without_topic, integration_without_push_action
):
    before = _reload(integration_without_push_action).additional

    output = _call_backfill()

    assert "0 integration(s) updated" in output
    assert _reload(er_destination_without_topic).additional == {}
    assert _reload(integration_without_push_action).additional == before


def test_backfill_type_filter(
    generic_webhooks_integration_predating_push_action, other_organization, integration_type_inreach,
):
    inreach = Integration.objects.create(type=integration_type_inreach, name="InReach", owner=other_organization)
    IntegrationAction.objects.create(
        integration_type=integration_type_inreach, type=IntegrationAction.ActionTypes.PUSH_DATA,
        name="Push Messages", value="push_messages",
    )

    _call_backfill("--type", "generic_webhooks")

    assert _reload(generic_webhooks_integration_predating_push_action).additional["topic"] == EXPECTED_TOPIC
    assert "topic" not in _reload(inreach).additional


def test_backfill_unknown_type_raises():
    with pytest.raises(CommandError, match="not found"):
        _call_backfill("--type", "no_such_type")
