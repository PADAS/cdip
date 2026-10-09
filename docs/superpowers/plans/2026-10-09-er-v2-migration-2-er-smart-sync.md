# ER v2 migration, part 2 of 4: er-smart-sync 0.5.0

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Release er-smart-sync 0.5.0, which imports the choice value rules from smartconnect-client and converts colliding v1 event types through EarthRanger's migrate endpoint before pushing v2.

**Architecture:** `choices.py` stops defining the sanitize and shortening rules and re-exports smartconnect-client's. `EarthRangerConfig` gains `migrate_legacy_v1`. `ERSmartSynchronizer` snapshots v1 event types once per run and, per CA push, migrates the intersection with the values it is about to write, then lets the existing compare-and-patch step bring the migrated records to the library's schema. The CLI exposes an off switch.

**Tech Stack:** Python 3.10+, pydantic 1.x, click, pytest with pytest-mock, ruff. Repo: `/Users/chrisdo/padas/earthranger-smart-utils` (branch off `main`). Version comes from the git tag via setuptools_scm; pushing `v0.5.0` runs `.github/workflows/release.yml` to PyPI.

**Spec:** `docs/superpowers/specs/2026-10-09-er-smart-sync-v2-migration-design.md` in PADAS/cdip, section "2. er-smart-sync (release 0.5.0)". Depends on part 1 (smartconnect-client 1.15.0 on PyPI).

## Global Constraints

- Dependency floor becomes `smartconnect-client>=1.15.0,<2.0` in `pyproject.toml`.
- The migrate call is `POST /api/v2.0/activity/eventtypes/migrate/` with body `{"dry_run": false, "event_types": [<values>]}`. ER returns a list of `{"event_type", "v2_schema", "warnings", "errors", "metadata"}`; a record is converted when its `errors` list is empty.
- `migrate_legacy_v1` is only consulted when `event_type_version == "v2"`.
- A migrate failure aborts that CA's push, the same policy as a choice-upsert error. The next run retries.
- Every public function keeps its name: `sanitize_choice_value` and `_shorten_value` stay importable from `er_smart_sync.choices` because `smart_to_er_v2.py` and the tests use them.
- Run `ruff check src tests && ruff format src tests` before each commit.

## Review Focus

1. ER's v1 list endpoint answering with an error after the sunset must not stop the v2 push; the run proceeds with nothing to migrate. Pinned in Task 3.
2. A value already converted by someone else between the snapshot and the call comes back with an `errors` entry; the run must treat the CA as failed and retry cleanly next time rather than crash. Pinned in Task 3 (error path).
3. `DryRunERClient` returns a dict, not a list, from `_post`; the migrate step must treat that as "nothing happened". Pinned in Task 3.
4. v1 types that are not in this run's build output (inactive SMART categories, hand-made types) must never be sent to migrate. Pinned in Task 3 (intersection test).
5. After a successful migrate the v2 snapshot must be refreshed, otherwise compare-and-patch sees no record and tries a POST that conflicts. Pinned in Task 3.

---

### Task 1: Import the shared choice value rules

**Files:**
- Modify: `src/er_smart_sync/choices.py:51-62` (`sanitize_choice_value`) and `:120-146` (`_shorten_value` and constants)
- Modify: `pyproject.toml:14`
- Test: `tests/test_choices.py`

**Interfaces:**
- Consumes: `smartconnect.choices.sanitize_choice_value`, `shorten_choice_value`, `CHOICE_VALUE_MAX_LEN` (part 1).
- Produces: unchanged names `sanitize_choice_value`, `_shorten_value`, `_CHOICE_VALUE_DISPLAY_MAX`, `_VALUE_HASH_LEN`, `_VALUE_PREFIX_LEN` in `er_smart_sync.choices`.

- [ ] **Step 1: Install the dependency**

```bash
cd /Users/chrisdo/padas/earthranger-smart-utils
git checkout -b feature/legacy-v1-migration main
uv pip install "smartconnect-client>=1.15.0"
```

If 1.15.0 is not on PyPI yet, install the local checkout instead: `uv pip install -e /Users/chrisdo/padas/smartconnect-client`.

- [ ] **Step 2: Write the failing test**

Append to `tests/test_choices.py`:

```python
# ── shared definition with smartconnect-client ────────────────


def test_sanitize_is_the_smartconnect_client_definition():
    import smartconnect.choices as shared

    from er_smart_sync import choices

    assert choices.sanitize_choice_value is shared.sanitize_choice_value
    assert choices._CHOICE_VALUE_DISPLAY_MAX == shared.CHOICE_VALUE_MAX_LEN


def test_shorten_value_matches_smartconnect_client():
    import smartconnect.choices as shared

    from er_smart_sync.choices import _shorten_value

    raw = "x" * 150
    assert _shorten_value(raw) == shared.shorten_choice_value(raw)
    assert _shorten_value("short") == "short"
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `pytest tests/test_choices.py -q -k smartconnect_client`
Expected: FAIL on the `is` assertion (two distinct function objects).

- [ ] **Step 4: Replace the local definitions**

In `src/er_smart_sync/choices.py`, add after the `smartconnect.models` import (line 24):

```python
from smartconnect.choices import (
    CHOICE_VALUE_MAX_LEN,
    sanitize_choice_value,  # noqa: F401  re-exported; the rule lives in smartconnect-client
    shorten_choice_value,
)
```

Delete the local `def sanitize_choice_value(...)` (lines 51 to 62). Replace the constants block and `_shorten_value` (lines 120 to 146) with:

```python
# ER's Choice table caps both `value` and `display` at varchar(100). The
# value rule (sanitize, then hash-suffix over 100 chars) is owned by
# smartconnect-client so cdip-routing can apply its inverse; only the
# display shortening below is local.
_CHOICE_VALUE_DISPLAY_MAX = CHOICE_VALUE_MAX_LEN
_VALUE_HASH_LEN = 8
_VALUE_PREFIX_LEN = _CHOICE_VALUE_DISPLAY_MAX - 1 - _VALUE_HASH_LEN


def _shorten_value(sanitized: str) -> str:
    """Hash-suffix overlong values via the shared smartconnect-client rule."""
    shortened = shorten_choice_value(sanitized)
    if shortened != sanitized:
        logger.debug(
            "Shortened choice value (len %d → %d) via hash-suffix: %r",
            len(sanitized),
            len(shortened),
            shortened,
        )
    return shortened
```

Remove the now unused `import re` if ruff reports it.

In `pyproject.toml` line 14 change the floor to `"smartconnect-client>=1.15.0,<2.0",`.

- [ ] **Step 5: Run the whole suite**

Run: `pytest -q && ruff check src tests`
Expected: all passed; the existing `test_sanitize_choice_value` table and the `_shorten_value` tests still pass against the shared implementation.

- [ ] **Step 6: Commit**

```bash
git add src/er_smart_sync/choices.py pyproject.toml tests/test_choices.py
git commit -m "Import choice value rules from smartconnect-client

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: `migrate_legacy_v1` config field

**Files:**
- Modify: `src/er_smart_sync/config.py:80-82`
- Modify: `docs/getting-started/config.md:35-36` and the table at `:62-63`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `EarthRangerConfig.migrate_legacy_v1: bool = True`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_config.py`:

```python
def test_er_config_migrate_legacy_v1_defaults_on():
    cfg = EarthRangerConfig(id="x", endpoint="https://x.pamdas.org", token="t")
    assert cfg.migrate_legacy_v1 is True


def test_er_config_migrate_legacy_v1_can_be_disabled():
    cfg = EarthRangerConfig(
        id="x", endpoint="https://x.pamdas.org", token="t", migrate_legacy_v1=False
    )
    assert cfg.migrate_legacy_v1 is False
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_config.py -q -k migrate_legacy`
Expected: FAIL with `AttributeError: 'EarthRangerConfig' object has no attribute 'migrate_legacy_v1'` (pydantic 1 ignores unknown kwargs, so the second test fails on the attribute too).

- [ ] **Step 3: Add the field**

In `src/er_smart_sync/config.py`, after `cm_variant_mode` (line 81):

```python
    # When pushing v2, convert SMART-derived v1 event types that collide with
    # the values about to be written via ER's migrate endpoint first.
    migrate_legacy_v1: bool = True
```

In `docs/getting-started/config.md`, after the `event_type_version` line of the YAML sample add:

```yaml
  migrate_legacy_v1: true         # v2 only; convert colliding v1 event types before pushing
```

and after the `event_type_version` row of the options table add:

```markdown
| `migrate_legacy_v1` | optional (default `true`) | v2 only. Before pushing, convert SMART-derived v1 event types whose value collides with the push via `POST /api/v2.0/activity/eventtypes/migrate/`; see [Event-type version](../concepts/event-type-version.md) |
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_config.py -q`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add src/er_smart_sync/config.py docs/getting-started/config.md tests/test_config.py
git commit -m "Add migrate_legacy_v1 to EarthRangerConfig

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: Migrate colliding v1 event types during the datamodel push

**Files:**
- Modify: `src/er_smart_sync/synchronizer.py` (`__init__` stats at `:215-229`, `synchronize_datamodel` at `:258-317`, `push_smart_ca_datamodel_to_earthranger` v2 branch at `:401-409`)
- Test: `tests/test_synchronizer.py`

**Interfaces:**
- Consumes: `EarthRangerConfig.migrate_legacy_v1` (Task 2); `ERClient._post(path, payload, params=None, base_url=None)` and `ERClient._api_root(version)` from earthranger-client 1.15 (already used by `choices.py`).
- Produces on `ERSmartSynchronizer`:
  - `migrate_legacy_event_types(values: list[str]) -> list[dict]`
  - `_fetch_legacy_v1_snapshot() -> list`
  - `_migrate_legacy_for(event_types) -> bool`
  - stats keys `event_types_migrated`, `event_types_migrate_errored`
  - attribute `_er_v1_event_types_cache: list | None`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_synchronizer.py`:

```python
class TestLegacyV1Migration:
    MIGRATE_PATH = "activity/eventtypes/migrate/"

    def _sync(self, config, mock_er_client):
        sync = ERSmartSynchronizer(
            config=config, er_client=mock_er_client, smart_client=MagicMock()
        )
        sync.skip_choices = True
        return sync

    @staticmethod
    def _et(value):
        et = MagicMock()
        et.value = value
        return et

    def test_snapshot_skipped_on_v1(self, sync_config, mock_er_client):
        sync = self._sync(sync_config, mock_er_client)
        assert sync._fetch_legacy_v1_snapshot() == []
        mock_er_client.get_event_types.assert_not_called()

    def test_snapshot_skipped_when_disabled(self, sync_config_v2, mock_er_client):
        sync_config_v2.earthranger.migrate_legacy_v1 = False
        sync = self._sync(sync_config_v2, mock_er_client)
        assert sync._fetch_legacy_v1_snapshot() == []
        mock_er_client.get_event_types.assert_not_called()

    def test_snapshot_fetches_v1_types(self, sync_config_v2, mock_er_client):
        mock_er_client.get_event_types.return_value = [{"value": "ca_cm_a"}]
        sync = self._sync(sync_config_v2, mock_er_client)
        assert sync._fetch_legacy_v1_snapshot() == [{"value": "ca_cm_a"}]
        mock_er_client.get_event_types.assert_called_once_with(
            include_inactive=True, include_schema=False, version="v1"
        )

    def test_snapshot_failure_is_non_fatal(self, sync_config_v2, mock_er_client):
        # After ER's v1 sunset the list endpoint errors; the v2 push must go on.
        mock_er_client.get_event_types.side_effect = Exception("410 Gone")
        sync = self._sync(sync_config_v2, mock_er_client)
        assert sync._fetch_legacy_v1_snapshot() == []

    def test_migrates_only_colliding_values_and_refreshes_v2_cache(
        self, sync_config_v2, mock_er_client
    ):
        sync = self._sync(sync_config_v2, mock_er_client)
        sync._er_v1_event_types_cache = [{"value": "ca_cm_a"}, {"value": "other"}]
        sync._er_event_types_cache = []
        mock_er_client._post.return_value = [
            {"event_type": "ca_cm_a", "v2_schema": {}, "warnings": [], "errors": []}
        ]
        mock_er_client.get_event_types.return_value = [{"value": "ca_cm_a"}]

        ok = sync._migrate_legacy_for([self._et("ca_cm_a"), self._et("ca_cm_b")])

        assert ok is True
        mock_er_client._post.assert_called_once_with(
            path=self.MIGRATE_PATH,
            payload={"dry_run": False, "event_types": ["ca_cm_a"]},
            base_url=mock_er_client._api_root.return_value,
        )
        mock_er_client._api_root.assert_called_with("v2.0")
        assert sync.datamodel_stats["event_types_migrated"] == 1
        assert sync.datamodel_stats["event_types_migrate_errored"] == 0
        assert sync._er_v1_event_types_cache == [{"value": "other"}]
        mock_er_client.get_event_types.assert_called_with(
            include_inactive=True, include_schema=True, version="v2"
        )
        assert sync._er_event_types_cache == [{"value": "ca_cm_a"}]

    def test_no_collisions_makes_no_call(self, sync_config_v2, mock_er_client):
        sync = self._sync(sync_config_v2, mock_er_client)
        sync._er_v1_event_types_cache = [{"value": "other"}]
        assert sync._migrate_legacy_for([self._et("ca_cm_a")]) is True
        mock_er_client._post.assert_not_called()

    def test_disabled_makes_no_call(self, sync_config_v2, mock_er_client):
        sync_config_v2.earthranger.migrate_legacy_v1 = False
        sync = self._sync(sync_config_v2, mock_er_client)
        sync._er_v1_event_types_cache = [{"value": "ca_cm_a"}]
        assert sync._migrate_legacy_for([self._et("ca_cm_a")]) is True
        mock_er_client._post.assert_not_called()

    def test_migration_error_aborts_push(self, sync_config_v2, mock_er_client):
        sync = self._sync(sync_config_v2, mock_er_client)
        sync._er_v1_event_types_cache = [{"value": "ca_cm_a"}, {"value": "ca_cm_b"}]
        mock_er_client._post.return_value = [
            {"event_type": "ca_cm_a", "v2_schema": {}, "warnings": [], "errors": []},
            {
                "event_type": "ca_cm_b",
                "v2_schema": None,
                "warnings": [],
                "errors": [{"code": "version_validation", "message": "not V1"}],
            },
        ]
        ok = sync._migrate_legacy_for([self._et("ca_cm_a"), self._et("ca_cm_b")])
        assert ok is False
        assert sync.datamodel_stats["event_types_migrated"] == 1
        assert sync.datamodel_stats["event_types_migrate_errored"] == 1
        # The converted one leaves the v1 snapshot; the failed one stays for the retry.
        assert sync._er_v1_event_types_cache == [{"value": "ca_cm_b"}]

    def test_dry_run_client_result_is_ignored(self, sync_config_v2, mock_er_client):
        sync = self._sync(sync_config_v2, mock_er_client)
        sync._er_v1_event_types_cache = [{"value": "ca_cm_a"}]
        mock_er_client._post.return_value = {"id": "dry-run", "dry_run": True}
        assert sync._migrate_legacy_for([self._et("ca_cm_a")]) is True
        assert sync.datamodel_stats["event_types_migrated"] == 0
        assert sync.datamodel_stats["event_types_migrate_errored"] == 0

    def test_push_aborts_before_event_types_when_migration_fails(
        self, sync_config_v2, mock_er_client
    ):
        sync = self._sync(sync_config_v2, mock_er_client)
        sync._er_v1_event_types_cache = [{"value": "x"}]
        mock_er_client._post.return_value = [
            {"event_type": "x", "v2_schema": None, "warnings": [], "errors": [{"code": "e", "message": "m"}]}
        ]
        dm = MagicMock()
        dm.export_as_dict.return_value = {"categories": [], "attributes": []}
        with (
            patch(
                "er_smart_sync.synchronizer.build_event_types_v2",
                return_value=[self._et("x")],
            ),
            patch.object(sync, "create_or_update_er_event_types") as create_mock,
        ):
            sync.push_smart_ca_datamodel_to_earthranger(
                dm=dm, smart_ca_uuid="uuid", ca_identifier="TEST"
            )
        create_mock.assert_not_called()

    def test_synchronize_datamodel_snapshots_and_clears_v1_cache(
        self, sync_config_v2, mock_er_client
    ):
        sync_config_v2.smart.ca_uuids = ["ca-1"]
        sync = self._sync(sync_config_v2, mock_er_client)
        mock_er_client.get_event_types.return_value = []
        seen = {}

        def fake_push(**kwargs):
            seen["v1_cache"] = sync._er_v1_event_types_cache

        with patch.object(sync, "push_smart_datamodel_to_earthranger", side_effect=fake_push):
            sync.synchronize_datamodel()

        assert seen["v1_cache"] == []
        assert sync._er_v1_event_types_cache is None
        versions = [c.kwargs.get("version") for c in mock_er_client.get_event_types.call_args_list]
        assert versions == ["v2", "v1"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_synchronizer.py -q -k LegacyV1`
Expected: FAIL with `AttributeError: 'ERSmartSynchronizer' object has no attribute '_fetch_legacy_v1_snapshot'` and similar.

- [ ] **Step 3: Implement**

In `src/er_smart_sync/synchronizer.py`, after the `_NON_RETRIABLE_ER_MESSAGE_SUBSTRINGS` block (line 66) add:

```python
# ER's server-side v1 -> v2 event type conversion. Versionless path under
# the v2 API root; `dry_run` defaults to true server-side, so it is always
# sent explicitly.
_MIGRATE_PATH = "activity/eventtypes/migrate/"
```

In `__init__`, after `self._er_event_types_cache: list | None = None` (line 198):

```python
        # v1 event types still in the tenant, snapshotted once per datamodel
        # run; None outside a run. Only populated for v2 pushes with
        # migrate_legacy_v1 on.
        self._er_v1_event_types_cache: list | None = None
```

and add two keys to `datamodel_stats` after `"event_types_errored": 0,`:

```python
            "event_types_migrated": 0,
            "event_types_migrate_errored": 0,
```

In `synchronize_datamodel`, after the v2 snapshot assignment (line 274) add:

```python
        self._er_v1_event_types_cache = self._fetch_legacy_v1_snapshot()
```

and in its `finally:` block add `self._er_v1_event_types_cache = None` after the other two resets.

In `push_smart_ca_datamodel_to_earthranger`, directly after the v2 `event_types = build_event_types_v2(...)` call (ends line 408) add:

```python
            if not self._migrate_legacy_for(event_types):
                return
```

Add these methods after `push_smart_ca_datamodel_to_earthranger` (before `calculate_event_category_value`):

```python
    # ──────────────────────────────────────────────
    # Legacy v1 -> v2 conversion
    # ──────────────────────────────────────────────

    def _migration_enabled(self) -> bool:
        return (
            self._event_type_version == "v2"
            and self.config.earthranger.migrate_legacy_v1
        )

    def _fetch_legacy_v1_snapshot(self) -> list:
        """v1 event types in the tenant, or [] when none can be listed.

        After EarthRanger's v1 sunset the v1 list endpoint stops answering.
        That must not block the v2 push, so a failure degrades to "nothing
        to migrate" with a warning.
        """
        if not self._migration_enabled():
            return []
        try:
            return (
                self.er_client.get_event_types(
                    include_inactive=True, include_schema=False, version="v1"
                )
                or []
            )
        except Exception:
            logger.warning(
                "Could not list v1 event types; skipping legacy migration this run",
                exc_info=True,
            )
            return []

    def migrate_legacy_event_types(self, values: list[str]) -> list[dict]:
        """Convert the given v1 event type values to v2 in place.

        Returns ER's per-type results, each
        ``{"event_type", "v2_schema", "warnings", "errors", "metadata"}``.
        An empty ``errors`` list means the record is now v2. A non-list
        response (the dry-run client) is treated as no results.
        """
        logger.info(
            "Migrating %d legacy v1 event types to v2",
            len(values),
            extra=dict(values=values),
        )
        results = _retry(
            self.er_client._post,
            path=_MIGRATE_PATH,
            payload={"dry_run": False, "event_types": list(values)},
            base_url=self.er_client._api_root("v2.0"),
        )
        return results if isinstance(results, list) else []

    def _migrate_legacy_for(self, event_types) -> bool:
        """Migrate v1 records whose value collides with ``event_types``.

        Returns False when any migration failed, so the caller aborts this
        CA's push (same policy as a choice-upsert error) and the next
        scheduled run retries. Values not in the v1 snapshot, including
        inactive SMART categories and hand-made types, are never sent.
        """
        if not self._migration_enabled() or not self._er_v1_event_types_cache:
            return True
        v1_values = {x.get("value") for x in self._er_v1_event_types_cache}
        targets = [et.value for et in event_types if et.value in v1_values]
        if not targets:
            return True

        results = self.migrate_legacy_event_types(targets)
        migrated = [r.get("event_type") for r in results if not r.get("errors")]
        failed = [r for r in results if r.get("errors")]
        self.datamodel_stats["event_types_migrated"] += len(migrated)
        self.datamodel_stats["event_types_migrate_errored"] += len(failed)

        for r in failed:
            logger.error(
                "Legacy v1 event type %r could not be migrated: %s",
                r.get("event_type"),
                [e.get("message") for e in r.get("errors", [])],
                extra=dict(value=r.get("event_type"), errors=r.get("errors")),
            )
        if migrated:
            logger.info(
                "Migrated %d legacy v1 event types: %s",
                len(migrated),
                migrated,
            )
            self._er_v1_event_types_cache = [
                x for x in self._er_v1_event_types_cache
                if x.get("value") not in migrated
            ]
            # The converted records are v2 now; refresh so compare-and-patch
            # sees them instead of attempting a conflicting POST.
            if self._er_event_types_cache is not None:
                self._er_event_types_cache = self.er_client.get_event_types(
                    include_inactive=True, include_schema=True, version="v2"
                )
        if failed:
            logger.warning(
                "Aborting event-type push for this CA: %d legacy v1 event "
                "types failed to migrate. Fix them in ER (or run with "
                "migrate_legacy_v1 off) and re-run.",
                len(failed),
            )
            return False
        return True
```

- [ ] **Step 4: Run the suite**

Run: `pytest -q && ruff check src tests && ruff format --check src tests`
Expected: all passed. If `test_cli.py` fakes build `datamodel_stats` by hand (see `fake_make_sync` around line 713), they still pass because `_print_datamodel_summary` iterates whatever dict it is given.

- [ ] **Step 5: Commit**

```bash
git add src/er_smart_sync/synchronizer.py tests/test_synchronizer.py
git commit -m "Migrate colliding v1 event types before the v2 push

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: CLI flag, docs, changelog, release

**Files:**
- Modify: `src/er_smart_sync/cli.py` (datamodel options at `:377-384`, signature at `:386-411`, overrides at `:428-432`)
- Modify: `docs/cli-reference/datamodel.md:28`
- Modify: `docs/concepts/event-type-version.md:114-121`
- Modify: `docs/troubleshooting.md:109-121`
- Modify: `docs/changelog.md:9`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `EarthRangerConfig.migrate_legacy_v1` (Task 2).
- Produces: `er-smart-sync datamodel --no-migrate-legacy-v1`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cli.py`:

```python
def test_datamodel_help_lists_no_migrate_legacy_v1():
    runner = CliRunner()
    result = runner.invoke(main, ["datamodel", "--help"])
    assert result.exit_code == 0
    assert "--no-migrate-legacy-v1" in result.output


def test_no_migrate_legacy_v1_flag_disables_config(tmp_path, monkeypatch):
    captured = {}

    def fake_make_sync(config, ctx=None):
        from er_smart_sync.synchronizer import ERSmartSynchronizer

        sync = ERSmartSynchronizer.__new__(ERSmartSynchronizer)
        sync.datamodel_stats = {}
        sync.push_smart_ca_datamodel_to_earthranger = lambda **kwargs: None
        sync.synchronize_datamodel = lambda: None
        captured["config"] = config
        return sync

    monkeypatch.setattr("er_smart_sync.cli._make_synchronizer", fake_make_sync)
    monkeypatch.setattr(
        "smartconnect.SmartClient.load_datamodel", lambda self, filename: MagicMock()
    )
    dm_file = tmp_path / "dm.xml"
    dm_file.write_text("<datamodel/>")

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "datamodel",
            "--from-file", str(dm_file),
            "--er-endpoint", "https://x/api/v1.0",
            "--er-token", "t",
            "--er-id", "i",
            "--ca-identifier", "TEST",
            "--no-migrate-legacy-v1",
        ],
    )
    assert result.exit_code == 0, result.output
    assert captured["config"].earthranger.migrate_legacy_v1 is False
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_cli.py -q -k migrate_legacy`
Expected: the help test fails on the missing flag; the second exits non-zero with "No such option".

- [ ] **Step 3: Add the flag**

In `src/er_smart_sync/cli.py`, after the `--skip-choices` option (ends line 384):

```python
@click.option(
    "--no-migrate-legacy-v1",
    "no_migrate_legacy_v1",
    is_flag=True,
    default=False,
    help=(
        "Do not convert colliding v1 event types via ER's migrate endpoint "
        "before pushing (v2 only). Default: migrate them."
    ),
)
```

Add `no_migrate_legacy_v1,` as the last parameter of `def datamodel(...)` after `skip_choices,`, and after the `cm_variant_mode` override (line 432):

```python
    if no_migrate_legacy_v1:
        config.earthranger.migrate_legacy_v1 = False
```

- [ ] **Step 4: Update the docs**

`docs/cli-reference/datamodel.md`, after the `--skip-choices` row:

```markdown
| `--no-migrate-legacy-v1` | off | Do not convert colliding v1 event types via ER's migrate endpoint before pushing (v2 only). By default they are migrated in place so historical events stay attached. |
```

`docs/concepts/event-type-version.md`, replace the "Migrating between versions" section (from the heading to the "Related" heading) with:

```markdown
## Migrating between versions

EarthRanger's event-type `value` is unique tenant-wide **across both
versions**, so a value that exists as v1 cannot be POSTed as v2.

When `event_type_version` is `v2` and `migrate_legacy_v1` is on (the
default), the datamodel sync lists the tenant's v1 event types once per
run and, for each CA push, sends the values it is about to write that
still exist as v1 to EarthRanger's server-side converter:

```
POST /api/v2.0/activity/eventtypes/migrate/
{"dry_run": false, "event_types": ["<value>", ...]}
```

The record flips to v2 in place and keeps its historical events. ER
converts the inline enums into its own Choice lists; the following
compare-and-patch step rewrites the schema to reference the library's
shared `dm…` lists, so ER's generated lists stay behind active but
unreferenced, like legacy `et…` lists. Only values that start with the
CA (and CM) UUID can collide, so hand-made v1 types are never touched.

A failed conversion aborts that CA's push (`event_types_migrate_errored`
in the run summary) and the next run retries. Pass
`--no-migrate-legacy-v1` or set `migrate_legacy_v1: false` to leave v1
records alone; the push then skips colliding values with a warning.
```

`docs/troubleshooting.md`, in "Duplicate-key conflict on event-type POST", replace the paragraph starting "`er-smart-sync` doesn't wrap this endpoint yet" with:

```markdown
Since 0.5.0 the datamodel sync does this for you when `event_type_version`
is `v2` and `migrate_legacy_v1` is on (the default). If you see this
warning on a v2 run, the flag is off or the migrate call failed earlier in
the log; look for `could not be migrated`.
```

`docs/changelog.md`, insert before the `## 0.4.0 — 2026-09-28` heading:

```markdown
## 0.5.0 — <release date>

### Added

**Colliding v1 event types are migrated before a v2 push.** With
`event_type_version: v2`, the datamodel sync now calls EarthRanger's
`POST /api/v2.0/activity/eventtypes/migrate/` for SMART-derived values
that still exist as v1, then patches them to the library's schema.
Controlled by `migrate_legacy_v1` (default on) and
`--no-migrate-legacy-v1`. New run-summary counters
`event_types_migrated` and `event_types_migrate_errored`.

### Changed

**Choice value rules now come from smartconnect-client.**
`sanitize_choice_value` and the over-100-character hash shortening are
imported from `smartconnect.choices` (smartconnect-client ≥ 1.15.0) so
cdip-routing can apply the inverse lookup from one definition. Output is
byte-for-byte unchanged.
```

Fill in the release date when tagging.

- [ ] **Step 5: Run the suite and docs build**

Run: `pytest -q && ruff check src tests && ruff format --check src tests && mkdocs build -q`
Expected: all passed; docs build without warnings about the edited pages.

- [ ] **Step 6: Commit, PR, release**

```bash
git add src/er_smart_sync/cli.py docs tests/test_cli.py
git commit -m "Add --no-migrate-legacy-v1 and document legacy migration

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
git push -u origin feature/legacy-v1-migration
gh pr create --title "0.5.0: migrate colliding v1 event types, shared choice rules" --body "$(cat <<'BODY'
- Datamodel sync migrates SMART-derived v1 event types that collide with the v2 push via ER's migrate endpoint, then patches them to the library schema. `migrate_legacy_v1` config (default on), `--no-migrate-legacy-v1` CLI flag, two new run-summary counters.
- Choice value rules are imported from smartconnect-client 1.15.0 so cdip-routing's inverse lookup shares one definition.

Spec: PADAS/cdip docs/superpowers/specs/2026-10-09-er-smart-sync-v2-migration-design.md

🤖 Generated with [Claude Code](https://claude.com/claude-code)
BODY
)"
```

After merge: set the changelog date in a follow-up commit if needed, then

```bash
git checkout main && git pull
git tag v0.5.0 && git push origin v0.5.0
```

and confirm `pip index versions er-smart-sync` shows 0.5.0. Part 4 depends on it.
