from fnmatch import fnmatch

from sync_integrations.smart_cache import (
    CACHE_PATTERN,
    GENERATION_KEY,
    ensure_smart_cache_generation,
)


class FakeRedis:
    def __init__(self, data=None):
        self.data = {k: (v.encode() if isinstance(v, str) else v) for k, v in (data or {}).items()}

    def get(self, key):
        return self.data.get(key)

    def set(self, key, value):
        self.data[key] = value.encode() if isinstance(value, str) else value

    def delete(self, key):
        self.data.pop(key.decode() if isinstance(key, bytes) else key, None)

    def scan_iter(self, match="*"):
        for key in list(self.data):
            if fnmatch(key, match):
                yield key.encode()


def test_first_run_flushes_stale_entries_and_writes_the_marker():
    client = FakeRedis(
        {
            "cache:smart-ca:ca-1:datamodel": "{}",
            "cache:smart-ca:na:cdm:cm-1": "{}",
            "er.function.state.abc": "{}",
        }
    )

    assert ensure_smart_cache_generation(client=client, version="1.15.0") is True

    assert set(client.data) == {"er.function.state.abc", GENERATION_KEY}
    assert client.data[GENERATION_KEY] == b"1.15.0"


def test_matching_generation_is_a_no_op():
    client = FakeRedis({GENERATION_KEY: "1.15.0", "cache:smart-ca:ca-1:datamodel": "{}"})

    assert ensure_smart_cache_generation(client=client, version="1.15.0") is False

    assert "cache:smart-ca:ca-1:datamodel" in client.data


def test_client_upgrade_flushes_again():
    client = FakeRedis({GENERATION_KEY: "1.15.0", "cache:smart-ca:ca-1:datamodel": "{}"})

    assert ensure_smart_cache_generation(client=client, version="1.16.0") is True

    assert "cache:smart-ca:ca-1:datamodel" not in client.data
    assert client.data[GENERATION_KEY] == b"1.16.0"


def test_pattern_covers_every_smartconnect_cache_key():
    for key in (
        "cache:smart-ca:ca-1:datamodel",
        "cache:smart-ca:ca-1:metadata",
        "cache:smart-ca:na:cdm:cm-1",
    ):
        assert fnmatch(key, CACHE_PATTERN)
