# ER v2 migration, part 4 of 4: Gundi Portal adopts er-smart-sync

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the portal's `ER_SMART_Synchronizer` with er-smart-sync 0.5.1 so every SMART-to-ER integration pushes v2 event types, migrating existing v1 ones in place, while the Celery tasks, queue and schedules stay as they are.

**Architecture:** `sync_integrations/er_smart_sync.py` shrinks to two factory functions that map the Django integration rows to the library's `SyncConfig` and build an `ERSmartSynchronizer` with four portal adapters: the existing GooglePublisher and cloud storage, a new Redis state store on the existing key, and a new tracing adapter over `core.tracing`. `tasks.py` keeps every task name and the datamodels-to-events-to-patrols chain, each task calling one library method. The old synchronizer, its tests and the dasclient-based management command are deleted.

**Tech Stack:** Django 4.2, Celery, Redis, pytest-django (Postgres test DB). Python 3.11 venv at `/Users/chrisdo/padas/cdip/.venv`. Work happens in this worktree on branch `chore/upgrade-smart-sync-event-types`.

**Spec:** `docs/superpowers/specs/2026-10-09-er-smart-sync-v2-migration-design.md`, section "4. cdip (this repo)". Depends on part 2 (er-smart-sync 0.5.1 on PyPI) and on part 3 being deployed before the prod rollout.

## Global Constraints

- `dependencies/requirements.in`: remove the `dasclient` and `smartconnect_client` GitHub wheel lines (currently lines 78 and 79), add `er-smart-sync==0.5.1`. `requirements.txt` is regenerated.
- Event type version is the Django setting `ER_SMART_SYNC_EVENT_TYPE_VERSION`, env-overridable, default `"v2"`. No per-integration knob.
- `cm_variant_mode` is always `"split"`; `migrate_legacy_v1` is always `True`.
- Redis state key stays `er.function.state.{integration_id}`; the stored JSON shape (`event_last_poll_at`, `patrol_last_poll_at`) is unchanged.
- Task names, the `QueueOnce` bases, the 1800 s soft time limits, the `smartsyncs` routing in `settings.CELERY_TASK_ROUTES`, and the `sync_er_smart_datamodels -> sync_er_events -> sync_er_patrols` chain are unchanged.
- Provider key passed to ER is the SMART outbound type slug, `smart_connect`, as today.

## Review Focus

1. A SMART integration whose `additional` lacks `version` (older rows) must produce the library default `"7.0"`, not `None`. Pinned in Task 4.
2. A Redis key written by the old code (`EarthRangerReaderState.json()`, timezone-aware ISO strings) must parse into `SyncState` without a backfill. Pinned in Task 2.
3. `synchronize_smart_datamodels(integration_id)` reads `additional["er_integration_id"]`; a missing or malformed id must log and return, not raise. Pinned in Task 5.
4. The env override `ER_SMART_SYNC_EVENT_TYPE_VERSION=v1` must reach the library config. Pinned in Task 4.
5. An ER integration configured with login and password but no token must pass both through so `ERClient` can fall back to OAuth. Pinned in Task 4.

## Test command

Tests need the local Postgres (see `/Users/chrisdo/.claude/projects/-Users-chrisdo-padas-cdip/memory/project_local_pytest_settings.md`). From this worktree:

```bash
cp /Users/chrisdo/padas/cdip/cdip_admin/cdip_admin/local_settings.py cdip_admin/cdip_admin/local_settings.py   # once; gitignored
cd cdip_admin
DB_HOST=localhost DB_PORT=5432 DB_USER=cdip_dbuser DB_PASSWORD=cdip_dbpassword DB_NAME=cdip_smartsync \
  /Users/chrisdo/padas/cdip/.venv/bin/python -m pytest sync_integrations -q --create-db
```

Use `--reuse-db` after the first run. Start Postgres with `docker compose up -d postgres` from the main checkout if `cdip-postgres` is not running. The command below is abbreviated as `pytest sync_integrations` in the tasks.

---

### Task 1: Dependencies

**Files:**
- Modify: `dependencies/requirements.in:78-79`
- Regenerate: `dependencies/requirements.txt`

- [ ] **Step 1: Edit `requirements.in`**

Delete the two lines

```
https://github.com/PADAS/das-clients/releases/download/v.1.0.40/dasclient-1.0.40-py3-none-any.whl
https://github.com/PADAS/smartconnect-client/releases/download/v1.11.0/smartconnect_client-1.11.0-py3-none-any.whl
```

and in their place add

```
er-smart-sync==0.5.1
```

- [ ] **Step 2: Regenerate `requirements.txt`**

The repo's `cryptography==2.9.2` pin has no macOS arm64 wheel, so compile in the same image the Dockerfile uses:

```bash
docker run --rm --platform linux/amd64 -v "$PWD/dependencies:/deps" -w /deps python:3.11-slim \
  sh -c "pip install -q pip-tools && pip-compile -q --output-file=requirements.txt requirements.in"
git diff --stat dependencies/requirements.txt
grep -nE "^(er-smart-sync|smartconnect-client|earthranger-client|gpxpy|dasclient)" dependencies/requirements.txt
```

Expected: `er-smart-sync==0.5.1`, `smartconnect-client==1.15.0` (or newer 1.x), `earthranger-client==1.15.0` (or newer), `gpxpy==1.6.2`; no `dasclient` line; no other pins change. A narrow dry run against the current pins on 2026-10-09 produced exactly these additions.

- [ ] **Step 3: Install into the venv**

```bash
/Users/chrisdo/padas/cdip/.venv/bin/pip install "er-smart-sync==0.5.1"
/Users/chrisdo/padas/cdip/.venv/bin/python -c "import er_smart_sync, smartconnect, erclient; print('ok')"
```

Expected: `ok`. (The venv is shared with the main checkout; `dasclient` stays installed there, which is harmless.)

- [ ] **Step 4: Commit**

```bash
git add dependencies/requirements.in dependencies/requirements.txt
git commit -m "Depend on er-smart-sync instead of dasclient and the smartconnect wheel

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: Redis state store

**Files:**
- Create: `cdip_admin/sync_integrations/state.py`
- Test: `cdip_admin/sync_integrations/tests/test_state.py`

**Interfaces:**
- Consumes: `sync_integrations.cache.cache` (a `redis.Redis`), `er_smart_sync.state.SyncState`.
- Produces: `RedisStateStore(client=None)` with `get_last_poll(integration_id) -> SyncState` and `set_last_poll(integration_id, state) -> None`; constant `STATE_KEY_BASE = "er.function.state"`.

- [ ] **Step 1: Write the failing tests**

```python
# cdip_admin/sync_integrations/tests/test_state.py
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest sync_integrations/tests/test_state.py`
Expected: `ModuleNotFoundError: No module named 'sync_integrations.state'`

- [ ] **Step 3: Implement**

```python
# cdip_admin/sync_integrations/state.py
"""er-smart-sync StateStore backed by the portal's Redis.

Keeps the key and JSON shape the previous synchronizer used
(``er.function.state.<integration_id>`` holding ``event_last_poll_at`` and
``patrol_last_poll_at``), so last-poll timestamps carry over with no
backfill.
"""
from er_smart_sync.state import SyncState

from sync_integrations.cache import cache

STATE_KEY_BASE = "er.function.state"


class RedisStateStore:
    def __init__(self, client=None):
        self._client = client if client is not None else cache

    @staticmethod
    def _key(integration_id: str) -> str:
        return f"{STATE_KEY_BASE}.{integration_id}"

    def get_last_poll(self, integration_id: str) -> SyncState:
        raw = self._client.get(self._key(integration_id))
        return SyncState.parse_raw(raw) if raw else SyncState()

    def set_last_poll(self, integration_id: str, state: SyncState) -> None:
        self._client.set(self._key(integration_id), state.json())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest sync_integrations/tests/test_state.py`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add cdip_admin/sync_integrations/state.py cdip_admin/sync_integrations/tests/test_state.py
git commit -m "Add Redis-backed state store for er-smart-sync

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: Tracing adapter

**Files:**
- Create: `cdip_admin/sync_integrations/tracing.py`
- Test: `cdip_admin/sync_integrations/tests/test_tracing.py`

**Interfaces:**
- Consumes: `core.tracing.tracer`, `core.tracing.instrumentation.build_context_headers`.
- Produces: `PortalTracing` with `start_span(name, kind="producer")` (context manager yielding an OpenTelemetry span) and `build_context_headers() -> dict`.

- [ ] **Step 1: Write the failing tests**

```python
# cdip_admin/sync_integrations/tests/test_tracing.py
from sync_integrations.tracing import PortalTracing


def test_start_span_yields_a_span_that_accepts_attributes_and_events():
    with PortalTracing().start_span("gundi_er_smart_sync.process_event", kind="producer") as span:
        span.set_attribute("is_patrol_event", True)
        span.add_event("gundi_er_smart_sync.event_sent_to_routing")


def test_unknown_kind_falls_back_to_internal():
    with PortalTracing().start_span("x", kind="not-a-kind"):
        pass


def test_build_context_headers_returns_a_dict():
    assert isinstance(PortalTracing().build_context_headers(), dict)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest sync_integrations/tests/test_tracing.py`
Expected: `ModuleNotFoundError: No module named 'sync_integrations.tracing'`

- [ ] **Step 3: Implement**

```python
# cdip_admin/sync_integrations/tracing.py
"""er-smart-sync TracingProvider over the portal's OpenTelemetry tracer."""
from contextlib import contextmanager

from opentelemetry import trace

from core import tracing

_SPAN_KINDS = {
    "producer": trace.SpanKind.PRODUCER,
    "consumer": trace.SpanKind.CONSUMER,
    "client": trace.SpanKind.CLIENT,
    "server": trace.SpanKind.SERVER,
    "internal": trace.SpanKind.INTERNAL,
}


class PortalTracing:
    @contextmanager
    def start_span(self, name: str, kind: str = "producer"):
        span_kind = _SPAN_KINDS.get(kind, trace.SpanKind.INTERNAL)
        with tracing.tracer.start_as_current_span(name, kind=span_kind) as span:
            yield span

    def build_context_headers(self) -> dict:
        return tracing.instrumentation.build_context_headers()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest sync_integrations/tests/test_tracing.py`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add cdip_admin/sync_integrations/tracing.py cdip_admin/sync_integrations/tests/test_tracing.py
git commit -m "Add tracing adapter for er-smart-sync

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: Config factory replaces the synchronizer

**Files:**
- Rewrite: `cdip_admin/sync_integrations/er_smart_sync.py` (841 lines become ~80)
- Delete: `cdip_admin/sync_integrations/tests/test_er_smart_sync.py`
- Modify: `cdip_admin/cdip_admin/settings.py` (after `RAW_OBSERVATIONS_TOPIC`, line 477)
- Test: `cdip_admin/sync_integrations/tests/test_sync_config.py`

**Interfaces:**
- Consumes: `RedisStateStore` (Task 2), `PortalTracing` (Task 3), `core.utils.get_publisher`, `cdip_connector.core.cloudstorage.get_cloud_storage`, `er_smart_sync.config.{SyncConfig, SmartConnectConfig, EarthRangerConfig}`, `er_smart_sync.synchronizer.ERSmartSynchronizer`.
- Produces:
  - `build_sync_config(*, smart_config, er_config) -> SyncConfig`
  - `build_synchronizer(*, smart_config, er_config) -> ERSmartSynchronizer`
  - setting `ER_SMART_SYNC_EVENT_TYPE_VERSION`

- [ ] **Step 1: Write the failing tests**

```python
# cdip_admin/sync_integrations/tests/test_sync_config.py
import pytest

from sync_integrations.er_smart_sync import build_sync_config, build_synchronizer

pytestmark = pytest.mark.django_db


@pytest.fixture
def smart_integration(outbound_integration_smart):
    outbound_integration_smart.login = "smart-user"
    outbound_integration_smart.password = "smart-pass"  # pragma: allowlist secret
    outbound_integration_smart.additional = {
        "version": "7.5.7",
        "use_language_code": "es",
        "ca_uuids": ["ca-1"],
        "configurable_models_lists": {"ca-1": [{"uuid": "cm-1", "name": "CM", "use_with_earth_ranger": True}]},
    }
    outbound_integration_smart.save()
    return outbound_integration_smart


@pytest.fixture
def er_integration(inbound_integration_er):
    inbound_integration_er.endpoint = "https://site.pamdas.org/api/v1.0"
    inbound_integration_er.token = "er-token"  # pragma: allowlist secret
    inbound_integration_er.save()
    return inbound_integration_er


def test_maps_smart_side(smart_integration, er_integration):
    config = build_sync_config(smart_config=smart_integration, er_config=er_integration)
    assert config.smart.endpoint == smart_integration.endpoint
    assert config.smart.login == "smart-user"
    assert config.smart.password == "smart-pass"
    assert config.smart.version == "7.5.7"
    assert config.smart.use_language_code == "es"
    assert config.smart.ca_uuids == ["ca-1"]
    assert config.smart.configurable_models_lists == smart_integration.additional["configurable_models_lists"]
    assert config.smart.provider_key == "smart_connect"


def test_maps_er_side_with_fixed_policy(smart_integration, er_integration, settings):
    settings.ER_SMART_SYNC_EVENT_TYPE_VERSION = "v2"
    config = build_sync_config(smart_config=smart_integration, er_config=er_integration)
    assert config.earthranger.id == str(er_integration.id)
    assert config.earthranger.endpoint == "https://site.pamdas.org/api/v1.0"
    assert config.earthranger.token == "er-token"
    assert config.earthranger.event_type_version == "v2"
    assert config.earthranger.cm_variant_mode == "split"
    assert config.earthranger.migrate_legacy_v1 is True


def test_event_type_version_setting_override(smart_integration, er_integration, settings):
    settings.ER_SMART_SYNC_EVENT_TYPE_VERSION = "v1"
    config = build_sync_config(smart_config=smart_integration, er_config=er_integration)
    assert config.earthranger.event_type_version == "v1"


def test_missing_smart_version_defaults(smart_integration, er_integration):
    smart_integration.additional = {"ca_uuids": ["ca-1"]}
    config = build_sync_config(smart_config=smart_integration, er_config=er_integration)
    assert config.smart.version == "7.0"
    assert config.smart.use_language_code == "en"
    assert config.smart.configurable_models_lists == {}


def test_er_login_password_without_token(smart_integration, er_integration):
    er_integration.token = ""
    er_integration.login = "er-user"
    er_integration.password = "er-pass"  # pragma: allowlist secret
    config = build_sync_config(smart_config=smart_integration, er_config=er_integration)
    assert config.earthranger.token == ""
    assert config.earthranger.login == "er-user"
    assert config.earthranger.password == "er-pass"


def test_build_synchronizer_wires_portal_adapters(mocker, smart_integration, er_integration, settings):
    from sync_integrations.state import RedisStateStore
    from sync_integrations.tracing import PortalTracing

    settings.RAW_OBSERVATIONS_TOPIC = "raw-observations-test"
    publisher = mocker.MagicMock()
    storage = mocker.MagicMock()
    mocker.patch("sync_integrations.er_smart_sync.get_publisher", return_value=publisher)
    mocker.patch("sync_integrations.er_smart_sync.get_cloud_storage", return_value=storage)
    er_client_cls = mocker.patch("er_smart_sync.synchronizer.ERClient")
    smart_client_cls = mocker.patch("er_smart_sync.synchronizer.SmartClient")

    sync = build_synchronizer(smart_config=smart_integration, er_config=er_integration)

    assert sync.publisher is publisher
    assert sync.file_storage is storage
    assert isinstance(sync.state_store, RedisStateStore)
    assert isinstance(sync.tracing, PortalTracing)
    assert sync.observations_topic == "raw-observations-test"
    er_client_cls.assert_called_once()
    assert er_client_cls.call_args.kwargs["provider_key"] == "smart_connect"
    smart_client_cls.assert_called_once()
    assert smart_client_cls.call_args.kwargs["version"] == "7.5.7"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest sync_integrations/tests/test_sync_config.py`
Expected: `ImportError: cannot import name 'build_sync_config'`

- [ ] **Step 3: Add the setting**

In `cdip_admin/cdip_admin/settings.py` after `RAW_OBSERVATIONS_TOPIC` (line 477):

```python
# EarthRanger event type API version used when pushing SMART data models.
# v1 writes end with ER's 2026-10-15 sunset; keep "v2" unless an emergency
# rollback for one environment is needed before that date.
ER_SMART_SYNC_EVENT_TYPE_VERSION = env.str("ER_SMART_SYNC_EVENT_TYPE_VERSION", default="v2")
```

- [ ] **Step 4: Rewrite `er_smart_sync.py`**

Replace the whole file with:

```python
# cdip_admin/sync_integrations/er_smart_sync.py
"""Glue between portal integration rows and the er-smart-sync library.

The synchronizer itself (SMART data models -> ER event types, ER events and
patrols -> SMART via routing) lives in er-smart-sync. This module only maps
the Django configuration into the library's config and plugs in the
portal's publisher, storage, Redis state and tracing.
"""
import logging

from cdip_connector.core.cloudstorage import get_cloud_storage
from django.conf import settings
from er_smart_sync.config import EarthRangerConfig, SmartConnectConfig, SyncConfig
from er_smart_sync.synchronizer import ERSmartSynchronizer

from core.utils import get_publisher
from sync_integrations.state import RedisStateStore
from sync_integrations.tracing import PortalTracing

logger = logging.getLogger(__name__)


def build_sync_config(*, smart_config, er_config) -> SyncConfig:
    """Map a SMART outbound configuration and an ER inbound configuration.

    Policy is fixed here rather than per integration: event type version from
    settings (v2), one ER event type per configurable-model node (split), and
    legacy v1 types migrated in place before each push.
    """
    additional = smart_config.additional or {}
    smart = SmartConnectConfig(
        endpoint=smart_config.endpoint,
        login=smart_config.login,
        password=smart_config.password,
        version=additional.get("version") or "7.0",
        use_language_code=additional.get("use_language_code") or "en",
        ca_uuids=additional.get("ca_uuids") or [],
        configurable_models_lists=additional.get("configurable_models_lists") or {},
        provider_key=smart_config.type.slug,
    )
    earthranger = EarthRangerConfig(
        id=str(er_config.id),
        endpoint=er_config.endpoint,
        login=er_config.login,
        password=er_config.password,
        token=er_config.token,
        event_type_version=settings.ER_SMART_SYNC_EVENT_TYPE_VERSION,
        cm_variant_mode="split",
        migrate_legacy_v1=True,
    )
    return SyncConfig(smart=smart, earthranger=earthranger)


def build_synchronizer(*, smart_config, er_config) -> ERSmartSynchronizer:
    return ERSmartSynchronizer(
        config=build_sync_config(smart_config=smart_config, er_config=er_config),
        publisher=get_publisher(),
        file_storage=get_cloud_storage(),
        state_store=RedisStateStore(),
        tracing=PortalTracing(),
        observations_topic=settings.RAW_OBSERVATIONS_TOPIC,
    )
```

Delete `cdip_admin/sync_integrations/tests/test_er_smart_sync.py` (it tests the removed class). The `mock_das_client`, `das_client_*_response` and `mock_last_poll` fixtures in `cdip_admin/conftest.py` lose their only users; leave them, they are inert.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest sync_integrations/tests/test_sync_config.py`
Expected: 6 passed. `tasks.py` still imports `ER_SMART_Synchronizer` at this point and fails to import; that is fixed in Task 5, so run only this file here.

- [ ] **Step 6: Commit**

```bash
git add cdip_admin/sync_integrations/er_smart_sync.py cdip_admin/cdip_admin/settings.py cdip_admin/sync_integrations/tests/test_sync_config.py
git rm -q cdip_admin/sync_integrations/tests/test_er_smart_sync.py
git commit -m "Replace ER_SMART_Synchronizer with er-smart-sync config factory

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: Tasks and management commands

**Files:**
- Modify: `cdip_admin/sync_integrations/tasks.py` (import at `:13`; `synchronize_smart_datamodels` at `:58-68`; `sync_er_smart_datamodels` at `:126-161`; `sync_er_events` at `:163-197`; `sync_er_patrols` at `:199-233`)
- Modify: `cdip_admin/sync_integrations/management/commands/runsync_command.py:9,62-66`
- Delete: `cdip_admin/sync_integrations/management/commands/sync_datamodel_to_er.py`
- Test: `cdip_admin/sync_integrations/tests/test_tasks.py`

**Interfaces:**
- Consumes: `build_synchronizer` (Task 4); library methods `synchronize_datamodel()`, `sync_patrol_datamodel()`, `synchronize_er_events()`, `synchronize_er_patrols()`.
- Produces: unchanged task names and signatures.

- [ ] **Step 1: Write the failing tests**

```python
# cdip_admin/sync_integrations/tests/test_tasks.py
import pytest

from sync_integrations import tasks

pytestmark = pytest.mark.django_db


@pytest.fixture
def synchronizer(mocker):
    sync = mocker.MagicMock()
    mocker.patch("sync_integrations.tasks.build_synchronizer", return_value=sync)
    return sync


def _ids(outbound_integration_smart, inbound_integration_er):
    return dict(
        smart_integration_id=str(outbound_integration_smart.id),
        er_integration_id=str(inbound_integration_er.id),
    )


def test_sync_er_smart_datamodels_runs_both_datamodel_syncs(
    synchronizer, outbound_integration_smart, inbound_integration_er
):
    tasks.sync_er_smart_datamodels(**_ids(outbound_integration_smart, inbound_integration_er))
    tasks.build_synchronizer.assert_called_once_with(
        smart_config=outbound_integration_smart, er_config=inbound_integration_er
    )
    synchronizer.synchronize_datamodel.assert_called_once_with()
    synchronizer.sync_patrol_datamodel.assert_called_once_with()


def test_sync_er_events_runs_event_sync(synchronizer, outbound_integration_smart, inbound_integration_er):
    tasks.sync_er_events(**_ids(outbound_integration_smart, inbound_integration_er))
    synchronizer.synchronize_er_events.assert_called_once_with()


def test_sync_er_patrols_runs_patrol_sync(synchronizer, outbound_integration_smart, inbound_integration_er):
    tasks.sync_er_patrols(**_ids(outbound_integration_smart, inbound_integration_er))
    synchronizer.synchronize_er_patrols.assert_called_once_with()


def test_sync_task_logs_and_returns_when_integration_missing(
    synchronizer, outbound_integration_smart, caplog
):
    tasks.sync_er_events(
        smart_integration_id=str(outbound_integration_smart.id),
        er_integration_id="00000000-0000-0000-0000-000000000000",
    )
    tasks.build_synchronizer.assert_not_called()
    assert "does not exist" in caplog.text


def test_synchronize_smart_datamodels_uses_er_integration_from_additional(
    synchronizer, outbound_integration_smart, inbound_integration_er
):
    outbound_integration_smart.additional = {"er_integration_id": str(inbound_integration_er.id)}
    outbound_integration_smart.save()
    tasks.synchronize_smart_datamodels(str(outbound_integration_smart.id))
    tasks.build_synchronizer.assert_called_once_with(
        smart_config=outbound_integration_smart, er_config=inbound_integration_er
    )
    synchronizer.synchronize_datamodel.assert_called_once_with()


@pytest.mark.parametrize("er_integration_id", [None, "not-a-uuid", "00000000-0000-0000-0000-000000000000"])
def test_synchronize_smart_datamodels_without_valid_er_integration_logs_and_returns(
    synchronizer, outbound_integration_smart, caplog, er_integration_id
):
    outbound_integration_smart.additional = (
        {"er_integration_id": er_integration_id} if er_integration_id is not None else {}
    )
    outbound_integration_smart.save()
    tasks.synchronize_smart_datamodels(str(outbound_integration_smart.id))
    tasks.build_synchronizer.assert_not_called()
    assert "er_integration_id" in caplog.text
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest sync_integrations/tests/test_tasks.py`
Expected: `ImportError: cannot import name 'ER_SMART_Synchronizer' from 'sync_integrations.er_smart_sync'` while collecting `tasks.py`.

- [ ] **Step 3: Update `tasks.py`**

Replace the import on line 13 with:

```python
from django.core.exceptions import ValidationError

from sync_integrations.er_smart_sync import build_synchronizer
```

Replace the body of `synchronize_smart_datamodels` (lines 60 to 68) with:

```python
def synchronize_smart_datamodels(integration_id: str):
    smart_config = OutboundIntegrationConfiguration.objects.get(id=integration_id)
    logger.info('Synchronizing SMART datamodels for %s (%s)', smart_config.name, smart_config.id)

    er_integration_id = (smart_config.additional or {}).get("er_integration_id")
    try:
        er_config = InboundIntegrationConfiguration.objects.get(id=er_integration_id)
    except (InboundIntegrationConfiguration.DoesNotExist, ValidationError, ValueError):
        logger.error(
            "SMART integration %s (%s) has no valid additional.er_integration_id (%r); skipping",
            smart_config.name, smart_config.id, er_integration_id,
        )
        return

    build_synchronizer(smart_config=smart_config, er_config=er_config).synchronize_datamodel()
    logger.info('Finished synchronizing SMART datamodels for %s (%s)', smart_config.name, smart_config.id)
```

In `sync_er_smart_datamodels`, replace the two lines

```python
        er_smart_sync = ER_SMART_Synchronizer(smart_config=smart_integration, er_config=er_configuration)
```
and
```python
        er_smart_sync.synchronize_datamodel()
        er_smart_sync.sync_patrol_datamodel()
```
with
```python
        er_smart_sync = build_synchronizer(smart_config=smart_integration, er_config=er_configuration)
```
and
```python
        er_smart_sync.synchronize_datamodel()
        er_smart_sync.sync_patrol_datamodel()
```
(the second pair is unchanged; only the constructor line changes).

In `sync_er_events`, replace the constructor line the same way and replace
`er_smart_sync.synchronize_er_events_to_smart_connect(config=er_configuration)` with
`er_smart_sync.synchronize_er_events()`.

In `sync_er_patrols`, replace the constructor line the same way and replace
`er_smart_sync.synchronize_er_patrols_to_smart_connect(config=er_configuration)` with
`er_smart_sync.synchronize_er_patrols()`.

Nothing else in the file changes: the lookups, the `enabled=True` and type-slug filters, the log lines and the `except Exception` blocks stay.

- [ ] **Step 4: Update the management commands**

In `runsync_command.py`, change line 9 to `from sync_integrations.er_smart_sync import build_synchronizer` and replace lines 62 to 66 with:

```python
            build_synchronizer(smart_config=smart_config, er_config=er_config).synchronize_datamodel()
```

Delete `cdip_admin/sync_integrations/management/commands/sync_datamodel_to_er.py`: it hard-codes placeholder hosts and tokens and only exists to call the removed class through dasclient.

- [ ] **Step 5: Run the app's whole test package and a Django check**

```bash
pytest sync_integrations
DB_HOST=localhost DB_PORT=5432 DB_USER=cdip_dbuser DB_PASSWORD=cdip_dbpassword DB_NAME=cdip_smartsync \
  /Users/chrisdo/padas/cdip/.venv/bin/python manage.py check
grep -rn "dasclient\|ER_SMART_Synchronizer\|synchronize_er_events_to_smart_connect" --include='*.py' . | grep -v "\.venv"
```

Expected: 18 passed across `test_state.py`, `test_tracing.py`, `test_sync_config.py`, `test_tasks.py`; `System check identified no issues`; the grep prints nothing.

- [ ] **Step 6: Commit**

```bash
git add cdip_admin/sync_integrations/tasks.py cdip_admin/sync_integrations/management/commands/runsync_command.py cdip_admin/sync_integrations/tests/test_tasks.py
git rm -q cdip_admin/sync_integrations/management/commands/sync_datamodel_to_er.py
git commit -m "Run sync tasks through er-smart-sync

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: PR and rollout

- [ ] **Step 1: Open the PR**

```bash
git push -u origin chore/upgrade-smart-sync-event-types
gh pr create --title "Push SMART data models as ER v2 event types via er-smart-sync" --body "$(cat <<'BODY'
Replaces the portal's ER_SMART_Synchronizer with er-smart-sync 0.5.1. Every SMART-to-ER sync now creates v2 event types with ER Choice lists, converting existing SMART-derived v1 types in place through ER's migrate endpoint before ER's 2026-10-15 v1 write sunset. Celery task names, queue, chain and Beat schedules are unchanged; last-poll state carries over on the existing Redis key.

Depends on cdip-routing's choice value lookup being deployed first (it maps v2 choice values back to SMART option keys).

Design: docs/superpowers/specs/2026-10-09-er-smart-sync-v2-migration-design.md
Plans: docs/superpowers/plans/2026-10-09-er-v2-migration-{1,2,3,4}-*.md

🤖 Generated with [Claude Code](https://claude.com/claude-code)
BODY
)"
```

- [ ] **Step 2: Preconditions before the prod deploy**

1. cdip-routing part 3 is live in prod.
2. The celery worker's `REDIS_DB` is the database the old synchronizer wrote `er.function.state.*` to (`KEYS er.function.state.*` in that db returns the integrations); the charts set `REDIS_DB: "0"`.
3. Every prod ER site the portal syncs runs ER 2.146.1 or newer. List them from the portal DB (enabled `InboundIntegrationConfiguration` rows of type `earth_ranger` linked to an enabled `smart_connect` outbound) and check each site's `/api/v1.0/status` version.
4. ER's migrator writes each inline enum key into its Choice table (`value` is varchar(100)); deep TREE leaves can exceed that, and the portal would then abort that CA's push on every run. A dry run stops before persistence, so `persist_failed` / `choice_creation_failed` never appear in it; the raw keys do, under `hardcoded_choices[].choices[].value`. Before the portal runs for real, dry-run the migrate endpoint against one representative prod tenant with TREE attributes and confirm the command below prints nothing (no type with an error code, no choice value over 100 characters). Error codes to expect otherwise: `schema_parse`, `schema_transform`, `unsupported_features`, the `choice_resolution_*` / `dependency_*` / `dynamic_choice_*` family, `exception`; `version_validation` means the type is already v2 and is fine. Warnings do not block. Any type that fails needs an ER-side fix or a spec decision (deactivate the v1 record and create v2 fresh, losing history linkage) before this rollout.

```bash
curl -sS -H "Authorization: Bearer $ER_TOKEN" -H "Content-Type: application/json" \
  -X POST "https://<site>.pamdas.org/api/v2.0/activity/eventtypes/migrate/" \
  -d '{"dry_run": true, "event_types": []}' | jq '
  .data[] | {event_type, errors: [.errors[].code], warnings: [.warnings[].code],
    long_values: [.hardcoded_choices[].choices[].value | select(length > 100)]}
  | select((.errors|length>0) or (.long_values|length>0))'
```

An empty `event_types` list makes ER evaluate every v1 type in the tenant.

- [ ] **Step 3: Confirm the SMART data model cache was flushed**

The flush is automatic: `build_synchronizer` calls `sync_integrations.smart_cache.ensure_smart_cache_generation()`, which deletes every `cache:smart-ca:*` entry on each worker process's first task and whenever the marker `cache:smart-ca:generation` (`<version>@<epoch>`) is not the installed smartconnect-client version or is less than an hour old. Entries written by smartconnect-client 1.11 have no TTL and lack the CM node `id` the split-mode slug uses; pushing from one would create display-only slugs that are duplicated once the cache refreshes. After the first sync task on the new image, verify in the portal's Redis:

```bash
redis-cli -h $REDIS_HOST -n $REDIS_DB GET cache:smart-ca:generation   # 1.15.0@<epoch of the first task>
```

and look for `Flushed N smartconnect data model cache entries` in the worker log. `maintain_smart_integrations` is an optional warm-up afterwards.

- [ ] **Step 4: First run, one site**

After the cache refresh, from a portal pod:

```bash
python manage.py runsync_command --smart_integration_id <id> --er_integration_id <id>
```

In the logs confirm the run summary shows `event_types_migrated` equal to the number of SMART-derived v1 types the site had, `event_types_migrate_errored=0`, and `event_types_skipped_by_conflict=0`. Then push one patrol with a TREE or mixed-case option through to SMART and confirm it lands. Only then let the Beat schedule run the remaining sites.
