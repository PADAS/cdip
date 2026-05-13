from types import SimpleNamespace
from uuid import UUID

from deployments.utils import get_default_dispatcher_name, get_default_topic_name


def _integration(base_url, type_value="traptagger", integration_id=None):
    return SimpleNamespace(
        base_url=base_url,
        type=SimpleNamespace(value=type_value),
        id=integration_id or UUID("1f42a0fa-8c5b-48b4-b9d7-b475c2635a02"),
    )


class TestGetDefaultDispatcherName:
    def test_traptagger_bare_hostname_does_not_lead_with_hyphen(self):
        integration = _integration("8fa1d0b7.fake-traptagger.org", "traptagger")
        result = get_default_dispatcher_name(integration)
        assert not result.startswith("-")
        assert result.startswith("8fa1d0b7-trapt-dis-")

    def test_smart_bare_hostname_does_not_lead_with_hyphen(self):
        integration = _integration("acme.fake-smart.org", "smart_connect")
        result = get_default_dispatcher_name(integration)
        assert not result.startswith("-")
        assert result[0].isalnum()

    def test_wpswatch_bare_hostname_does_not_lead_with_hyphen(self):
        integration = _integration("cam.fake-wpswatch.org", "wpswatch")
        result = get_default_dispatcher_name(integration)
        assert not result.startswith("-")
        assert result[0].isalnum()

    def test_earthranger_with_scheme_preserves_existing_behavior(self):
        integration = _integration("https://example.pamdas.org", "earth_ranger")
        result = get_default_dispatcher_name(integration)
        assert result.startswith("example-earth-dis-")

    def test_empty_base_url_does_not_lead_with_hyphen(self):
        integration = _integration("", "traptagger")
        result = get_default_dispatcher_name(integration)
        assert not result.startswith("-")
        assert result[0].isalnum()


class TestGetDefaultTopicName:
    def test_traptagger_bare_hostname_does_not_lead_with_hyphen(self):
        integration = _integration("8fa1d0b7.fake-traptagger.org", "traptagger")
        result = get_default_topic_name(integration)
        assert not result.startswith("-")
        assert result.startswith("8fa1d0b7.fake-traptagger-traptagg-") or \
               result.startswith("8fa1d0b7-traptagg-")
        assert result.endswith("-topic")

    def test_smart_bare_hostname_does_not_lead_with_hyphen(self):
        integration = _integration("acme.fake-smart.org", "smart_connect")
        result = get_default_topic_name(integration)
        assert not result.startswith("-")
        assert result[0].isalnum()
        assert result.endswith("-topic")

    def test_wpswatch_bare_hostname_does_not_lead_with_hyphen(self):
        integration = _integration("cam.fake-wpswatch.org", "wpswatch")
        result = get_default_topic_name(integration)
        assert not result.startswith("-")
        assert result[0].isalnum()
        assert result.endswith("-topic")

    def test_earthranger_with_scheme_preserves_existing_behavior(self):
        integration = _integration("https://example.pamdas.org", "earth_ranger")
        result = get_default_topic_name(integration)
        assert result.startswith("example-earthran-")
        assert result.endswith("-topic")

    def test_empty_base_url_does_not_lead_with_hyphen(self):
        integration = _integration("", "traptagger")
        result = get_default_topic_name(integration)
        assert not result.startswith("-")
        assert result[0].isalnum()
        assert result.endswith("-topic")
