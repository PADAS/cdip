"""Shared helpers for the standalone Redis ops scripts. No Django dependency."""
import os
import re
import time

import redis

_SEPARATORS = re.compile(r"[.:]")


def get_redis_from_env(db):
    """Build a client from REDIS_HOST (required) and REDIS_PORT (default 6379)."""
    host = os.environ.get("REDIS_HOST")
    if not host:
        print("Error: REDIS_HOST environment variable is not set")
        raise SystemExit(1)
    port_str = os.environ.get("REDIS_PORT", "6379")
    try:
        port = int(port_str)
    except ValueError:
        print(f"Error: REDIS_PORT must be an integer, got '{port_str}'")
        raise SystemExit(1)
    return redis.Redis(host=host, port=port, db=db)


def key_prefix(key, depth=1):
    """Bucket a key by its first `depth` segments, splitting on '.' and ':'."""
    parts = _SEPARATORS.split(key.decode(errors="replace"))
    return ".".join(parts[:depth])


def chunked(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def iter_key_batches(r, match=None, count=500, throttle_seconds=0.05):
    """Yield batches of keys via SCAN, sleeping between iterations to cap server load."""
    cursor = 0
    while True:
        cursor, keys = r.scan(cursor, match=match, count=count)
        if keys:
            yield keys
        if cursor == 0:
            return
        if throttle_seconds:
            time.sleep(throttle_seconds)
