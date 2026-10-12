# cdip_admin/sync_integrations/er_smart_sync.py
"""Glue between portal integration rows and the er-smart-sync library.

The synchronizer itself (SMART data models -> ER event types, ER events and
patrols -> SMART via routing) lives in er-smart-sync. This module only maps
the Django configuration into the library's config and plugs in the
portal's publisher, storage, Redis state and tracing.
"""
import logging

from cdip_connector.core.cloudstorage import get_cloud_storage
from django.conf import settings
from er_smart_sync.config import EarthRangerConfig, SmartConnectConfig, SyncConfig
from er_smart_sync.synchronizer import ERSmartSynchronizer

from core.utils import get_publisher
from sync_integrations.state import RedisStateStore
from sync_integrations.tracing import PortalTracing

logger = logging.getLogger(__name__)


def build_sync_config(*, smart_config, er_config) -> SyncConfig:
    """Map a SMART outbound configuration and an ER inbound configuration.

    Policy is fixed here rather than per integration: event type version from
    settings (v2), one ER event type per configurable-model node (split), and
    legacy v1 types migrated in place before each push.
    """
    additional = smart_config.additional or {}
    smart = SmartConnectConfig(
        endpoint=smart_config.endpoint,
        login=smart_config.login,
        password=smart_config.password,
        version=additional.get("version") or "7.0",
        use_language_code=additional.get("use_language_code") or "en",
        ca_uuids=additional.get("ca_uuids") or [],
        configurable_models_lists=additional.get("configurable_models_lists") or {},
        provider_key=smart_config.type.slug,
    )
    earthranger = EarthRangerConfig(
        id=str(er_config.id),
        endpoint=er_config.endpoint,
        login=er_config.login,
        password=er_config.password,
        token=er_config.token,
        event_type_version=settings.ER_SMART_SYNC_EVENT_TYPE_VERSION,
        cm_variant_mode="split",
        migrate_legacy_v1=True,
    )
    return SyncConfig(smart=smart, earthranger=earthranger)


def build_synchronizer(*, smart_config, er_config) -> ERSmartSynchronizer:
    return ERSmartSynchronizer(
        config=build_sync_config(smart_config=smart_config, er_config=er_config),
        publisher=get_publisher(),
        file_storage=get_cloud_storage(),
        state_store=RedisStateStore(),
        tracing=PortalTracing(),
        observations_topic=settings.RAW_OBSERVATIONS_TOPIC,
    )
