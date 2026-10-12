from datetime import datetime, timezone

from er_smart_sync.state import SyncState

from sync_integrations.state import STATE_KEY_BASE, RedisStateStore


class FakeRedis:
    def __init__(self):
        self.data = {}

    def get(self, key):
        return self.data.get(key)

    def set(self, key, value):
        self.data[key] = value.encode("utf-8") if isinstance(value, str) else value


def test_missing_key_yields_empty_state():
    store = RedisStateStore(client=FakeRedis())
    state = store.get_last_poll("abc")
    assert state == SyncState()


def test_round_trip_uses_existing_key_format():
    client = FakeRedis()
    store = RedisStateStore(client=client)
    when = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
    store.set_last_poll("abc", SyncState(event_last_poll_at=when))

    assert f"{STATE_KEY_BASE}.abc" in client.data
    assert store.get_last_poll("abc").event_last_poll_at == when
    assert store.get_last_poll("abc").patrol_last_poll_at is None


def test_reads_state_written_by_the_old_synchronizer():
    # Exact bytes the previous smartconnect.er_sync_utils.EarthRangerReaderState.json() wrote.
    legacy = (
        b'{"event_last_poll_at": "2026-09-30T08:15:00.123456+00:00", '
        b'"patrol_last_poll_at": "2026-09-29T08:15:00+00:00"}'
    )
    client = FakeRedis()
    client.data[f"{STATE_KEY_BASE}.legacy"] = legacy
    state = RedisStateStore(client=client).get_last_poll("legacy")
    assert state.event_last_poll_at == datetime(2026, 9, 30, 8, 15, 0, 123456, tzinfo=timezone.utc)
    assert state.patrol_last_poll_at == datetime(2026, 9, 29, 8, 15, tzinfo=timezone.utc)
