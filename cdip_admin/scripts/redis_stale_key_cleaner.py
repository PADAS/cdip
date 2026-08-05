"""Find (and optionally UNLINK) keys that have NO TTL and have been idle longer
than a threshold. Keys with any TTL are never touched: they expire on their own,
and deleting live dispatched_observation.* idempotency keys early breaks the
PubSub redelivery contract (see docs/superpowers/specs/2026-08-04-redis-prod-cleanup-design.md).

Dry-run by default; deletion requires --delete.

Usage:
    REDIS_HOST=... python redis_stale_key_cleaner.py 0                       # dry-run, 30d
    REDIS_HOST=... python redis_stale_key_cleaner.py 0 --match 'backfill*' --delete
"""
import argparse
import sys
import time

import redis

from scripts.redis_ops_common import (
    chunked,
    get_redis_from_env,
    iter_key_batches,
    key_prefix,
)

MIN_DELETE_IDLE_DAYS = 2.0
DAY_SECONDS = 86400


class IdleTimeUnavailable(RuntimeError):
    pass


def fetch_idle_times(r, keys):
    """Pipelined OBJECT IDLETIME. Aborts loudly if the server can't answer
    (e.g. LFU maxmemory-policy) — never treat unknown idle as 0."""
    pipe = r.pipeline(transaction=False)
    for k in keys:
        pipe.execute_command("OBJECT", "IDLETIME", k)
    try:
        return pipe.execute()
    except redis.exceptions.ResponseError as exc:
        raise IdleTimeUnavailable(
            f"OBJECT IDLETIME failed ({exc}). If maxmemory-policy is an LFU policy, "
            "idle times are unavailable; aborting rather than treating idle as 0."
        ) from exc


def find_stale_candidates(r, idle_threshold_seconds, match=None, scan_count=500,
                          throttle_seconds=0.05, idle_fetcher=None, on_progress=None):
    """Return (key, idle_seconds) for keys with TTL == -1 and idle > threshold."""
    idle_fetcher = idle_fetcher or fetch_idle_times
    candidates = []
    for keys in iter_key_batches(r, match=match, count=scan_count,
                                 throttle_seconds=throttle_seconds):
        pipe = r.pipeline(transaction=False)
        for k in keys:
            pipe.ttl(k)
        ttls = pipe.execute()
        no_ttl_keys = [k for k, ttl in zip(keys, ttls) if ttl == -1]
        if no_ttl_keys:
            for k, idle in zip(no_ttl_keys, idle_fetcher(r, no_ttl_keys)):
                if idle is not None and idle > idle_threshold_seconds:
                    candidates.append((k, idle))
        if on_progress:
            on_progress(len(keys), len(candidates))
    return candidates
