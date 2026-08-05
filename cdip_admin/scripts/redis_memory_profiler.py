"""Read-only memory profiler for a Redis instance: per-db overview plus
per-key-prefix memory/count/no-TTL breakdown. Never writes or deletes.

Usage:
    cd cdip_admin && REDIS_HOST=... python -m scripts.redis_memory_profiler            # overview only
    cd cdip_admin && REDIS_HOST=... python -m scripts.redis_memory_profiler 0 --depth 1
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


def print_overview(r):
    mem = r.info("memory")
    print(
        f"used_memory: {mem.get('used_memory_human')}  "
        f"maxmemory: {mem.get('maxmemory_human', mem.get('maxmemory'))} "
        f"(policy: {mem.get('maxmemory_policy')})  "
        f"fragmentation: {mem.get('mem_fragmentation_ratio')}"
    )
    keyspace = r.info("keyspace")
    for db_name in sorted(keyspace):
        info = keyspace[db_name]
        print(
            f"{db_name}: keys={info.get('keys'):,} expires={info.get('expires'):,} "
            f"avg_ttl={info.get('avg_ttl')}"
        )
    print()


def parse_args():
    parser = argparse.ArgumentParser(
        description="Read-only Redis memory profiler: instance overview, plus "
        "per-prefix memory breakdown for one db."
    )
    parser.add_argument("db", type=int, nargs="?", default=None,
                        help="db number to profile by prefix (omit for overview only)")
    parser.add_argument("--depth", type=int, default=1,
                        help="key segments (split on . and :) per prefix bucket (default 1)")
    parser.add_argument("--scan-count", type=int, default=500,
                        help="SCAN COUNT hint per batch (default 500)")
    parser.add_argument("--throttle", type=float, default=50,
                        help="sleep between SCAN batches in ms (default 50)")
    return parser.parse_args()


def main():
    args = parse_args()
    r = get_redis_from_env(args.db if args.db is not None else 0)
    print_overview(r)
    if args.db is None:
        return

    total = r.dbsize()
    print(f"Profiling db {args.db} (~{total:,} keys) by prefix (depth {args.depth})...\n")
    progress = {"scanned": 0, "start": time.time(), "last_print": 0.0}

    def on_batch(n):
        progress["scanned"] += n
        now = time.time()
        if now - progress["last_print"] >= 1.0:
            elapsed = now - progress["start"]
            rate = progress["scanned"] / elapsed if elapsed > 0 else 0
            pct = (progress["scanned"] / total * 100) if total else 0
            sys.stdout.write(
                f"\rScanned {progress['scanned']:,}/{total:,} ({pct:.1f}%) | {rate:,.0f} keys/s"
            )
            sys.stdout.flush()
            progress["last_print"] = now

    batches = iter_key_batches(
        r, count=args.scan_count, throttle_seconds=args.throttle / 1000.0
    )
    stats = aggregate_prefix_stats(
        batches, lambda keys: fetch_key_stats(r, keys), depth=args.depth, on_batch=on_batch
    )
    sys.stdout.write("\n\n")
    print(format_stats_table(stats))


if __name__ == "__main__":
    main()
