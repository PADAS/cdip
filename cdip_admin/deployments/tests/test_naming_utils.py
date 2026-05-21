from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from django.conf import settings

from deployments.utils import (
    _leading_subdomain,
    create_dispatcher_for_integration,
    get_default_dispatcher_name,
    get_default_topic_name,
)


def _integration(base_url, type_value="traptagger", integration_id=None, **flags):
    """Build a lightweight Integration stand-in for naming-util tests.

    The flags map to ``is_*_site`` properties used by
    ``_dispatcher_secret_id_for`` to pick the correct secret. Returns a
    plain ``SimpleNamespace`` — fine for the pure naming utilities, which
    only do attribute access. For ``create_dispatcher_for_integration``
    use ``_integration_spec_mock`` instead so the helper's isinstance
    guard accepts it.
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


def _integration_spec_mock(base_url, type_value="earth_ranger", **flags):
    """Integration-spec'd mock for ``create_dispatcher_for_integration`` tests.

    The helper checks ``isinstance(integration, Integration)``, so the
    plain ``SimpleNamespace`` from ``_integration`` would be rejected.
    Using ``MagicMock(spec=Integration)`` makes ``isinstance`` return True
    without requiring DB setup.
    """
    from integrations.models.v2.models import Integration

    m = MagicMock(spec=Integration)
    m.base_url = base_url
    m.type = SimpleNamespace(value=type_value)
    m.id = UUID("1f42a0fa-8c5b-48b4-b9d7-b475c2635a02")
    for flag in ("is_smart_site", "is_wpswatch_site", "is_traptagger_site", "is_er_site"):
        setattr(m, flag, flags.get(flag, False))
    return m


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
        integration = _integration_spec_mock(
            "https://example.pamdas.org", "earth_ranger", **flags
        )

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
        integration = _integration_spec_mock(
            "https://example.pamdas.org", "earth_ranger", is_er_site=True
        )

        create_dispatcher_for_integration(integration)

        kwargs = create.call_args.kwargs
        # v2 naming: <subdomain>-<typeshort>-dis-<uuid>
        assert kwargs["name"].startswith("example-earth-dis-")
        # legacy_integration must NOT be set — this helper is v2-only.
        assert "legacy_integration" not in kwargs

    def test_rejects_non_v2_integration(self, patched):
        create, secrets = patched
        # SimpleNamespace is the v1 / non-Integration shape used elsewhere.
        # The helper must refuse and not touch the DB or secrets backend.
        not_an_integration = _integration("https://example.pamdas.org")

        with pytest.raises(TypeError, match="v2-only"):
            create_dispatcher_for_integration(not_an_integration)

        create.assert_not_called()
        secrets.assert_not_called()


class TestLeadingSubdomain:
    """Direct tests for the segment-cleanup helper.

    The naming utilities pass arbitrary strings from ``parsed.netloc`` or
    ``parsed.path`` into this helper, so it has to harden against shapes
    that don't look like normal hostnames.
    """

    def test_strips_non_ascii_letters_from_rest_of_segment(self):
        # Cyrillic 'а' (U+0430) in position 1 — must not leak into the name.
        # ASCII letters either side survive.
        assert _leading_subdomain("aаbc.example.com") == "abc"

    def test_falls_back_to_int_when_segment_is_wholly_non_ascii(self):
        # Cyrillic 'а' alone — filter strips it, leaving an empty segment.
        assert _leading_subdomain("а.example.com") == "int"

    def test_strips_slash_from_path_derived_host(self):
        # parsed.path can carry a leading '/' through the fallback.
        assert _leading_subdomain("/oddly.example.com") == "oddly"

    def test_strips_at_sign_from_userinfo_in_path(self):
        # urlparse without a scheme leaves user@host in path.
        assert _leading_subdomain("user@example.com", max_len=8) == "userexam"

    def test_numeric_only_segment_gets_letter_prefix(self):
        assert _leading_subdomain("8fa1d0b7.example.com", max_len=8) == "i8fa1d0b"

    def test_respects_max_len_after_prefix(self):
        # Prefix happens AFTER the initial trim, then we re-trim — so the
        # total length stays at max_len.
        result = _leading_subdomain("999.example.com", max_len=4)
        assert result == "i999"
        assert len(result) == 4
