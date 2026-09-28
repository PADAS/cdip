import json
import shutil
import subprocess
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from integrations.management.commands.convert_bridge_integration import (
    EVERYWHERE_HUB_JQ_FILTER,
    EVERYWHERE_HUB_WEBHOOK_CONFIG,
)
from integrations.models import (
    Integration,
    IntegrationType,
    IntegrationWebhook,
    WebhookConfiguration,
)


pytestmark = pytest.mark.django_db


# The shipped filter with the fix reverted: this is what live rows look like.
BUGGY_JQ_FILTER = EVERYWHERE_HUB_JQ_FILTER.replace(
    "else .alertType end", "else . end"
)


@pytest.fixture(autouse=True)
def buggy_filter_is_actually_different():
    assert BUGGY_JQ_FILTER != EVERYWHERE_HUB_JQ_FILTER, (
        "the fixed filter no longer contains 'else .alertType end'; this test "
        "module's buggy fixture is stale"
    )


@pytest.fixture
def generic_webhook_type():
    integration_type = IntegrationType.objects.create(
        name="Webhook", value="generic_webhooks"
    )
    IntegrationWebhook.objects.create(
        integration_type=integration_type,
        name="Generic JSON Webhook",
        value="generic_json_webhook",
    )
    return integration_type


@pytest.fixture
def webhook_config_factory(organization, generic_webhook_type):
    def make(jq_filter, name="Everywhere Hub Alerts", integration_type=None):
        integration = Integration.objects.create(
            type=integration_type or generic_webhook_type,
            owner=organization,
            name=name,
        )
        return WebhookConfiguration.objects.create(
            integration=integration,
            webhook=(integration_type or generic_webhook_type).webhook,
            data={**EVERYWHERE_HUB_WEBHOOK_CONFIG, "jq_filter": jq_filter},
        )

    return make


def run_repair(*args):
    stdout = StringIO()
    call_command(
        "repair_everywhere_hub_jq_filter", *args, stdout=stdout, stderr=StringIO()
    )
    return stdout.getvalue()


def run_repair_json(*args):
    return json.loads(run_repair(*args))


def test_apply_repairs_a_buggy_filter(webhook_config_factory):
    config = webhook_config_factory(BUGGY_JQ_FILTER)

    run_repair("--apply")

    config.refresh_from_db()
    assert config.data["jq_filter"] == EVERYWHERE_HUB_JQ_FILTER


def test_dry_run_is_the_default(webhook_config_factory):
    config = webhook_config_factory(BUGGY_JQ_FILTER)

    run_repair()

    config.refresh_from_db()
    assert config.data["jq_filter"] == BUGGY_JQ_FILTER


def test_dry_run_still_reports_what_it_would_repair(webhook_config_factory):
    webhook_config_factory(BUGGY_JQ_FILTER)

    report = run_repair_json()

    assert report["applied"] is False
    assert len(report["repaired"]) == 1


def test_an_already_correct_filter_is_left_alone(webhook_config_factory):
    config = webhook_config_factory(EVERYWHERE_HUB_JQ_FILTER)

    report = run_repair_json("--apply")

    config.refresh_from_db()
    assert config.data["jq_filter"] == EVERYWHERE_HUB_JQ_FILTER
    assert report["repaired"] == []


def test_a_filter_without_the_everywhere_hub_marker_is_not_touched(
    webhook_config_factory,
):
    # 'else . end' is ordinary jq; only Everywhere Hub filters are in scope.
    unrelated = '. | if .active then .name else . end'
    config = webhook_config_factory(unrelated, name="Some Other Feed")

    report = run_repair_json("--apply")

    config.refresh_from_db()
    assert config.data["jq_filter"] == unrelated
    assert report["repaired"] == []


def test_a_configuration_for_another_webhook_is_ignored(
    webhook_config_factory, organization
):
    other_type = IntegrationType.objects.create(name="Liquidtech", value="liquidtech")
    IntegrationWebhook.objects.create(
        integration_type=other_type,
        name="Liquidtech Webhook",
        value="liquidtech_webhook",
    )
    config = webhook_config_factory(BUGGY_JQ_FILTER, integration_type=other_type)

    report = run_repair_json("--apply")

    config.refresh_from_db()
    assert config.data["jq_filter"] == BUGGY_JQ_FILTER
    assert report["repaired"] == []


def test_only_the_alert_type_expression_changes(webhook_config_factory):
    # A filter customised elsewhere keeps its customisation.
    customised = BUGGY_JQ_FILTER.replace("conversation_id: 0", "conversation_id: 42")
    config = webhook_config_factory(customised)

    run_repair("--apply")

    config.refresh_from_db()
    assert "conversation_id: 42" in config.data["jq_filter"]
    assert "else .alertType end" in config.data["jq_filter"]
    assert "else . end" not in config.data["jq_filter"]


def test_repair_is_idempotent(webhook_config_factory):
    config = webhook_config_factory(BUGGY_JQ_FILTER)

    run_repair("--apply")
    second = run_repair_json("--apply")

    config.refresh_from_db()
    assert config.data["jq_filter"] == EVERYWHERE_HUB_JQ_FILTER
    assert second["repaired"] == []


def test_report_records_the_previous_filter_so_a_revert_is_possible(
    webhook_config_factory,
):
    config = webhook_config_factory(BUGGY_JQ_FILTER)

    report = run_repair_json("--apply")

    entry = report["repaired"][0]
    assert entry["webhook_configuration"] == str(config.id)
    assert entry["integration"] == str(config.integration_id)
    assert entry["previous_jq_filter"] == BUGGY_JQ_FILTER


def test_integration_flag_limits_the_repair(webhook_config_factory):
    target = webhook_config_factory(BUGGY_JQ_FILTER)
    other = webhook_config_factory(BUGGY_JQ_FILTER, name="Another Hub")

    run_repair("--apply", "--integration", str(target.integration_id))

    target.refresh_from_db()
    other.refresh_from_db()
    assert target.data["jq_filter"] == EVERYWHERE_HUB_JQ_FILTER
    assert other.data["jq_filter"] == BUGGY_JQ_FILTER


def test_unknown_integration_is_rejected(webhook_config_factory):
    webhook_config_factory(BUGGY_JQ_FILTER)

    with pytest.raises(CommandError, match="not found"):
        run_repair("--integration", "1d9f4a6e-0000-0000-0000-000000000000")


def test_malformed_integration_id_is_rejected(webhook_config_factory):
    webhook_config_factory(BUGGY_JQ_FILTER)

    with pytest.raises(CommandError, match="not found"):
        run_repair("--integration", "not-a-uuid")


@pytest.mark.skipif(shutil.which("jq") is None, reason="jq CLI is required")
def test_repaired_filter_emits_a_string_event_type_for_an_unmapped_alert(
    webhook_config_factory,
):
    config = webhook_config_factory(BUGGY_JQ_FILTER)
    payload = {
        "alertType": "SOME UNMAPPED ALERT",
        "deviceName": "tracker-1",
        "description": "Alert description",
        "createTimeMs": 1700000000000,
        "location": {
            "gpsTimeMs": 1700000000000,
            "latitudeDegrees": 1,
            "longitudeDegrees": 2,
        },
    }

    def event_type_for(jq_filter):
        result = subprocess.run(
            ["jq", jq_filter], input=json.dumps(payload),
            text=True, capture_output=True, check=True,
        )
        return json.loads(result.stdout)["event_type"]

    # Before: the fallback yields the whole payload object.
    assert isinstance(event_type_for(config.data["jq_filter"]), dict)

    run_repair("--apply")

    config.refresh_from_db()
    assert event_type_for(config.data["jq_filter"]) == "SOME UNMAPPED ALERT"
