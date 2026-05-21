from types import SimpleNamespace
from uuid import UUID

import pytest
from django.conf import settings

from deployments.utils import (
    create_dispatcher_for_integration,
    get_default_dispatcher_name,
    get_default_topic_name,
)


def _integration(base_url, type_value="traptagger", integration_id=None, **flags):
    """Build a lightweight Integration stand-in for naming/helper tests.

    The flags map to ``is_*_site`` properties used by
    ``_dispatcher_secret_id_for`` to pick the correct secret.
    """
    return SimpleNamespace(
        base_url=base_url,
        type=SimpleNamespace(value=type_value),
        id=integration_id or UUID("1f42a0fa-8c5b-48b4-b9d7-b475c2635a02"),
        is_smart_site=flags.get("is_smart_site", False),
        is_wpswatch_site=flags.get("is_wpswatch_site", False),
        is_traptagger_site=flags.get("is_traptagger_site", False),
        is_er_site=flags.get("is_er_site", False),
    )


class TestGetDefaultDispatcherName:
    def test_traptagger_numeric_leading_hostname_gets_letter_prefix(self):
        # GCP Cloud Run service names must start with a lowercase letter.
        # The fixture hostname `8fa1d0b7.fake-traptagger.org` starts with a
        # digit, so the subdomain segment must be prefixed.
        integration = _integration("8fa1d0b7.fake-traptagger.org", "traptagger")
        result = get_default_dispatcher_name(integration)
        assert result[0].isalpha()
        assert result.startswith("i8fa1d0b-trapt-dis-")

    def test_smart_bare_hostname_does_not_lead_with_hyphen(self):
        integration = _integration("acme.fake-smart.org", "smart_connect")
        result = get_default_dispatcher_name(integration)
        assert result[0].isalpha()
        assert result.startswith("acme-smart-dis-")

    def test_wpswatch_bare_hostname_does_not_lead_with_hyphen(self):
        integration = _integration("cam.fake-wpswatch.org", "wpswatch")
        result = get_default_dispatcher_name(integration)
        assert result[0].isalpha()
        assert result.startswith("cam-wpswa-dis-")

    def test_earthranger_with_scheme_preserves_existing_behavior(self):
        integration = _integration("https://example.pamdas.org", "earth_ranger")
        result = get_default_dispatcher_name(integration)
        assert result.startswith("example-earth-dis-")

    def test_empty_base_url_falls_back_to_int_placeholder(self):
        integration = _integration("", "traptagger")
        result = get_default_dispatcher_name(integration)
        assert result[0].isalpha()
        assert result.startswith("int-trapt-dis-")


class TestGetDefaultTopicName:
    def test_traptagger_numeric_leading_hostname_gets_letter_prefix(self):
        integration = _integration("8fa1d0b7.fake-traptagger.org", "traptagger")
        result = get_default_topic_name(integration)
        assert result[0].isalpha()
        assert result.startswith("i8fa1d0b7-traptagg-")
        assert result.endswith("-topic")

    def test_smart_bare_hostname_does_not_lead_with_hyphen(self):
        integration = _integration("acme.fake-smart.org", "smart_connect")
        result = get_default_topic_name(integration)
        assert result[0].isalpha()
        assert result.startswith("acme-smartcon-")
        assert result.endswith("-topic")

    def test_wpswatch_bare_hostname_does_not_lead_with_hyphen(self):
        integration = _integration("cam.fake-wpswatch.org", "wpswatch")
        result = get_default_topic_name(integration)
        assert result[0].isalpha()
        assert result.startswith("cam-wpswatch-")
        assert result.endswith("-topic")

    def test_earthranger_with_scheme_preserves_existing_behavior(self):
        integration = _integration("https://example.pamdas.org", "earth_ranger")
        result = get_default_topic_name(integration)
        assert result.startswith("example-earthran-")
        assert result.endswith("-topic")

    def test_empty_base_url_falls_back_to_int_placeholder(self):
        integration = _integration("", "traptagger")
        result = get_default_topic_name(integration)
        assert result[0].isalpha()
        assert result.startswith("int-traptagg-")
        assert result.endswith("-topic")


class TestCreateDispatcherForIntegration:
    """Direct unit tests for the v2 dispatcher-creation helper.

    Mocks the model and the GCP secrets fetch so the helper's contract
    is exercised in isolation: it must pick the correct ``secret_id`` per
    integration type, generate a v2 dispatcher name, and pass the
    integration through to ``DispatcherDeployment.objects.create``.
    """

    @pytest.fixture
    def patched(self, mocker):
        create = mocker.patch("deployments.models.DispatcherDeployment.objects.create")
        secrets = mocker.patch(
            "deployments.utils.get_dispatcher_defaults_from_gcp_secrets",
            return_value={"sentinel": "config"},
        )
        return create, secrets

    @pytest.mark.parametrize(
        "flags, expected_secret_setting",
        [
            ({"is_er_site": True}, "DISPATCHER_DEFAULTS_SECRET"),
            ({"is_smart_site": True}, "DISPATCHER_DEFAULTS_SECRET_SMART"),
            ({"is_wpswatch_site": True}, "DISPATCHER_DEFAULTS_SECRET_WPSWATCH"),
            ({"is_traptagger_site": True}, "DISPATCHER_DEFAULTS_SECRET_TRAPTAGGER"),
            ({}, "DISPATCHER_DEFAULTS_SECRET"),  # fallthrough default
        ],
    )
    def test_selects_correct_secret_per_type(self, patched, flags, expected_secret_setting):
        create, secrets = patched
        integration = _integration("https://example.pamdas.org", "earth_ranger", **flags)

        create_dispatcher_for_integration(integration)

        secrets.assert_called_once_with(
            secret_id=getattr(settings, expected_secret_setting)
        )
        create.assert_called_once()
        kwargs = create.call_args.kwargs
        assert kwargs["integration"] is integration
        assert kwargs["configuration"] == {"sentinel": "config"}

    def test_passes_v2_dispatcher_name_and_integration_fk(self, patched):
        create, _secrets = patched
        integration = _integration(
            "https://example.pamdas.org", "earth_ranger", is_er_site=True
        )

        create_dispatcher_for_integration(integration)

        kwargs = create.call_args.kwargs
        # v2 naming: <subdomain>-<typeshort>-dis-<uuid>
        assert kwargs["name"].startswith("example-earth-dis-")
        # legacy_integration must NOT be set — this helper is v2-only.
        assert "legacy_integration" not in kwargs
