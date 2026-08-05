import fakeredis
import pytest
import redis

from scripts.redis_stale_key_cleaner import (
    IdleTimeUnavailable,
    fetch_idle_times,
    find_stale_candidates,
)

DAY = 86400


def _seeded():
    r = fakeredis.FakeRedis()
    r.set("backfill.old", "x")                                   # no TTL, idle 40d
    r.set("backfill.recent", "x")                                # no TTL, idle 1d
    r.set("dispatched_observation.a.b", "x", ex=25 * 3600)       # has TTL, idle 40d
    idle = {
        b"backfill.old": 40 * DAY,
        b"backfill.recent": 1 * DAY,
        b"dispatched_observation.a.b": 40 * DAY,
    }
    return r, lambda _r, keys: [idle[k] for k in keys]


class TestFindStaleCandidates:
    def test_only_no_ttl_keys_over_threshold_are_candidates(self):
        r, idle_fetcher = _seeded()
        cands = find_stale_candidates(
            r, idle_threshold_seconds=30 * DAY, idle_fetcher=idle_fetcher, throttle_seconds=0
        )
        assert cands == [(b"backfill.old", 40 * DAY)]

    def test_key_with_ttl_is_never_a_candidate_even_when_idle(self):
        r, idle_fetcher = _seeded()
        cands = find_stale_candidates(
            r, idle_threshold_seconds=1, idle_fetcher=idle_fetcher, throttle_seconds=0
        )
        assert all(not k.startswith(b"dispatched_observation") for k, _ in cands)

    def test_match_constrains_scan(self):
        r, idle_fetcher = _seeded()
        r.set("other.old", "x")
        cands = find_stale_candidates(
            r, idle_threshold_seconds=1, match="backfill*",
            idle_fetcher=idle_fetcher, throttle_seconds=0,
        )
        assert {k for k, _ in cands} == {b"backfill.old", b"backfill.recent"}

    def test_idle_fetcher_error_propagates(self):
        r, _ = _seeded()

        def boom(_r, keys):
            raise IdleTimeUnavailable("no idle times")

        with pytest.raises(IdleTimeUnavailable):
            find_stale_candidates(
                r, idle_threshold_seconds=1, idle_fetcher=boom, throttle_seconds=0
            )

    def test_on_progress_reports_totals(self):
        r, idle_fetcher = _seeded()
        calls = []
        find_stale_candidates(
            r, idle_threshold_seconds=30 * DAY, idle_fetcher=idle_fetcher,
            throttle_seconds=0, on_progress=lambda n, c: calls.append((n, c)),
        )
        assert sum(n for n, _ in calls) == 3
        assert calls[-1][1] == 1


class TestFetchIdleTimes:
    def test_response_error_raises_idle_time_unavailable(self, monkeypatch):
        r = fakeredis.FakeRedis()
        r.set("k", "v")

        class BoomPipe:
            def execute_command(self, *args):
                return self

            def execute(self):
                raise redis.exceptions.ResponseError("An LFU maxmemory policy is selected")

        monkeypatch.setattr(r, "pipeline", lambda transaction=False: BoomPipe())
        with pytest.raises(IdleTimeUnavailable, match="OBJECT IDLETIME failed"):
            fetch_idle_times(r, [b"k"])
