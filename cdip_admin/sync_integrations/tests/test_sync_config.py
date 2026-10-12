import pytest

from sync_integrations.er_smart_sync import build_sync_config, build_synchronizer

pytestmark = pytest.mark.django_db


@pytest.fixture
def smart_integration(outbound_integration_smart):
    outbound_integration_smart.login = "smart-user"
    outbound_integration_smart.password = "smart-pass"  # pragma: allowlist secret
    outbound_integration_smart.additional = {
        "version": "7.5.7",
        "use_language_code": "es",
        "ca_uuids": ["ca-1"],
        "configurable_models_lists": {"ca-1": [{"uuid": "cm-1", "name": "CM", "use_with_earth_ranger": True}]},
    }
    outbound_integration_smart.save()
    return outbound_integration_smart


@pytest.fixture
def er_integration(inbound_integration_er):
    inbound_integration_er.endpoint = "https://site.pamdas.org/api/v1.0"
    inbound_integration_er.token = "er-token"  # pragma: allowlist secret
    inbound_integration_er.save()
    return inbound_integration_er


def test_maps_smart_side(smart_integration, er_integration):
    config = build_sync_config(smart_config=smart_integration, er_config=er_integration)
    assert config.smart.endpoint == smart_integration.endpoint
    assert config.smart.login == "smart-user"
    assert config.smart.password == "smart-pass"
    assert config.smart.version == "7.5.7"
    assert config.smart.use_language_code == "es"
    assert config.smart.ca_uuids == ["ca-1"]
    assert config.smart.configurable_models_lists == smart_integration.additional["configurable_models_lists"]
    assert config.smart.provider_key == "smart_connect"


def test_maps_er_side_with_fixed_policy(smart_integration, er_integration, settings):
    settings.ER_SMART_SYNC_EVENT_TYPE_VERSION = "v2"
    config = build_sync_config(smart_config=smart_integration, er_config=er_integration)
    assert config.earthranger.id == str(er_integration.id)
    assert config.earthranger.endpoint == "https://site.pamdas.org/api/v1.0"
    assert config.earthranger.token == "er-token"
    assert config.earthranger.event_type_version == "v2"
    assert config.earthranger.cm_variant_mode == "split"
    assert config.earthranger.migrate_legacy_v1 is True


def test_event_type_version_setting_override(smart_integration, er_integration, settings):
    settings.ER_SMART_SYNC_EVENT_TYPE_VERSION = "v1"
    config = build_sync_config(smart_config=smart_integration, er_config=er_integration)
    assert config.earthranger.event_type_version == "v1"


def test_missing_smart_version_defaults(smart_integration, er_integration):
    smart_integration.additional = {"ca_uuids": ["ca-1"]}
    config = build_sync_config(smart_config=smart_integration, er_config=er_integration)
    assert config.smart.version == "7.0"
    assert config.smart.use_language_code == "en"
    assert config.smart.configurable_models_lists == {}


def test_er_login_password_without_token(smart_integration, er_integration):
    er_integration.token = ""
    er_integration.login = "er-user"
    er_integration.password = "er-pass"  # pragma: allowlist secret
    config = build_sync_config(smart_config=smart_integration, er_config=er_integration)
    assert config.earthranger.token == ""
    assert config.earthranger.login == "er-user"
    assert config.earthranger.password == "er-pass"


def test_build_synchronizer_wires_portal_adapters(mocker, smart_integration, er_integration, settings):
    from sync_integrations.state import RedisStateStore
    from sync_integrations.tracing import PortalTracing

    settings.RAW_OBSERVATIONS_TOPIC = "raw-observations-test"
    publisher = mocker.MagicMock()
    storage = mocker.MagicMock()
    mocker.patch("sync_integrations.er_smart_sync.get_publisher", return_value=publisher)
    mocker.patch("sync_integrations.er_smart_sync.get_cloud_storage", return_value=storage)
    cache_guard = mocker.patch("sync_integrations.er_smart_sync.ensure_smart_cache_generation")
    er_client_cls = mocker.patch("er_smart_sync.synchronizer.ERClient")
    smart_client_cls = mocker.patch("er_smart_sync.synchronizer.SmartClient")

    sync = build_synchronizer(smart_config=smart_integration, er_config=er_integration)

    cache_guard.assert_called_once_with()
    assert sync.publisher is publisher
    assert sync.file_storage is storage
    assert isinstance(sync.state_store, RedisStateStore)
    assert isinstance(sync.tracing, PortalTracing)
    assert sync.observations_topic == "raw-observations-test"
    er_client_cls.assert_called_once()
    assert er_client_cls.call_args.kwargs["provider_key"] == "smart_connect"
    smart_client_cls.assert_called_once()
    assert smart_client_cls.call_args.kwargs["version"] == "7.5.7"
