"""Read-only memory profiler for a Redis instance: per-db overview plus
per-key-prefix memory/count/no-TTL breakdown. Never writes or deletes.

Usage:
    REDIS_HOST=... python redis_memory_profiler.py            # overview only
    REDIS_HOST=... python redis_memory_profiler.py 0 --depth 1
"""
import argparse
import sys
import time
from collections import defaultdict
from dataclasses import dataclass

from scripts.redis_ops_common import get_redis_from_env, iter_key_batches, key_prefix


@dataclass
class PrefixStats:
    count: int = 0
    total_bytes: int = 0
    no_ttl_count: int = 0


def fetch_key_stats(r, keys):
    """Pipelined (MEMORY USAGE, TTL) per key. Memory is None if the key vanished."""
    pipe = r.pipeline(transaction=False)
    for k in keys:
        pipe.memory_usage(k, samples=0)
    for k in keys:
        pipe.ttl(k)
    results = pipe.execute()
    return list(zip(results[: len(keys)], results[len(keys):]))


def aggregate_prefix_stats(key_batches, stats_fetcher, depth=1, on_batch=None):
    stats = defaultdict(PrefixStats)
    for keys in key_batches:
        for key, (mem, ttl) in zip(keys, stats_fetcher(keys)):
            if ttl == -2:  # key expired/deleted mid-scan
                continue
            s = stats[key_prefix(key, depth)]
            s.count += 1
            s.total_bytes += mem or 0
            if ttl == -1:
                s.no_ttl_count += 1
        if on_batch:
            on_batch(len(keys))
    return dict(stats)


def format_stats_table(stats):
    rows = sorted(stats.items(), key=lambda kv: kv[1].total_bytes, reverse=True)
    lines = [f"{'prefix':<50} {'keys':>12} {'MB':>10} {'avg B':>8} {'% no-TTL':>9}"]
    for prefix, s in rows:
        avg = s.total_bytes // s.count if s.count else 0
        pct = (s.no_ttl_count / s.count * 100) if s.count else 0.0
        lines.append(
            f"{prefix:<50} {s.count:>12,} {s.total_bytes / 1048576:>10.1f} "
            f"{avg:>8,} {pct:>8.1f}%"
        )
    return "\n".join(lines)
