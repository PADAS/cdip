from unittest.mock import Mock

from scripts.redis_memory_profiler import (
    PrefixStats,
    aggregate_prefix_stats,
    format_stats_table,
    print_overview,
)

STATS_TABLE = {
    b"disp.1.a": (100, 90000),      # (memory bytes, ttl seconds)
    b"disp.2.b": (150, 90000),
    b"backfill.9": (1000, -1),      # leaked: no TTL
    b"gone.1": (None, -2),          # vanished mid-scan
}


def fake_fetcher(keys):
    return [STATS_TABLE[k] for k in keys]


class TestAggregatePrefixStats:
    def test_aggregates_counts_bytes_and_no_ttl_by_prefix(self):
        batches = [[b"disp.1.a", b"disp.2.b"], [b"backfill.9"]]
        stats = aggregate_prefix_stats(batches, fake_fetcher)
        assert stats["disp"] == PrefixStats(count=2, total_bytes=250, no_ttl_count=0)
        assert stats["backfill"] == PrefixStats(count=1, total_bytes=1000, no_ttl_count=1)

    def test_key_gone_mid_scan_is_skipped(self):
        stats = aggregate_prefix_stats([[b"gone.1", b"backfill.9"]], fake_fetcher)
        assert "gone" not in stats
        assert stats["backfill"].count == 1

    def test_nil_memory_usage_counts_as_zero_bytes(self):
        def fetcher(keys):
            return [(None, -1)]
        stats = aggregate_prefix_stats([[b"backfill.9"]], fetcher)
        assert stats["backfill"] == PrefixStats(count=1, total_bytes=0, no_ttl_count=1)

    def test_on_batch_reports_progress(self):
        seen = []
        aggregate_prefix_stats(
            [[b"disp.1.a", b"disp.2.b"], [b"backfill.9"]], fake_fetcher, on_batch=seen.append
        )
        assert seen == [2, 1]


class TestFormatStatsTable:
    def test_rows_sorted_by_total_bytes_desc_with_leak_column(self):
        stats = {
            "small": PrefixStats(count=10, total_bytes=1000, no_ttl_count=0),
            "big": PrefixStats(count=4, total_bytes=8 * 1048576, no_ttl_count=2),
        }
        out = format_stats_table(stats)
        lines = out.splitlines()
        assert "prefix" in lines[0] and "% no-TTL" in lines[0]
        assert lines[1].startswith("big")
        assert "8.0" in lines[1] and "50.0%" in lines[1]
        assert lines[2].startswith("small")
        assert "0.0%" in lines[2]


class TestPrintOverview:
    def test_prints_memory_and_keyspace_sections(self, capsys):
        r = Mock()
        r.info.side_effect = [
            {
                "used_memory_human": "100.5M",
                "maxmemory_human": "1.0G",
                "maxmemory": 1073741824,
                "maxmemory_policy": "allkeys-lru",
                "mem_fragmentation_ratio": 1.05,
            },
            {
                "db0": {
                    "keys": 1000,
                    "expires": 500,
                    "avg_ttl": 3600000,
                }
            }
        ]
        print_overview(r)
        out = capsys.readouterr().out
        assert "used_memory" in out
        assert "db0" in out
