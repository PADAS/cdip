import fakeredis
import pytest

from scripts.redis_ops_common import (
    chunked,
    get_redis_from_env,
    iter_key_batches,
    key_prefix,
)


class TestKeyPrefix:
    def test_dot_separated_key_buckets_to_first_segment(self):
        assert key_prefix(b"dispatched_observation.0a1b.9f8e") == "dispatched_observation"

    def test_colon_separated_key(self):
        assert key_prefix(b"backfill:job:123") == "backfill"

    def test_depth_two_joins_first_two_segments(self):
        assert key_prefix(b"backfill.movebank.123", depth=2) == "backfill.movebank"

    def test_key_without_separator_is_its_own_prefix(self):
        assert key_prefix(b"celery") == "celery"

    def test_undecodable_bytes_do_not_crash(self):
        assert key_prefix(b"\xff\xfe.tail") == "��"


class TestChunked:
    def test_splits_into_batches_of_size(self):
        assert list(chunked([1, 2, 3, 4, 5], 2)) == [[1, 2], [3, 4], [5]]

    def test_empty_list_yields_nothing(self):
        assert list(chunked([], 10)) == []


class TestGetRedisFromEnv:
    def test_missing_host_exits(self, monkeypatch):
        monkeypatch.delenv("REDIS_HOST", raising=False)
        with pytest.raises(SystemExit):
            get_redis_from_env(0)

    def test_non_integer_port_exits(self, monkeypatch):
        monkeypatch.setenv("REDIS_HOST", "localhost")
        monkeypatch.setenv("REDIS_PORT", "not-a-port")
        with pytest.raises(SystemExit):
            get_redis_from_env(0)

    def test_valid_env_returns_client(self, monkeypatch):
        monkeypatch.setenv("REDIS_HOST", "localhost")
        monkeypatch.setenv("REDIS_PORT", "6390")
        client = get_redis_from_env(3)
        kwargs = client.connection_pool.connection_kwargs
        assert (kwargs["host"], kwargs["port"], kwargs["db"]) == ("localhost", 6390, 3)


class TestIterKeyBatches:
    def _seeded(self):
        r = fakeredis.FakeRedis()
        for i in range(25):
            r.set(f"prefix.{i}", "x")
        r.set("other.key", "x")
        return r

    def test_yields_all_keys_across_batches(self):
        r = self._seeded()
        seen = [k for batch in iter_key_batches(r, count=10, throttle_seconds=0) for k in batch]
        assert len(seen) == 26
        assert set(seen) == set(r.keys("*"))

    def test_match_filters_keys(self):
        r = self._seeded()
        seen = [k for batch in iter_key_batches(r, match="prefix.*", count=10, throttle_seconds=0) for k in batch]
        assert len(seen) == 25
        assert all(k.startswith(b"prefix.") for k in seen)
