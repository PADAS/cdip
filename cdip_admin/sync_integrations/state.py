"""er-smart-sync StateStore backed by the portal's Redis.

Keeps the key and JSON shape the previous synchronizer used
(``er.function.state.<integration_id>`` holding ``event_last_poll_at`` and
``patrol_last_poll_at``), so last-poll timestamps carry over with no
backfill.
"""
from er_smart_sync.state import SyncState

from sync_integrations.cache import cache

STATE_KEY_BASE = "er.function.state"


class RedisStateStore:
    def __init__(self, client=None):
        self._client = client if client is not None else cache

    @staticmethod
    def _key(integration_id: str) -> str:
        return f"{STATE_KEY_BASE}.{integration_id}"

    def get_last_poll(self, integration_id: str) -> SyncState:
        raw = self._client.get(self._key(integration_id))
        return SyncState.parse_raw(raw) if raw else SyncState()

    def set_last_poll(self, integration_id: str, state: SyncState) -> None:
        self._client.set(self._key(integration_id), state.json())
