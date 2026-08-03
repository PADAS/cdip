# Pipeline Batch Envelope Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Note on paths:** this plan is a point-in-time execution record; absolute
> paths like `/Users/chrisdo/padas/<repo>` refer to the author's local
> checkouts of the sibling repos (gundi-core, cdip, cdip-routing,
> gundi-dispatcher-er). Substitute your own checkout locations if re-running
> any steps.

**Goal:** Preserve source-side observation batches end-to-end through Gundi (portal → routing → ER dispatcher) so backfills post to EarthRanger's bulk sensors endpoint instead of one HTTP request per observation.

**Architecture:** Three new gundi-core system events carry a batch envelope ("1..N observations sharing a provider") through the existing Pub/Sub pipeline. The portal stops shredding list-POSTs into per-item messages above a threshold; routing transforms per item and groups per `(destination, provider_key)`; the ER dispatcher bulk-posts via the already-list-capable `post_sensor_observation`. Batches only shrink or split, never merge — no buffering or timers anywhere.

**Tech Stack:** Python, pydantic v1 (`<2`), Django 4.2 (portal), FastAPI (routing), functions-framework Cloud Function (dispatcher), GCP Pub/Sub, Redis, pytest + pytest-asyncio + pytest-mock.

**Spec:** `docs/superpowers/specs/2026-07-29-pipeline-batch-envelope-design.md` (in the cdip repo).

## Global Constraints

- Four repos, each with its own venv and test suite: `/Users/chrisdo/padas/gundi-core`, `/Users/chrisdo/padas/cdip` (portal), `/Users/chrisdo/padas/cdip-routing`, `/Users/chrisdo/padas/gundi-dispatcher-er`. Every task states its repo; run all commands from that repo's root unless stated otherwise.
- **pydantic v1 only** (`pydantic>=1.7.3,<2` in gundi-core): use `Field(..., const=True)`, `@validator`, `.parse_obj()`, `.dict()`/`.json()`. No pydantic-v2 idioms.
- **All three new events MUST keep the inherited default `schema_version="v1"`.** Both cdip-routing (`app/services/process_messages.py:37`) and gundi-dispatcher-er (`core/services.py:338`) dead-letter/discard any transformer event whose `schema_version != "v1"`. Do NOT pin `schema_version` to `"v2"` the way `ObservationDeliveryFailed` does.
- An event's wire name is its **Python class name** (`SystemEventBaseModel.event_type` property, injected by `.dict()`). Consumers route on hand-maintained `event_type`-string → handler dicts; every consumer task must add its dict entries.
- Batch invariant (from the spec): all items in an envelope share `(data_provider_id, stream_type)`; stages may split or shrink a batch, never merge. One posted ER batch must share one `(destination_id, provider_key)` — the sensors endpoint path embeds `provider_key`.
- `external_id` stays `None` for batch-delivered observations (spec decision — ER's bulk sensor response has no reliable per-item IDs and nothing downstream needs observation external_ids).
- Feature branch per repo, named `gundi-batch-envelope` (adjust to a Jira key if one is assigned). Commit after every green test cycle. Do not push or open PRs unless asked.
- gundi-core version: the local checkout says `1.11.3` but the portal already pins `1.12.0` — upstream is ahead. Task 1 starts by syncing the repo; the new release is the **next minor above upstream HEAD** (assumed `1.13.0` below — verify and substitute the real number everywhere it appears).

---

### Task 1: gundi-core — batch envelope events

**Repo:** `/Users/chrisdo/padas/gundi-core`

**Files:**
- Create: `gundi_core/events/batches.py`
- Modify: `gundi_core/events/__init__.py` (add one import line)
- Modify: `gundi_core/__init__.py` (version bump)
- Test: `tests/test_batches.py`

**Interfaces:**
- Consumes: `SystemEventBaseModel` (`gundi_core/events/core.py`), `Observation`, `ERObservation`, `StreamPrefixEnum` (`gundi_core/schemas/v2`).
- Produces (used by Tasks 2–6):
  - `ObservationsBatch(data_provider_id, observations: List[Observation], batch_id=auto)` — pydantic model
  - `ObservationsBatchReceived(payload: ObservationsBatch)` — system event
  - `TransformedERObservationItem(gundi_id, observation: ERObservation)`
  - `ERObservationsBatch(batch_id, data_provider_id, destination_id, provider_key, items: List[TransformedERObservationItem])`
  - `ObservationsBatchTransformedER(payload: ERObservationsBatch)` — system event
  - `ObservationsBatchDeliveryDetails(batch_id, data_provider_id, destination_id, delivered_at, gundi_ids: List)`
  - `ObservationsBatchDelivered(payload: ObservationsBatchDeliveryDetails)` — system event
  - Note: batch size/count is NOT a model field — it is `len(...)` on the list, and is duplicated into Pub/Sub attributes (`batch_count`) by publishers so consumers can act before parsing.

- [ ] **Step 1: Sync the repo and pick the version**

```bash
cd /Users/chrisdo/padas/gundi-core
git checkout main && git pull
head -1 gundi_core/__init__.py   # e.g. __version__ = "1.12.0"
git checkout -b gundi-batch-envelope
```

Whatever `__version__` upstream shows, the new version is its next minor (e.g. `1.12.0` → `1.13.0`). Use that number in this task's Step 6 and in Tasks 2, 4, 5 requirement pins.

- [ ] **Step 2: Write the failing test**

Create `tests/test_batches.py`:

```python
"""Tests for gundi_core.events.batches."""

import json
import uuid
from datetime import datetime, timezone

import pytest

from gundi_core.events import (
    ERObservationsBatch,
    ObservationsBatch,
    ObservationsBatchDelivered,
    ObservationsBatchDeliveryDetails,
    ObservationsBatchReceived,
    ObservationsBatchTransformedER,
    TransformedERObservationItem,
)
from gundi_core.schemas.v2 import ERObservation, Location, Observation


@pytest.fixture
def observations():
    return [
        Observation(
            gundi_id=str(uuid.uuid4()),
            data_provider_id="ddd0946d-15b0-4308-b93d-e0470b6d33b6",
            source_id=uuid.uuid4(),
            external_source_id=f"device-{i}",
            recorded_at=datetime(2026, 7, 1, 12, i, 0, tzinfo=timezone.utc),
            location=Location(lon=-122.0, lat=47.0),
        )
        for i in range(3)
    ]


@pytest.fixture
def er_items(observations):
    return [
        TransformedERObservationItem(
            gundi_id=obs.gundi_id,
            observation=ERObservation(
                manufacturer_id=obs.external_source_id,
                recorded_at=obs.recorded_at,
                location={"lon": obs.location.lon, "lat": obs.location.lat},
            ),
        )
        for obs in observations
    ]


def test_batch_received_round_trip(observations):
    event = ObservationsBatchReceived(
        payload=ObservationsBatch(
            data_provider_id="ddd0946d-15b0-4308-b93d-e0470b6d33b6",
            observations=observations,
        )
    )
    raw = json.loads(event.json())
    assert raw["event_type"] == "ObservationsBatchReceived"
    assert raw["schema_version"] == "v1"  # MUST stay v1: routing/dispatcher gates discard anything else
    rebuilt = ObservationsBatchReceived.parse_obj(raw)
    assert len(rebuilt.payload.observations) == 3
    assert rebuilt.payload.observations[0].external_source_id == "device-0"
    assert rebuilt.payload.batch_id  # auto-generated


def test_batch_transformed_er_round_trip(er_items):
    event = ObservationsBatchTransformedER(
        payload=ERObservationsBatch(
            batch_id=str(uuid.uuid4()),
            data_provider_id="ddd0946d-15b0-4308-b93d-e0470b6d33b6",
            destination_id="338225f3-91f9-4fe1-b013-353a229ce504",
            provider_key="gundi_movebank_abc123",
            items=er_items,
        )
    )
    raw = json.loads(event.json())
    assert raw["event_type"] == "ObservationsBatchTransformedER"
    assert raw["schema_version"] == "v1"
    rebuilt = ObservationsBatchTransformedER.parse_obj(raw)
    assert rebuilt.payload.provider_key == "gundi_movebank_abc123"
    assert len(rebuilt.payload.items) == 3
    assert str(rebuilt.payload.items[1].gundi_id) == str(er_items[1].gundi_id)


def test_batch_delivered_round_trip():
    gundi_ids = [str(uuid.uuid4()) for _ in range(3)]
    event = ObservationsBatchDelivered(
        payload=ObservationsBatchDeliveryDetails(
            batch_id=str(uuid.uuid4()),
            data_provider_id="ddd0946d-15b0-4308-b93d-e0470b6d33b6",
            destination_id="338225f3-91f9-4fe1-b013-353a229ce504",
            delivered_at=datetime(2026, 7, 29, 12, 0, 0, tzinfo=timezone.utc),
            gundi_ids=gundi_ids,
        )
    )
    raw = json.loads(event.json())
    assert raw["event_type"] == "ObservationsBatchDelivered"
    rebuilt = ObservationsBatchDelivered.parse_obj(raw)
    assert [str(g) for g in rebuilt.payload.gundi_ids] == gundi_ids


def test_empty_observations_default_is_a_list():
    batch = ObservationsBatch(data_provider_id="ddd0946d-15b0-4308-b93d-e0470b6d33b6")
    assert batch.observations == []
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_batches.py -v`
Expected: FAIL with `ImportError: cannot import name 'ObservationsBatch'`

- [ ] **Step 4: Write the implementation**

Create `gundi_core/events/batches.py`:

```python
import uuid
from datetime import datetime
from typing import List, Union
from uuid import UUID

from pydantic import BaseModel, Field

from gundi_core.schemas.v2 import ERObservation, Observation, StreamPrefixEnum
from .core import SystemEventBaseModel


# Batch envelopes: a message carrying 1..N items that share a data provider
# and stream type. Pipeline stages may SPLIT or SHRINK a batch (drop items,
# regroup per destination) but must never MERGE batches — that invariant is
# what keeps the pipeline free of buffers and flush timers.
#
# IMPORTANT: these events must keep the inherited schema_version="v1".
# cdip-routing and the ER dispatcher discard transformer events with any
# other schema_version.


class ObservationsBatch(BaseModel):
    batch_id: Union[UUID, str] = Field(default_factory=uuid.uuid4)
    data_provider_id: Union[UUID, str] = Field(
        ...,
        description="The provider Integration shared by every observation in the batch.",
    )
    stream_type: str = Field(StreamPrefixEnum.observation.value, const=True)
    observations: List[Observation] = Field(default_factory=list)


class ObservationsBatchReceived(SystemEventBaseModel):
    payload: ObservationsBatch


class TransformedERObservationItem(BaseModel):
    gundi_id: Union[UUID, str] = Field(
        ...,
        description="Gundi ID of the source observation (per-item identity — "
                    "single-item messages carry this in PubSub attributes instead).",
    )
    observation: ERObservation


class ERObservationsBatch(BaseModel):
    batch_id: Union[UUID, str] = Field(default_factory=uuid.uuid4)
    data_provider_id: Union[UUID, str]
    destination_id: Union[UUID, str]
    provider_key: str = Field(
        ...,
        description="EarthRanger provider key shared by every item. The ER "
                    "sensors endpoint path embeds this, so one batch = one key.",
    )
    items: List[TransformedERObservationItem] = Field(default_factory=list)


class ObservationsBatchTransformedER(SystemEventBaseModel):
    payload: ERObservationsBatch


class ObservationsBatchDeliveryDetails(BaseModel):
    batch_id: Union[UUID, str]
    data_provider_id: Union[UUID, str]
    destination_id: Union[UUID, str]
    delivered_at: datetime
    gundi_ids: List[Union[UUID, str]] = Field(default_factory=list)
    # No external_ids: ER's bulk sensors response has no reliable per-item IDs,
    # and nothing downstream depends on observation external_ids (unlike events).


class ObservationsBatchDelivered(SystemEventBaseModel):
    payload: ObservationsBatchDeliveryDetails
```

In `gundi_core/events/__init__.py`, add after the existing imports (keep alphabetical-ish grouping used there):

```python
from .batches import *
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/ -v`
Expected: all PASS (including the pre-existing `test_delivery.py`).

- [ ] **Step 6: Bump the version**

Edit `gundi_core/__init__.py` to the version chosen in Step 1 (e.g.):

```python
__version__ = "1.13.0"
```

- [ ] **Step 7: Commit**

```bash
git add gundi_core/events/batches.py gundi_core/events/__init__.py gundi_core/__init__.py tests/test_batches.py
git commit -m "Add observation batch envelope events (ObservationsBatchReceived/TransformedER/Delivered)"
```

- [ ] **Step 8: Release note (manual gate)**

The release is tag-driven: after this branch merges to main upstream, tagging `v1.13.0` publishes the package (the workflow hard-fails if the tag ≠ `__version__`). Tasks 2, 4, 5 pin this version. Until it's released, dependent repos can test against the local checkout with `pip install -e /Users/chrisdo/padas/gundi-core` in their venvs — each of those tasks says when.

---

### Task 2: Portal — consume `ObservationsBatchDelivered`

**Repo:** `/Users/chrisdo/padas/cdip` (working dir for tests: `cdip_admin/`)

**Files:**
- Modify: `cdip_admin/event_consumers/dispatcher_events_consumer.py` (new handler + registry entry)
- Modify: `dependencies/requirements.in` and `dependencies/requirements.txt` (gundi-core pin)
- Test: `cdip_admin/event_consumers/tests/test_dispatcher_events_consumer.py`

**Interfaces:**
- Consumes: `ObservationsBatchDelivered` / `ObservationsBatchDeliveryDetails` from Task 1 (via `from gundi_core import events as system_events`, already imported at module top).
- Produces: `handle_observations_batch_delivered_event(event_dict: dict) -> None`, registered as `"ObservationsBatchDelivered"` in the module-level `event_handlers` dict. Consumed by the dispatcher's published events (Task 4).

- [ ] **Step 1: Point the venv at the new gundi-core**

```bash
cd /Users/chrisdo/padas/cdip
git checkout main && git pull && git checkout -b gundi-batch-envelope
.venv/bin/pip install -e /Users/chrisdo/padas/gundi-core
```

Also update the pins now so the dependency change ships with the code change — in `dependencies/requirements.in` line 67 change `gundi-core==1.12.0` to the Task 1 version (e.g. `gundi-core==1.13.0`), and mirror the same change at `dependencies/requirements.txt:257` (full `pip-compile` regeneration can be done at PR time per repo convention; the direct edit keeps the diff reviewable).

- [ ] **Step 2: Write the failing test**

Append to `cdip_admin/event_consumers/tests/test_dispatcher_events_consumer.py`:

```python
def _make_batch_delivered_message(traces, destination):
    message = MagicMock()
    event_dict = {
        "event_id": "705535df-1b9b-412b-9fd5-e29b09582111",
        "timestamp": "2026-07-29 18:19:19.215459+00:00",
        "schema_version": "v1",
        "event_type": "ObservationsBatchDelivered",
        "payload": {
            "batch_id": "8a5535df-1b9b-412b-9fd5-e29b09582222",
            "data_provider_id": str(traces[0].data_provider.id),
            "destination_id": str(destination.id),
            "delivered_at": "2026-07-29 18:19:19.215015+00:00",
            "gundi_ids": [str(t.object_id) for t in traces],
        },
    }
    message.data = json.dumps(event_dict).encode("utf-8")
    return message


def test_process_observations_batch_delivered_event(
        lotek_observation_trace, integrations_list_er
):
    destination = integrations_list_er[0]
    message = _make_batch_delivered_message(
        traces=[lotek_observation_trace], destination=destination
    )
    process_event(message)
    lotek_observation_trace.refresh_from_db()
    assert str(lotek_observation_trace.destination.id) == str(destination.id)
    assert str(lotek_observation_trace.delivered_at) == "2026-07-29 18:19:19.215015+00:00"
    assert lotek_observation_trace.external_id is None  # By design: no per-item IDs from bulk posts
    assert not lotek_observation_trace.has_error
    # One aggregate activity-log entry for the whole batch
    activity_log = ActivityLog.objects.filter(
        integration_id=str(lotek_observation_trace.data_provider.id),
        value="observation_batch_delivery_succeeded",
    ).first()
    assert activity_log
    assert activity_log.log_level == ActivityLog.LogLevels.DEBUG
    assert activity_log.origin == ActivityLog.Origin.DISPATCHER
    assert activity_log.title == f"1 Observations Delivered to '{destination.base_url}'"
    assert activity_log.details["batch_id"] == "8a5535df-1b9b-412b-9fd5-e29b09582222"


def test_process_observations_batch_delivered_event_second_destination(
        lotek_observation_trace, integrations_list_er
):
    # The trace is already bound to destination[0]; delivery to destination[1]
    # must CREATE a second trace row, not overwrite the first.
    first, second = integrations_list_er[0], integrations_list_er[1]
    lotek_observation_trace.destination = first
    lotek_observation_trace.save()
    message = _make_batch_delivered_message(
        traces=[lotek_observation_trace], destination=second
    )
    process_event(message)
    rows = GundiTrace.objects.filter(object_id=lotek_observation_trace.object_id)
    assert rows.count() == 2
    new_row = rows.exclude(id=lotek_observation_trace.id).first()
    assert str(new_row.destination.id) == str(second.id)
    assert new_row.delivered_at is not None


def test_process_observations_batch_delivered_event_unknown_ids_are_skipped(
        lotek_observation_trace, integrations_list_er
):
    destination = integrations_list_er[0]
    message = _make_batch_delivered_message(
        traces=[lotek_observation_trace], destination=destination
    )
    # Inject an unknown gundi_id alongside the real one
    event_dict = json.loads(message.data)
    event_dict["payload"]["gundi_ids"].append("99999999-9999-9999-9999-999999999999")
    message.data = json.dumps(event_dict).encode("utf-8")
    process_event(message)  # Must not raise
    lotek_observation_trace.refresh_from_db()
    assert lotek_observation_trace.delivered_at is not None
```

Note: `lotek_observation_trace` and `integrations_list_er` are existing conftest fixtures (used by `test_retriable_status_delivery_errors_are_logged_as_warnings`). If `lotek_observation_trace` has `object_type` other than `"obv"`, that's fine — the handler doesn't branch on it.

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd cdip_admin && ../.venv/bin/pytest event_consumers/tests/test_dispatcher_events_consumer.py -k batch -v`
Expected: FAIL — the events are processed but discarded with "Unknown Event Type ObservationsBatchDelivered" (the entrypoint swallows and acks unknown types), so the trace assertions fail.

- [ ] **Step 4: Write the handler**

In `cdip_admin/event_consumers/dispatcher_events_consumer.py`, add after `handle_observation_delivered_event` (note the file already imports `json`, `system_events`, `GundiTrace`, `Integration`, `ActivityLog`, `logger`):

```python
def handle_observations_batch_delivered_event(event_dict: dict):
    event = system_events.ObservationsBatchDelivered.parse_obj(event_dict)
    details = event.payload
    destination_id = str(details.destination_id)
    gundi_ids = [str(g) for g in details.gundi_ids]
    logger.info(
        f"Observations Batch Delivery Succeeded. batch_id: {details.batch_id}, "
        f"destination_id: {destination_id}, count: {len(gundi_ids)}",
        extra={"event": event_dict}
    )
    traces = list(GundiTrace.objects.filter(object_id__in=gundi_ids))
    if not traces:  # This shouldn't happen
        logger.warning(f"No known observations in batch {details.batch_id}. Event Ignored.")
        return

    traces_by_object_id = {}
    for trace in traces:
        traces_by_object_id.setdefault(str(trace.object_id), []).append(trace)

    to_update = []
    to_create = []
    for gundi_id in gundi_ids:
        object_traces = traces_by_object_id.get(gundi_id)
        if not object_traces:
            logger.warning(f"Unknown Observation with id {gundi_id} in batch {details.batch_id}. Skipped.")
            continue
        bound = next(
            (t for t in object_traces if t.destination_id and str(t.destination_id) == destination_id),
            None,
        )
        unbound = next((t for t in object_traces if not t.destination_id), None)
        trace = bound or unbound
        if trace:
            trace.destination_id = destination_id
            trace.delivered_at = details.delivered_at
            trace.has_error = False
            trace.error = ""
            to_update.append(trace)
        else:  # Delivered to an additional destination: add a row
            base = object_traces[0]
            to_create.append(
                GundiTrace(
                    object_id=base.object_id,
                    object_type=base.object_type,
                    source=base.source,
                    created_by=base.created_by,
                    data_provider=base.data_provider,
                    destination_id=destination_id,
                    delivered_at=details.delivered_at,
                )
            )
    if to_update:
        GundiTrace.objects.bulk_update(
            to_update, ["destination_id", "delivered_at", "has_error", "error"]
        )
    if to_create:
        GundiTrace.objects.bulk_create(to_create)

    # One aggregate activity-log entry for the whole batch
    destination = Integration.objects.filter(id=destination_id).first()
    destination_str = destination.base_url if destination else destination_id
    log_data = json.loads(json.dumps(event_dict["payload"], default=str))
    ActivityLog.objects.create(
        log_level=ActivityLog.LogLevels.DEBUG,
        log_type=ActivityLog.LogTypes.EVENT,
        origin=ActivityLog.Origin.DISPATCHER,
        integration=traces[0].data_provider,
        value="observation_batch_delivery_succeeded",
        title=f"{len(gundi_ids)} Observations Delivered to '{destination_str}'",
        details=log_data,
        is_reversible=False,
    )
```

Add the registry entry in the module-level `event_handlers` dict (line ~394):

```python
event_handlers = {
    "ObservationDelivered": handle_observation_delivered_event,
    "ObservationsBatchDelivered": handle_observations_batch_delivered_event,
    "ObservationDeliveryFailed": handle_observation_delivery_failed_event,
    "ObservationUpdated": handle_observation_updated_event,
    "ObservationUpdateFailed": handle_observation_update_failed_event,
    "DispatcherCustomLog": handle_dispatcher_log_event
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd cdip_admin && ../.venv/bin/pytest event_consumers/tests/test_dispatcher_events_consumer.py -v`
Expected: all PASS (new batch tests plus every pre-existing test).

- [ ] **Step 6: Commit**

```bash
git add cdip_admin/event_consumers/dispatcher_events_consumer.py \
        cdip_admin/event_consumers/tests/test_dispatcher_events_consumer.py \
        dependencies/requirements.in dependencies/requirements.txt
git commit -m "Handle ObservationsBatchDelivered: bulk trace update + one activity-log entry per batch"
```

---

### Task 3: ER dispatcher — throttling debits N items

**Repo:** `/Users/chrisdo/padas/gundi-dispatcher-er`

**Files:**
- Modify: `core/throttling.py` (`_evaluate`, `check_admission`)
- Modify: `core/services.py:377-416` (`process_request` passes `amount` from attributes)
- Test: `tests/test_throttling.py`

**Interfaces:**
- Produces: `check_admission(destination_id, stream_type, amount=1)` and `_evaluate(destination_id, family, amount=1)`. `amount` comes from the `batch_count` Pub/Sub attribute (set by routing in Task 5; absent = 1). Existing single-message callers are unaffected by the default.

- [ ] **Step 1: Branch and point the venv at the new gundi-core**

```bash
cd /Users/chrisdo/padas/gundi-dispatcher-er
git checkout main && git pull && git checkout -b gundi-batch-envelope
.venv/bin/pip install -e /Users/chrisdo/padas/gundi-core
```

Update pins: in `requirements.in` change `gundi-core==1.11.2` to the Task 1 version; mirror in `requirements.txt:129`. NOTE: this jump crosses released versions 1.11.3–1.12.x — check the gundi-core changelog/commits for anything the dispatcher consumes (it imports events + v2 schemas) before assuming compatibility.

- [ ] **Step 2: Write the failing tests**

Append to `tests/test_throttling.py` (fixtures `mock_throttle_db`, `throttling_enabled` already exist at the top of the file; `check_admission` and `ThrottledMessage` are already imported there — verify and reuse the file's existing import style):

```python
@pytest.mark.asyncio
async def test_admission_debits_batch_amount(mock_throttle_db, throttling_enabled):
    mock_throttle_db.incr.return_value = 250  # first increment of the window, amount=250
    await check_admission(destination_id="dest-1", stream_type="obv", amount=250)
    # incr was called with the batch amount
    args, kwargs = mock_throttle_db.incr.call_args
    assert 250 in args or kwargs.get("amount") == 250
    # First increment of the window (count == amount) must still set the expiry
    assert mock_throttle_db.expire.called


@pytest.mark.asyncio
async def test_admission_rejects_batch_over_cap(mock_throttle_db, throttling_enabled, mocker):
    # Cap is 300/min by default; a second batch pushing the counter to 500 must be deferred
    mocker.patch.object(settings, "THROTTLE_GRACE_WAIT_MAX_SECONDS", 0)
    mock_throttle_db.incr.return_value = 500
    with pytest.raises(ThrottledMessage):
        await check_admission(destination_id="dest-1", stream_type="obv", amount=250)


@pytest.mark.asyncio
async def test_admission_default_amount_is_one(mock_throttle_db, throttling_enabled):
    mock_throttle_db.incr.return_value = 1
    await check_admission(destination_id="dest-1", stream_type="obv")
    assert mock_throttle_db.expire.called  # count == amount == 1 sets the window expiry
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_throttling.py -k batch_amount -v` (and `-k default_amount`)
Expected: FAIL with `TypeError: check_admission() got an unexpected keyword argument 'amount'`

- [ ] **Step 4: Implement**

In `core/throttling.py`, change `_evaluate` (currently `core/throttling.py:71`) and `check_admission` (`:95`):

```python
def _evaluate(destination_id, family, amount=1):
    # Returns (admitted, reason, retry_after). Plain commands instead of a Lua
    # script: INCR is atomic, and the check-then-increment race admits at most
    # a few extra messages — acceptable for a kindness cap, and it keeps this
    # module testable against the suite's MagicMock Redis.
    db = utils._cache_db
    for scope in (SITE_SCOPE, family):
        ttl = db.ttl(_cooldown_key(destination_id, scope))
        # TTL semantics: -2 missing, -1 no expiry (shouldn't happen for our
        # setex keys; treated as no cooldown, failing open), 0 = expiring this
        # second - still honored so nothing leaks through the final second.
        if ttl is not None and ttl >= 0:
            return False, "cooldown", ttl
    now = int(time.time())
    rate_key = _rate_key(destination_id, family, now // 60)
    count = db.incr(rate_key, amount)
    if count == amount:
        # First increment of this window (whatever its size).
        # Two windows so a straggler INCR never resurrects an expired key
        db.expire(rate_key, 120)
    if count <= _cap_for_family(family):
        return True, None, None
    return False, "rate", 60 - (now % 60)


async def check_admission(destination_id, stream_type, amount=1):
    # Raises ThrottledMessage when the message must be deferred (nacked).
    # `amount` is the number of items the message carries (1 for classic
    # single-observation messages, N for batch envelopes).
    if not settings.THROTTLING_ENABLED or not destination_id:
        return
    family = get_family(stream_type)
    try:
        admitted, reason, retry_after = _evaluate(destination_id, family, amount)
        if admitted:
            return
        if reason == "rate" and retry_after <= settings.THROTTLE_GRACE_WAIT_MAX_SECONDS:
            # The window opens soon: wait it out instead of paying a redelivery
            await asyncio.sleep(retry_after)
            admitted, reason, retry_after = _evaluate(destination_id, family, amount)
            if admitted:
                return
    except Exception as e:
        # Fail open on ANY gate malfunction (Redis errors or bugs): throttling
        # is a kindness, not a correctness requirement, and a broken gate must
        # never 500-loop the stream.
        logger.warning(f"Throttle gate unavailable, admitting message: {e}", exc_info=True)
        return
    logger.info(
        f"Message deferred by throttle gate. destination_id={destination_id}, "
        f"family={family}, reason={reason}, retry_after={retry_after}"
    )
    raise ThrottledMessage(
        destination_id=destination_id, family=family, reason=reason, retry_after=retry_after
    )
```

In `core/services.py`, the `check_admission` call inside `process_request` (currently lines ~410-413) becomes:

```python
            try:
                admission_amount = int(attributes.get("batch_count") or 1)
            except (TypeError, ValueError):
                admission_amount = 1
            await throttling.check_admission(
                destination_id=attributes.get("destination_id"),
                stream_type=attributes.get("stream_type"),
                amount=admission_amount,
            )
```

- [ ] **Step 5: Run the full throttling suite**

Run: `.venv/bin/pytest tests/test_throttling.py -v`
Expected: all PASS — including the pre-existing tests, which exercise `amount=1` implicitly. NOTE: the existing `mock_throttle_db.incr.return_value = 1` fixtures still satisfy `count == amount`; if any pre-existing test asserts `incr` called with exactly one positional arg, update it to allow the amount argument.

- [ ] **Step 6: Commit**

```bash
git add core/throttling.py core/services.py tests/test_throttling.py requirements.in requirements.txt
git commit -m "Throttling: debit N items per message via batch_count attribute"
```

---

### Task 4: ER dispatcher — batch envelope handler

**Repo:** `/Users/chrisdo/padas/gundi-dispatcher-er`

**Files:**
- Modify: `core/settings.py` (add `ER_BULK_SIZE`)
- Modify: `core/utils.py` (add `is_observation_dispatched`)
- Modify: `core/dispatchers.py` (add `ERObservationsBatchDispatcher`)
- Modify: `core/event_handlers.py` (add `handle_er_observations_batch`, `dispatch_observations_batch_v2`, registry entries)
- Test: `tests/test_process_observation_batches_v2.py` (new file)

**Interfaces:**
- Consumes: `ObservationsBatchTransformedER` / `ERObservationsBatch` / `TransformedERObservationItem` / `ObservationsBatchDelivered` / `ObservationsBatchDeliveryDetails` from Task 1; `check_admission(..., amount=N)` from Task 3 (already wired in `process_request`); existing `get_integration_details`, `cache_dispatched_observation`, `publish_event`, `throttling.record_success`/`record_distress`, `DispatcherException`, `ReferenceDataError`.
- Produces: one `ObservationsBatchDelivered` event per processed envelope (consumed by Task 2's portal handler); per-item `ObservationDeliveryFailed` events for poison items (consumed by the existing portal handler).

**Failure semantics implemented here (from the spec):** transient error (no status code, or any status outside {400, 403} ) → record distress, publish `ObservationsBatchDelivered` for what already succeeded, then raise `DispatcherException` so the whole envelope nacks and redelivers (redelivery skips delivered items via the cache). Permanent error (HTTP 400/403 on a chunk) → per-item fallback: each item posts individually; individual successes are cached and counted delivered; individual failures publish `ObservationDeliveryFailed` and are NOT retried. The envelope acks (returns 200) once every item is delivered or individually failed.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_process_observation_batches_v2.py`:

```python
import base64
import datetime
import json

import pytest

from core import settings
from core.services import process_request
from erclient import ERClientException


def _make_batch_request(mocker, items_count=3, provider_key="gundi_movebank_abc123"):
    destination_id = "338225f3-91f9-4fe1-b013-353a229ce504"
    data_provider_id = "ddd0946d-15b0-4308-b93d-e0470b6d33b6"
    items = [
        {
            "gundi_id": f"23ca4b15-18b6-4cf4-9da6-36dd69c6f63{i}",
            "observation": {
                "manufacturer_id": f"device-{i}",
                "source_type": "tracking-device",
                "subject_name": f"subject-{i}",
                "recorded_at": "2026-07-22 11:51:05+00:00",
                "location": {"lon": -72.7, "lat": -51.6},
                "additional": {"speed_kmph": 30},
            },
        }
        for i in range(items_count)
    ]
    envelope = {
        "event_id": "48bd073a-8e35-43cf-91c2-c7b4b87a26d7",
        "timestamp": "2026-07-29 13:23:43.952056+00:00",
        "schema_version": "v1",
        "event_type": "ObservationsBatchTransformedER",
        "payload": {
            "batch_id": "8a5535df-1b9b-412b-9fd5-e29b09582222",
            "data_provider_id": data_provider_id,
            "destination_id": destination_id,
            "provider_key": provider_key,
            "items": items,
        },
    }
    publish_time = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    json_data = {
        "message": {
            "data": base64.b64encode(json.dumps(envelope).encode("utf-8")).decode("utf-8"),
            "attributes": {
                "gundi_version": "v2",
                "batch": "true",
                "batch_count": str(items_count),
                "provider_key": provider_key,
                "stream_type": "obv",
                "destination_id": destination_id,
                "data_provider_id": data_provider_id,
                "tracing_context": "{}",
            },
            "messageId": "11937923011474847",
            "message_id": "11937923011474847",
            "publishTime": publish_time,
            "publish_time": publish_time,
        },
        "subscription": "projects/MY-PROJECT/subscriptions/MY-SUB",
    }
    mock_request = mocker.MagicMock()
    mock_request.headers = {}
    mock_request.data = json.dumps(json_data)
    mock_request.get_json.return_value = json_data
    return mock_request


@pytest.mark.asyncio
async def test_process_observations_batch_posts_one_bulk_request(
    mocker,
    mock_cache_empty,
    mock_gundi_client_v2_class,
    mock_erclient_class,
    mock_pubsub_client,
):
    mocker.patch("core.utils._cache_db", mock_cache_empty)
    mocker.patch("core.utils.GundiClient", mock_gundi_client_v2_class)
    mocker.patch("core.dispatchers.TokenCachingAsyncERClient", mock_erclient_class)
    mocker.patch("core.utils.pubsub", mock_pubsub_client)

    await process_request(_make_batch_request(mocker, items_count=3))

    # ONE bulk post for the whole envelope
    post_mock = mock_erclient_class.return_value.post_sensor_observation
    assert post_mock.call_count == 1
    (posted,) = post_mock.call_args.args
    assert isinstance(posted, list)
    assert len(posted) == 3
    # Every item cached as dispatched
    assert mock_cache_empty.setex.call_count == 3
    # One ObservationsBatchDelivered event published
    publish_mock = mock_pubsub_client.PublisherClient.return_value.publish
    assert publish_mock.called


@pytest.mark.asyncio
async def test_batch_respects_er_bulk_size(
    mocker,
    mock_cache_empty,
    mock_gundi_client_v2_class,
    mock_erclient_class,
    mock_pubsub_client,
):
    mocker.patch("core.utils._cache_db", mock_cache_empty)
    mocker.patch("core.utils.GundiClient", mock_gundi_client_v2_class)
    mocker.patch("core.dispatchers.TokenCachingAsyncERClient", mock_erclient_class)
    mocker.patch("core.utils.pubsub", mock_pubsub_client)
    mocker.patch.object(settings, "ER_BULK_SIZE", 2)

    await process_request(_make_batch_request(mocker, items_count=3))

    post_mock = mock_erclient_class.return_value.post_sensor_observation
    assert post_mock.call_count == 2  # 2 + 1


@pytest.mark.asyncio
async def test_batch_skips_already_delivered_items(
    mocker,
    mock_gundi_client_v2_class,
    mock_erclient_class,
    mock_pubsub_client,
    dispatched_event,
):
    # First item is a cache hit (already delivered); the other two must post.
    mock_cache = mocker.MagicMock()
    mock_cache.get.side_effect = (dispatched_event.json(), None, None)
    mocker.patch("core.utils._cache_db", mock_cache)
    mocker.patch("core.utils.GundiClient", mock_gundi_client_v2_class)
    mocker.patch("core.dispatchers.TokenCachingAsyncERClient", mock_erclient_class)
    mocker.patch("core.utils.pubsub", mock_pubsub_client)

    await process_request(_make_batch_request(mocker, items_count=3))

    post_mock = mock_erclient_class.return_value.post_sensor_observation
    (posted,) = post_mock.call_args.args
    assert len(posted) == 2


@pytest.mark.asyncio
async def test_batch_transient_error_raises_for_redelivery(
    mocker,
    mock_cache_empty,
    mock_gundi_client_v2_class,
    mock_erclient_class,
    mock_pubsub_client,
):
    mocker.patch("core.utils._cache_db", mock_cache_empty)
    mocker.patch("core.utils.GundiClient", mock_gundi_client_v2_class)
    mocker.patch("core.dispatchers.TokenCachingAsyncERClient", mock_erclient_class)
    mocker.patch("core.utils.pubsub", mock_pubsub_client)
    err = ERClientException("ER error ON POST: service unavailable")
    err.status_code = 503
    mock_erclient_class.return_value.post_sensor_observation.side_effect = err

    with pytest.raises(Exception):
        await process_request(_make_batch_request(mocker, items_count=3))
    # Nothing was cached as delivered
    assert not mock_cache_empty.setex.called


@pytest.mark.asyncio
async def test_batch_400_falls_back_to_per_item_and_acks(
    mocker,
    mock_cache_empty,
    mock_gundi_client_v2_class,
    mock_erclient_class,
    mock_pubsub_client,
    post_sensor_observation_response,
):
    mocker.patch("core.utils._cache_db", mock_cache_empty)
    mocker.patch("core.utils.GundiClient", mock_gundi_client_v2_class)
    mocker.patch("core.dispatchers.TokenCachingAsyncERClient", mock_erclient_class)
    mocker.patch("core.utils.pubsub", mock_pubsub_client)

    from tests.conftest import async_return
    bulk_err = ERClientException("ER error ON POST: bad payload")
    bulk_err.status_code = 400
    item_err = ERClientException("ER error ON POST: bad payload")
    item_err.status_code = 400
    post_mock = mock_erclient_class.return_value.post_sensor_observation
    # Bulk call fails with 400; per-item fallback: item0 ok, item1 fails, item2 ok
    post_mock.side_effect = [
        bulk_err,
        async_return(post_sensor_observation_response),
        item_err,
        async_return(post_sensor_observation_response),
    ]

    # Must NOT raise: poison items are individually failed, envelope acks
    await process_request(_make_batch_request(mocker, items_count=3))

    assert post_mock.call_count == 4  # 1 bulk + 3 singles
    assert mock_cache_empty.setex.call_count == 2  # only the two successes cached
```

NOTE for the implementer: `mock_cache_empty`, `mock_gundi_client_v2_class`, `mock_erclient_class`, `mock_pubsub_client`, `dispatched_event`, `post_sensor_observation_response`, and `async_return` all exist in `tests/conftest.py`. `ERClientException` import path: `from erclient import ERClientException` — verify against how `core/dispatchers.py` imports erclient errors and match it.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_process_observation_batches_v2.py -v`
Expected: FAIL — `process_transformer_event_v2` logs "Event of type 'ObservationsBatchTransformedER' unknown" and dead-letters, so `post_sensor_observation.call_count == 0`.

- [ ] **Step 3: Implement — settings and cache helper**

`core/settings.py`, after the throttling block (~line 85):

```python
# Batch delivery (see cdip repo: docs/superpowers/specs/2026-07-29-pipeline-batch-envelope-design.md)
# Max observations per single ER bulk request. Independent from the envelope
# size chosen upstream; an envelope larger than this is posted in sub-chunks.
ER_BULK_SIZE = env.int("ER_BULK_SIZE", 200)
```

`core/utils.py`, after `cache_dispatched_observation` (~line 396):

```python
def is_observation_dispatched(gundi_id, destination_id) -> bool:
    # Cache-only check used by the batch path to skip already-delivered items
    # on envelope redelivery. Unlike get_dispatched_observation, this must NOT
    # fall back to a portal query — a large batch would turn one cache outage
    # into hundreds of portal calls. Fail open: worst case an item is re-posted
    # and ER receives a duplicate observation.
    try:
        cache_key = f"dispatched_observation.{gundi_id}.{destination_id}"
        return bool(_cache_db.get(cache_key))
    except Exception as e:
        logger.warning(f"Error reading dispatched-observation cache: {e}")
        return False
```

- [ ] **Step 4: Implement — batch dispatcher**

`core/dispatchers.py`, after `ERObservationDispatcher` (~line 327):

```python
class ERObservationsBatchDispatcher(ERDispatcherV2):

    async def _send(self, observations, **kwargs):
        # observations: List[schemas.v2.ERObservation] sharing this client's
        # provider_key. Posted as a single JSON array to the ER sensors endpoint.
        async with self.er_client as client:
            try:
                observations_cleaned = [
                    json.loads(o.json(exclude_none=True, exclude_unset=True))
                    for o in observations
                ]
                return await client.post_sensor_observation(observations_cleaned)
            except Exception as ex:
                logger.exception(
                    f"Error sending observations batch to {client.service_root}: \n{type(ex)}: {ex}"
                )
                raise ex
```

- [ ] **Step 5: Implement — handler**

`core/event_handlers.py`. Extend the transformer imports at the top:

```python
from gundi_core.events.transformers import (
    EventTransformedER,
    EventUpdateTransformedER,
    AttachmentTransformedER,
    ObservationTransformedER,
    ObservationsBatchTransformedER,
    MessageTransformedER
)
```

Add after `handle_er_observation` (~line 313):

```python
# ER status codes that mean the payload itself is bad: retrying the same
# bytes can never succeed, so shrink the batch instead of nacking it.
PERMANENT_ER_STATUS_CODES = {400, 403}


def _chunked(items, size):
    for start in range(0, len(items), size):
        yield items[start:start + size]


async def _publish_batch_delivered(batch, delivered_gundi_ids):
    if not delivered_gundi_ids:
        return
    await publish_event(
        event=system_events.ObservationsBatchDelivered(
            payload=system_events.ObservationsBatchDeliveryDetails(
                batch_id=batch.batch_id,
                data_provider_id=batch.data_provider_id,
                destination_id=batch.destination_id,
                delivered_at=datetime.now(timezone.utc),
                gundi_ids=delivered_gundi_ids,
            )
        ),
        topic_name=settings.DISPATCHER_EVENTS_TOPIC,
    )


async def _publish_item_delivery_failed(batch, item, exception):
    await publish_event(
        event=system_events.ObservationDeliveryFailed(
            payload=DeliveryErrorDetails(
                error=f"{type(exception).__name__}: {exception}",
                error_traceback=traceback.format_exc(),
                server_response_status=getattr(exception, "status_code", None),
                server_response_body=getattr(exception, "response_body", ""),
                observation=gundi_schemas_v2.DispatchedObservation(
                    gundi_id=item.gundi_id,
                    related_to=None,
                    external_id=None,
                    data_provider_id=batch.data_provider_id,
                    destination_id=batch.destination_id,
                    delivered_at=datetime.now(timezone.utc),
                ),
            )
        ),
        topic_name=settings.DISPATCHER_EVENTS_TOPIC,
    )


def _cache_item_as_dispatched(batch, item):
    cache_dispatched_observation(
        observation=gundi_schemas_v2.DispatchedObservation(
            gundi_id=item.gundi_id,
            related_to=None,
            external_id=None,  # By design: ER bulk responses carry no reliable per-item IDs
            data_provider_id=batch.data_provider_id,
            destination_id=batch.destination_id,
            delivered_at=datetime.now(timezone.utc),
        )
    )


async def dispatch_observations_batch_v2(batch, attributes: dict):
    with tracing.tracer.start_as_current_span(
            "er_dispatcher.dispatch_observations_batch", kind=SpanKind.CLIENT
    ) as current_span:
        destination_id = str(batch.destination_id)
        stream_type = gundi_schemas_v2.StreamPrefixEnum.observation.value
        current_span.set_attribute("batch_id", str(batch.batch_id))
        current_span.set_attribute("destination_id", destination_id)
        current_span.set_attribute("batch_count", len(batch.items))

        destination_integration = await get_integration_details(integration_id=destination_id)
        if not destination_integration:
            error_msg = f"No destination config details found for destination_id {destination_id}"
            logger.error(error_msg)
            raise ReferenceDataError(error_msg)

        # Skip items already delivered — makes envelope redelivery idempotent
        pending = [
            item for item in batch.items
            if not is_observation_dispatched(gundi_id=str(item.gundi_id), destination_id=destination_id)
        ]
        current_span.set_attribute("pending_count", len(pending))
        if not pending:
            logger.info(f"All items in batch {batch.batch_id} already delivered. Skipping.")
            return

        dispatcher = dispatchers.ERObservationsBatchDispatcher(
            integration=destination_integration,
            provider=batch.provider_key,
        )
        delivered_gundi_ids = []
        for chunk in _chunked(pending, settings.ER_BULK_SIZE):
            try:
                await dispatcher.send([item.observation for item in chunk])
            except Exception as e:
                status_code = getattr(e, "status_code", None)
                error = f"{type(e).__name__}: {e}"
                if status_code in PERMANENT_ER_STATUS_CODES:
                    # Permanent: shrink the batch — post items individually so
                    # the poison record(s) get identified and failed alone.
                    logger.warning(
                        f"Bulk post rejected ({status_code}) for batch {batch.batch_id}. "
                        f"Falling back to per-item posts for {len(chunk)} items."
                    )
                    single_dispatcher = dispatchers.ERObservationDispatcher(
                        integration=destination_integration,
                        provider=batch.provider_key,
                    )
                    for item in chunk:
                        try:
                            await single_dispatcher.send(item.observation)
                        except Exception as item_exc:
                            logger.warning(
                                f"Observation {item.gundi_id} in batch {batch.batch_id} failed individually: {item_exc}"
                            )
                            await _publish_item_delivery_failed(batch, item, item_exc)
                        else:
                            _cache_item_as_dispatched(batch, item)
                            delivered_gundi_ids.append(str(item.gundi_id))
                else:
                    # Transient: record distress, report partial progress, and
                    # nack the envelope. Redelivery skips delivered items via
                    # the dispatched-observation cache.
                    notify_scope = throttling.record_distress(
                        destination_id=destination_id,
                        stream_type=stream_type,
                        status_code=status_code,
                        error=error,
                        retry_after=getattr(e, "retry_after", None),
                    )
                    if notify_scope:
                        await publish_throttling_notice(attributes=attributes, scope=notify_scope)
                    await _publish_batch_delivered(batch, delivered_gundi_ids)
                    raise DispatcherException(
                        f"Transient error dispatching batch {batch.batch_id}: {error}"
                    )
            else:
                for item in chunk:
                    _cache_item_as_dispatched(batch, item)
                    delivered_gundi_ids.append(str(item.gundi_id))
                throttling.record_success(destination_id=destination_id, stream_type=stream_type)

        current_span.set_attribute("delivered_count", len(delivered_gundi_ids))
        await _publish_batch_delivered(batch, delivered_gundi_ids)


async def handle_er_observations_batch(event: ObservationsBatchTransformedER, attributes: dict):
    with tracing.tracer.start_as_current_span(
            "er_dispatcher.handle_er_observations_batch", kind=SpanKind.CONSUMER
    ) as current_span:
        current_span.set_attribute("batch_count", len(event.payload.items))
        return await dispatch_observations_batch_v2(batch=event.payload, attributes=attributes)
```

Also add `is_observation_dispatched` to the `core.utils` import block at the top of `core/event_handlers.py`.

Wire the registries at the bottom of `core/event_handlers.py`:

```python
event_schemas = {
    "EventTransformedER": EventTransformedER,
    "EventUpdateTransformedER": EventUpdateTransformedER,
    "AttachmentTransformedER": AttachmentTransformedER,
    "ObservationTransformedER": ObservationTransformedER,
    "ObservationsBatchTransformedER": ObservationsBatchTransformedER,
    "MessageTransformedER": MessageTransformedER
}

event_handlers = {
    "EventTransformedER": handle_er_event,
    "EventUpdateTransformedER": handle_er_event_update,
    "AttachmentTransformedER": handle_er_attachment,
    "ObservationTransformedER": handle_er_observation,
    "ObservationsBatchTransformedER": handle_er_observations_batch,
    "MessageTransformedER": handle_er_message
}
```

- [ ] **Step 6: Run the new tests, then the whole suite**

Run: `.venv/bin/pytest tests/test_process_observation_batches_v2.py -v`
Expected: all PASS.
Run: `.venv/bin/pytest tests/ -v`
Expected: all PASS (no regression in single-item paths).

- [ ] **Step 7: Commit**

```bash
git add core/settings.py core/utils.py core/dispatchers.py core/event_handlers.py tests/test_process_observation_batches_v2.py
git commit -m "Handle ObservationsBatchTransformedER: bulk posts, idempotent redelivery, per-item 400 fallback"
```

- [ ] **Step 8: Deployment-config note (carry into the PR description)**

`deploy_function.sh` currently sets `MAX_INSTANCES=1, CONCURRENCY=4, --memory=256Mi`. Before enabling batching in an environment, verify memory headroom with 4 concurrent envelopes of 500 items (a 500-item envelope is roughly 0.5–1 MB of JSON plus parsed pydantic models — likely fine, but confirm in dev with a real backfill; bump to 512Mi if resident memory exceeds ~70%).

---

### Task 5: Routing — batch envelope branch

**Repo:** `/Users/chrisdo/padas/cdip-routing`

**Files:**
- Modify: `app/services/event_handlers.py` (new handler + helpers + registry entries)
- Modify: `requirements.in` / `requirements.txt` (gundi-core pin)
- Test: `app/tests/test_process_observation_batches_v2.py` (new file)

**Interfaces:**
- Consumes: `ObservationsBatchReceived`, `ObservationsBatchTransformedER`, `ERObservationsBatch`, `TransformedERObservationItem` from Task 1; existing `get_connection`, `get_route`, `get_integration`, `get_provider_key`, `transform_observation_v2`, `build_gcp_pubsub_message`, `send_message_to_gcp_pubsub_dispatcher`, `_publish_gundi_delivery`.
- Produces: per-destination `ObservationsBatchTransformedER` Pub/Sub messages with attributes `{gundi_version: "v2", batch: "true", batch_count: "<N>", provider_key, stream_type: "obv", destination_id, data_provider_id}` — consumed by Task 4. Items whose transform result is not an `ERObservation` (non-ER destinations, e.g. Movebank's raw-dict transformer) publish individually exactly as today. Generic-model destinations publish one `GundiDelivery` per item as today.
- Dedup note (spec deviation, justified): the spec sketched per-item Redis dedup, but routing's dedup keys on the **system event_id**, and items inside an envelope never had individual event IDs — the only duplicate source at this stage is Pub/Sub redelivery of the whole message, which the existing envelope-level `event_id` dedup in `process_request` already covers with no code change. No per-item dedup is added.

- [ ] **Step 1: Branch and point the venv at the new gundi-core**

```bash
cd /Users/chrisdo/padas/cdip-routing
git checkout main && git pull && git checkout -b gundi-batch-envelope
venv/bin/pip install -e /Users/chrisdo/padas/gundi-core
```

Update pins: `requirements.in:17` `gundi-core==1.11.3` → the Task 1 version; mirror in `requirements.txt`.

- [ ] **Step 2: Write the failing tests**

Create `app/tests/test_process_observation_batches_v2.py`:

```python
"""Tests for the observations batch branch in event_handlers.

An ObservationsBatchReceived envelope is transformed per item, grouped per
(destination, effective provider_key), and published as one
ObservationsBatchTransformedER message per group.
"""

import json
import uuid

import pytest

from app.conftest import async_return
from app.services.process_messages import process_observation_event


def _make_batch_event_dict(observations_count=3, data_provider_id=None):
    data_provider_id = data_provider_id or "f870e228-4a65-40f0-888c-41bdc1124c3c"
    observations = [
        {
            "gundi_id": str(uuid.uuid4()),
            "data_provider_id": data_provider_id,
            "source_id": str(uuid.uuid4()),
            "external_source_id": f"device-{i}",
            "recorded_at": f"2026-07-22 11:5{i}:05+00:00",
            "location": {"lon": -72.7, "lat": -51.6},
            "observation_type": "obv",
        }
        for i in range(observations_count)
    ]
    return {
        "event_id": str(uuid.uuid4()),
        "timestamp": "2026-07-29 13:23:43.952056+00:00",
        "schema_version": "v1",
        "event_type": "ObservationsBatchReceived",
        "payload": {
            "batch_id": str(uuid.uuid4()),
            "data_provider_id": data_provider_id,
            "stream_type": "obv",
            "observations": observations,
        },
    }


def _batch_attributes(count):
    return {
        "observation_type": "obv",
        "gundi_version": "v2",
        "batch": "true",
        "batch_count": str(count),
        "tracing_context": "{}",
    }


def _decode_published_payload(send_mock, call_index=0):
    call_kwargs = send_mock.call_args_list[call_index][1]
    return json.loads(call_kwargs["message"].decode("utf-8")), call_kwargs


@pytest.mark.asyncio
async def test_batch_publishes_one_transformed_envelope_per_destination(
    mocker,
    mock_cache,
    mock_gundi_client_v2,
    destination_integration_v2,
    connection_v2,
    route_v2,
):
    mocker.patch("app.core.gundi._cache_db", mock_cache)
    mocker.patch("app.core.gundi.portal_v2", mock_gundi_client_v2)
    send_mock = mocker.AsyncMock()
    mocker.patch(
        "app.services.event_handlers.send_message_to_gcp_pubsub_dispatcher", send_mock
    )

    event_dict = _make_batch_event_dict(
        observations_count=3,
        data_provider_id=str(connection_v2.provider.id),
    )
    await process_observation_event(event_dict, _batch_attributes(3))

    # ONE publish for the whole batch (single ER destination in connection_v2)
    assert send_mock.call_count == 1
    payload, call_kwargs = _decode_published_payload(send_mock)
    assert payload["event_type"] == "ObservationsBatchTransformedER"
    assert len(payload["payload"]["items"]) == 3
    assert payload["payload"]["provider_key"]
    attrs = call_kwargs["attributes"]
    assert attrs["batch"] == "true"
    assert attrs["batch_count"] == "3"
    assert attrs["stream_type"] == "obv"
    assert attrs["destination_id"]
    # Every item pairs a gundi_id with the transformed ER observation
    source_gundi_ids = {o["gundi_id"] for o in event_dict["payload"]["observations"]}
    item_gundi_ids = {i["gundi_id"] for i in payload["payload"]["items"]}
    assert item_gundi_ids == source_gundi_ids


@pytest.mark.asyncio
async def test_batch_shrinks_on_transform_failure(
    mocker,
    mock_cache,
    mock_gundi_client_v2,
    destination_integration_v2,
    connection_v2,
    route_v2,
):
    mocker.patch("app.core.gundi._cache_db", mock_cache)
    mocker.patch("app.core.gundi.portal_v2", mock_gundi_client_v2)
    send_mock = mocker.AsyncMock()
    mocker.patch(
        "app.services.event_handlers.send_message_to_gcp_pubsub_dispatcher", send_mock
    )
    real_transform = mocker.patch("app.services.event_handlers.transform_observation_v2")
    # Middle item fails to transform; batch must shrink, not abort
    ok = mocker.MagicMock()
    ok.provider_key = None
    from gundi_core.schemas.v2 import ERObservation
    ok_obs = ERObservation(
        manufacturer_id="device-ok",
        recorded_at="2026-07-22 11:51:05+00:00",
        location={"lon": -72.7, "lat": -51.6},
    )
    real_transform.side_effect = [
        async_return(ok_obs),
        Exception("boom"),
        async_return(ok_obs),
    ]

    event_dict = _make_batch_event_dict(
        observations_count=3,
        data_provider_id=str(connection_v2.provider.id),
    )
    await process_observation_event(event_dict, _batch_attributes(3))

    assert send_mock.call_count == 1
    payload, _ = _decode_published_payload(send_mock)
    assert len(payload["payload"]["items"]) == 2


@pytest.mark.asyncio
async def test_batch_with_all_items_failing_publishes_nothing(
    mocker,
    mock_cache,
    mock_gundi_client_v2,
    destination_integration_v2,
    connection_v2,
    route_v2,
):
    mocker.patch("app.core.gundi._cache_db", mock_cache)
    mocker.patch("app.core.gundi.portal_v2", mock_gundi_client_v2)
    send_mock = mocker.AsyncMock()
    mocker.patch(
        "app.services.event_handlers.send_message_to_gcp_pubsub_dispatcher", send_mock
    )
    mocker.patch(
        "app.services.event_handlers.transform_observation_v2",
        side_effect=Exception("boom"),
    )

    event_dict = _make_batch_event_dict(
        observations_count=2,
        data_provider_id=str(connection_v2.provider.id),
    )
    await process_observation_event(event_dict, _batch_attributes(2))

    send_mock.assert_not_called()
```

NOTE for the implementer: `connection_v2`, `route_v2`, `destination_integration_v2`, `mock_gundi_client_v2`, `mock_cache` are existing conftest fixtures (used throughout `app/tests/`). Verify the exact fixture names for connection/route with `grep -n "def connection" app/conftest.py` and adjust — the mocked `portal_v2` client's `get_connection_details`/`get_route_details`/`get_integration_details` return values are what matter. Follow the arrangement in `app/tests/test_process_observations_v2_generic.py`, which is the direct precedent.

- [ ] **Step 3: Run tests to verify they fail**

Run: `venv/bin/pytest app/tests/test_process_observation_batches_v2.py -v`
Expected: FAIL — `process_observation_event` logs "Event of type 'ObservationsBatchReceived' unknown. Ignored." and `send_mock` is never called.

- [ ] **Step 4: Implement**

`app/services/event_handlers.py`. Extend imports:

```python
from gundi_core.events import (
    ObservationReceived,
    ObservationsBatchReceived,
    EventReceived,
    EventUpdateReceived,
    AttachmentReceived,
    TextMessageReceived,
    GundiDelivery,
    ProviderInfo,
    ERObservationsBatch,
    ObservationsBatchTransformedER,
    TransformedERObservationItem,
)
from gundi_core.schemas.v2 import StreamPrefixEnum, ERObservation
```

Add after `transform_and_route_observation` (follow its structure; `_publish_gundi_delivery` is the branch-shape precedent):

```python
async def _publish_transformed_batch_group(
    *,
    batch,
    items,
    effective_provider_key,
    destination,
    broker_config,
    current_span,
):
    er_batch = ERObservationsBatch(
        batch_id=batch.batch_id,
        data_provider_id=batch.data_provider_id,
        destination_id=str(destination.id),
        provider_key=effective_provider_key,
        items=items,
    )
    envelope = ObservationsBatchTransformedER(payload=er_batch)
    attributes = {
        "gundi_version": "v2",
        "batch": "true",
        "batch_count": str(len(items)),
        "provider_key": effective_provider_key,
        "stream_type": StreamPrefixEnum.observation.value,
        "destination_id": str(destination.id),
        "data_provider_id": str(batch.data_provider_id),
    }
    pubsub_message = build_gcp_pubsub_message(payload=envelope.dict(exclude_none=True))
    await send_message_to_gcp_pubsub_dispatcher(
        message=pubsub_message,
        attributes=attributes,
        destination=destination,
        broker_config=broker_config,
        ordering_key="",
    )
    logger.info(
        f"Batch {batch.batch_id}: {len(items)} observations transformed and sent to destination {destination.id}.",
        extra=attributes,
    )


async def transform_and_route_observations_batch(batch):
    with tracing.tracer.start_as_current_span(
        "routing_service.transform_and_route_observations_batch", kind=SpanKind.CONSUMER
    ) as current_span:
        current_span.set_attribute("batch_id", str(batch.batch_id))
        current_span.set_attribute("batch_count", len(batch.observations))
        if not batch.observations:
            return
        try:
            data_provider_id = str(batch.data_provider_id)
            # ONE connection/route lookup for the whole batch — every item
            # shares the provider by the envelope invariant.
            connection = await get_connection(connection_id=data_provider_id)
            if not connection:
                error = f"Connection '{data_provider_id}' not found."
                current_span.set_attribute("error", error)
                raise ReferenceDataError(error)
            provider = connection.provider
            default_route = await get_route(
                route_id=connection.default_route.id,
                data_provider_id=data_provider_id,
            )
            if not default_route:
                error = f"Default route '{connection.default_route.id}', for provider '{data_provider_id}' not found."
                current_span.set_attribute("error", error)
                raise ReferenceDataError(error)
            route_configuration = default_route.configuration
            provider_key = get_provider_key(provider)
            destinations = connection.destinations
            current_span.set_attribute("destinations_qty", len(destinations))

            provider_str = f"'{connection.provider.owner.name} - {connection.provider.name}'({connection.provider.id})"
            for destination in destinations:
                destination_integration = await get_integration(
                    integration_id=destination.id
                )
                broker_config = destination_integration.additional or {}
                destination_str = (
                    f"'{destination.owner.name} - {destination.name}'({destination.id})"
                )

                # Generic-model destinations keep the per-item GundiDelivery
                # path (splitting the batch is allowed; merging never is).
                if broker_config.get("generic_model"):
                    for observation in batch.observations:
                        await _publish_gundi_delivery(
                            observation=observation,
                            destination=destination,
                            destination_integration=destination_integration,
                            provider=provider,
                            provider_key=provider_key,
                            route_configuration=route_configuration,
                            broker_config=broker_config,
                            destination_str=destination_str,
                            provider_str=provider_str,
                            current_span=current_span,
                        )
                    continue

                # Transform per item; group per effective provider_key because
                # field mappings may override it per item and one ER bulk post
                # allows exactly one provider_key in its URL path.
                groups = {}
                for observation in batch.observations:
                    try:
                        transformed = await transform_observation_v2(
                            observation=observation,
                            destination=destination_integration,
                            provider=provider,
                            route_configuration=route_configuration,
                        )
                    except Exception as e:
                        # Shrink the batch, never abort it
                        error_msg = (
                            f"Error transforming observation {observation.gundi_id} in batch {batch.batch_id} "
                            f"from {provider_str} for destination {destination_str}: {type(e).__name__}: {e}. Discarded."
                        )
                        logger.exception(error_msg)
                        current_span.add_event(
                            name="routing_service.batch_item_discarded_on_transformer_error"
                        )
                        continue
                    if not transformed:
                        current_span.add_event(
                            name="routing_service.batch_item_discarded_by_transformer"
                        )
                        continue
                    if not isinstance(transformed, ERObservation):
                        # Non-ER destination in the same connection (e.g. a raw-dict
                        # transformer): no batch envelope exists for it yet, so this
                        # item publishes individually exactly as the single path does.
                        pubsub_message_payload = (
                            transformed
                            if isinstance(transformed, dict)
                            else build_transformer_event(transformed).dict(exclude_none=True)
                        )
                        attributes = build_transformed_message_attributes(
                            observation=observation,
                            destination=destination,
                            gundi_version="v2",
                            provider_key=getattr(transformed, "provider_key", provider_key),
                        )
                        await send_message_to_gcp_pubsub_dispatcher(
                            message=build_gcp_pubsub_message(payload=pubsub_message_payload),
                            attributes=attributes,
                            destination=destination,
                            broker_config=broker_config,
                            ordering_key="",
                        )
                        continue
                    effective_key = getattr(transformed, "provider_key", None) or provider_key
                    groups.setdefault(effective_key, []).append(
                        TransformedERObservationItem(
                            gundi_id=observation.gundi_id,
                            observation=transformed,
                        )
                    )

                for effective_provider_key, items in groups.items():
                    await _publish_transformed_batch_group(
                        batch=batch,
                        items=items,
                        effective_provider_key=effective_provider_key,
                        destination=destination,
                        broker_config=broker_config,
                        current_span=current_span,
                    )
        except ReferenceDataError as e:
            logger.exception(
                f"External error occurred obtaining reference data for batch {batch.batch_id}: {e}",
                extra={ExtraKeys.AttentionNeeded: True, ExtraKeys.InboundIntId: str(batch.data_provider_id)},
            )
            current_span.set_attribute("error", str(e))
            raise e  # Raise so the whole envelope is retried later by GCP
        except Exception as e:
            logger.exception(
                f"Unexpected internal exception occurred processing batch {batch.batch_id}: {e}",
                extra={ExtraKeys.AttentionNeeded: True, ExtraKeys.InboundIntId: str(batch.data_provider_id)},
            )
            current_span.set_attribute("error", str(e))
            raise e


async def handle_observations_batch_received(event: ObservationsBatchReceived):
    with tracing.tracer.start_as_current_span(
        "routing_service.handle_observations_batch_received", kind=SpanKind.CONSUMER
    ) as current_span:
        current_span.set_attribute("batch_count", len(event.payload.observations))
        await transform_and_route_observations_batch(batch=event.payload)
```

Wire the registries at the bottom:

```python
event_handlers = {
    "ObservationReceived": handle_observation_received,
    "ObservationsBatchReceived": handle_observations_batch_received,
    "EventReceived": handle_event_received,
    "EventUpdateReceived": handle_event_update,
    "AttachmentReceived": handle_attachment_received,
    "TextMessageReceived": handle_text_message_received,
}

event_schemas = {
    "ObservationReceived": ObservationReceived,
    "ObservationsBatchReceived": ObservationsBatchReceived,
    "EventReceived": EventReceived,
    "EventUpdateReceived": EventUpdateReceived,
    "AttachmentReceived": AttachmentReceived,
    "TextMessageReceived": TextMessageReceived,
}
```

No change to `process_request` or dedup: the envelope carries its own `event_id`, so the existing message-level dedup (`process_messages.py:281`) and processed-status write (`:58`) cover redelivery unchanged.

- [ ] **Step 5: Run the new tests, then the whole suite**

Run: `venv/bin/pytest app/tests/test_process_observation_batches_v2.py -v`
Expected: all PASS.
Run: `venv/bin/pytest app/tests/ -v`
Expected: all PASS (no regression in single-item, generic-model, or v1 paths).

- [ ] **Step 6: Commit**

```bash
git add app/services/event_handlers.py app/tests/test_process_observation_batches_v2.py requirements.in requirements.txt
git commit -m "Route ObservationsBatchReceived: one lookup per batch, group per (destination, provider_key)"
```

---

### Task 6: Portal — publish batch envelopes above a threshold

**Repo:** `/Users/chrisdo/padas/cdip` (working dir for tests: `cdip_admin/`)

**Files:**
- Modify: `cdip_admin/cdip_admin/settings.py` (two new env settings, "Sensors API to Routing" block ~line 467)
- Modify: `cdip_admin/api/v2/utils.py:319` (`send_observations_to_routing` refactor)
- Test: `cdip_admin/api/v2/tests/test_observations_api.py`

**Interfaces:**
- Consumes: `ObservationsBatchReceived` / `ObservationsBatch` from Task 1 (add to the existing `gundi_core.events` import at the top of utils.py); existing `publisher`, `is_duplicate_data`, `log_data_received`, tracing helpers.
- Produces: Pub/Sub messages on `RAW_OBSERVATIONS_TOPIC` with attributes `{observation_type: "obv", gundi_version: "v2", batch: "true", batch_count: "<N>", tracing_context}` — consumed by Task 5. Below the threshold, behavior is byte-for-byte today's (per-item `ObservationReceived` with per-item `gundi_id` attribute).
- **This is the on-switch and kill switch:** `OBSERVATIONS_BATCH_THRESHOLD` unreachable (e.g. `999999999`) reverts the whole platform to per-item without redeploying anything else.

- [ ] **Step 1: Write the failing test**

Append to `cdip_admin/api/v2/tests/test_observations_api.py`:

```python
def test_create_observations_in_bulk_above_threshold_publishes_batch_envelope(
        api_client, mocker, mock_publisher, mock_deduplication, settings,
        provider_trap_tagger, keyauth_headers_trap_tagger
):
    settings.OBSERVATIONS_BATCH_THRESHOLD = 3
    settings.OBSERVATIONS_BATCH_MAX_ITEMS = 2
    mocker.patch("api.v2.utils.publisher", mock_publisher)
    mocker.patch("api.v2.utils.is_duplicate_data", mock_deduplication)
    data = [
        {
            "source": f"batch-device-{i}",
            "type": "tracking-device",
            "recorded_at": f"2026-07-24 13:0{i}:00-0700",
            "location": {"lat": -51.690, "lon": -72.714},
        }
        for i in range(3)
    ]
    response = api_client.post(
        reverse("observations-list"), data=data, format='json', **keyauth_headers_trap_tagger
    )
    assert response.status_code == status.HTTP_200_OK
    # 3 items, max 2 per envelope -> 2 publishes (2 + 1), both batch envelopes
    assert mock_publisher.publish.call_count == 2
    first_call = mock_publisher.publish.call_args_list[0].kwargs
    assert first_call["data"]["event_type"] == "ObservationsBatchReceived"
    assert len(first_call["data"]["payload"]["observations"]) == 2
    extra = first_call["extra"]
    assert extra["batch"] == "true"
    assert extra["batch_count"] == "2"
    assert extra["gundi_version"] == "v2"
    assert extra["observation_type"] == StreamPrefixEnum.observation.value
    second_call = mock_publisher.publish.call_args_list[1].kwargs
    assert len(second_call["data"]["payload"]["observations"]) == 1


def test_create_observations_below_threshold_publishes_per_item(
        api_client, mocker, mock_publisher, mock_deduplication, settings,
        provider_trap_tagger, keyauth_headers_trap_tagger
):
    settings.OBSERVATIONS_BATCH_THRESHOLD = 10
    mocker.patch("api.v2.utils.publisher", mock_publisher)
    mocker.patch("api.v2.utils.is_duplicate_data", mock_deduplication)
    data = [
        {
            "source": f"single-device-{i}",
            "type": "tracking-device",
            "recorded_at": f"2026-07-24 13:0{i}:00-0700",
            "location": {"lat": -51.690, "lon": -72.714},
        }
        for i in range(2)
    ]
    response = api_client.post(
        reverse("observations-list"), data=data, format='json', **keyauth_headers_trap_tagger
    )
    assert response.status_code == status.HTTP_200_OK
    assert mock_publisher.publish.call_count == 2
    for call in mock_publisher.publish.call_args_list:
        assert call.kwargs["data"]["event_type"] == "ObservationReceived"
        assert "gundi_id" in call.kwargs["extra"]
```

(`settings` here is pytest-django's settings-override fixture; it works because utils.py reads `settings.OBSERVATIONS_BATCH_THRESHOLD` at call time, per Step 3.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd cdip_admin && ../.venv/bin/pytest api/v2/tests/test_observations_api.py -k threshold -v`
Expected: FAIL — `AttributeError` on the new settings, or 3 per-item publishes with `event_type == "ObservationReceived"`.

- [ ] **Step 3: Implement**

`cdip_admin/cdip_admin/settings.py`, in the "Sensors API to Routing" block (~line 467):

```python
# Sensors API to Routing
RAW_OBSERVATIONS_TOPIC = env.str("RAW_OBSERVATIONS_TOPIC", "raw-observations-prod")
# Batch envelope publishing (docs/superpowers/specs/2026-07-29-pipeline-batch-envelope-design.md).
# List-POSTs with at least this many non-duplicate observations publish
# ObservationsBatchReceived envelopes instead of per-item events. This is the
# platform kill switch: set it unreachable to revert to per-item end to end.
OBSERVATIONS_BATCH_THRESHOLD = env.int("OBSERVATIONS_BATCH_THRESHOLD", 10)
# Max observations per envelope (PubSub messages must stay far below 10MB).
OBSERVATIONS_BATCH_MAX_ITEMS = env.int("OBSERVATIONS_BATCH_MAX_ITEMS", 500)
```

`cdip_admin/api/v2/utils.py`: add `ObservationsBatchReceived` and `ObservationsBatch` to the `gundi_core.events` import (line 9-10). Then restructure `send_observations_to_routing` — the per-item span/build/duplicate-check loop stays exactly as it is, but instead of publishing inline it collects survivors; publishing happens at the end:

```python
def send_observations_to_routing(observations, gundi_ids):
    ready = []  # (observation_obj, gundi_id) pairs that survived duplicate checks
    for observation, gundi_id in zip(observations, gundi_ids):
        # Trace observations with Open Telemetry
        with tracing.tracer.start_as_current_span(
                f"gundi_api.process_observation", kind=trace.SpanKind.PRODUCER
        ) as current_span:
            # ... EVERYTHING from the current loop body stays IDENTICAL here,
            # from enrich_span_with_environment through the is_duplicate
            # check-and-continue — EXCEPT the final
            # `with tracing.tracer.start_as_current_span(...
            #     "gundi_api.send_observations_to_routing" ...` block,
            # which is REMOVED from the loop. In its place:
            ready.append((observation_obj, gundi_id))

    if not ready:
        return
    if len(ready) >= settings.OBSERVATIONS_BATCH_THRESHOLD:
        _publish_observations_batched(ready)
    else:
        for observation_obj, gundi_id in ready:
            _publish_single_observation(observation_obj, gundi_id)


def _publish_single_observation(observation_obj, gundi_id):
    # This is the publish block moved verbatim from the old loop body
    with tracing.tracer.start_as_current_span(
            f"gundi_api.send_observations_to_routing", kind=trace.SpanKind.PRODUCER
    ) as current_span:
        msg_for_routing = ObservationReceived(payload=observation_obj)
        tracing.instrumentation.enrich_span_from_observation(
            span=current_span, observation=msg_for_routing.payload, gundi_version="v2"
        )
        tracing_context = json.dumps(
            tracing.instrumentation.build_context_headers(),
            default=str,
        )
        observations_topic = settings.RAW_OBSERVATIONS_TOPIC
        logger.debug(
            f"Publishing ObservationReceived(event_id={msg_for_routing.event_id}, gundi_id={gundi_id}) to PubSub topic {observations_topic}.."
        )
        publisher.publish(
            topic=observations_topic,
            data=msg_for_routing.dict(exclude_none=True),
            extra={
                "observation_type": StreamPrefixEnum.observation.value,
                "gundi_version": "v2",
                "gundi_id": str(gundi_id),
                "tracing_context": tracing_context,
            },
        )


def _publish_observations_batched(ready):
    # All observations in one API request share the provider by construction
    # (one API key = one integration), so the envelope invariant holds.
    data_provider_id = str(ready[0][0].data_provider_id)
    batch_max = settings.OBSERVATIONS_BATCH_MAX_ITEMS
    observations_topic = settings.RAW_OBSERVATIONS_TOPIC
    for start in range(0, len(ready), batch_max):
        chunk = ready[start:start + batch_max]
        with tracing.tracer.start_as_current_span(
                f"gundi_api.send_observations_batch_to_routing", kind=trace.SpanKind.PRODUCER
        ) as current_span:
            batch = ObservationsBatch(
                data_provider_id=data_provider_id,
                observations=[obs for obs, _ in chunk],
            )
            msg_for_routing = ObservationsBatchReceived(payload=batch)
            current_span.set_attribute("batch_id", str(batch.batch_id))
            current_span.set_attribute("batch_count", len(chunk))
            tracing_context = json.dumps(
                tracing.instrumentation.build_context_headers(),
                default=str,
            )
            logger.debug(
                f"Publishing ObservationsBatchReceived(event_id={msg_for_routing.event_id}, "
                f"batch_id={batch.batch_id}, count={len(chunk)}) to PubSub topic {observations_topic}.."
            )
            publisher.publish(
                topic=observations_topic,
                data=msg_for_routing.dict(exclude_none=True),
                extra={
                    "observation_type": StreamPrefixEnum.observation.value,
                    "gundi_version": "v2",
                    "batch": "true",
                    "batch_count": str(len(chunk)),
                    "tracing_context": tracing_context,
                },
            )
```

- [ ] **Step 4: Run the new tests, then the surrounding suite**

Run: `cd cdip_admin && ../.venv/bin/pytest api/v2/tests/test_observations_api.py -v`
Expected: all PASS — including the pre-existing `test_create_observations_in_bulk` (2 items < default threshold 10, so it still sees `publish.call_count == 2` per-item publishes).

- [ ] **Step 5: Commit**

```bash
git add cdip_admin/cdip_admin/settings.py cdip_admin/api/v2/utils.py cdip_admin/api/v2/tests/test_observations_api.py
git commit -m "Publish ObservationsBatchReceived envelopes above OBSERVATIONS_BATCH_THRESHOLD"
```

---

### Task 7: End-to-end verification in dev (manual gate)

No code. Run after all repos' PRs are merged and released, in this order (each step is inert until the next):

1. Tag/release gundi-core (Task 1's version).
2. Deploy the portal (Tasks 2 + 6 code — the publish path stays inert until step 5's env var).
3. Deploy the ER dispatcher (Tasks 3 + 4). **Deployment-order hazard:** the
   ER dispatcher is deployed as ONE Cloud Function per destination topic
   (`er-dispatcher-<destination-uuid>-<env>`, see `deploy_function.sh`), not
   as a single service — this step means redeploying ALL of them, in every
   environment. Once step 5 flips the portal threshold, routing emits
   `ObservationsBatchTransformedER` envelopes to every ER destination; any
   dispatcher function still on the pre-batch revision doesn't recognize the
   event type, logs `Event of type 'ObservationsBatchTransformedER' unknown.
   Ignored.`, and dead-letters the whole envelope — silently, with no
   per-item failure events to surface it in the portal. Before enabling the
   portal threshold in step 5, enumerate the deployed dispatcher function
   revisions per environment and confirm every ER destination's function
   carries the batch handler.
4. Deploy cdip-routing (Task 5).
5. In dev only, set `OBSERVATIONS_BATCH_THRESHOLD=10` explicitly (it's the code default, but set it so the kill-switch path — raising it to `999999999` — is a config change that's already wired).

Verification checklist (dev):

- [ ] Trigger a Movebank (or any list-posting) action-runner pull large enough to exceed the threshold.
- [ ] Portal logs show `Publishing ObservationsBatchReceived(...)`; routing logs show `Batch ...: N observations transformed and sent`; dispatcher logs show one bulk post per ≤`ER_BULK_SIZE` chunk.
- [ ] ER destination row count matches the number of observations sent.
- [ ] `GundiTrace` rows for the batch have `delivered_at` set, `external_id` null, `has_error` false.
- [ ] Exactly one `observation_batch_delivery_succeeded` activity-log entry per envelope, visible in the Portal UI for the connection.
- [ ] Poison test: include one observation with a deliberately invalid payload for ER (e.g. malformed `recorded_at` that survives Gundi validation but fails ER); confirm the rest of its chunk delivers, and the poison item gets an `observation_delivery_failed` activity-log entry.
- [ ] Trickle test: POST 2 observations; confirm per-item `ObservationReceived` publishes (no batch envelope, no added latency).
- [ ] Kill switch: set `OBSERVATIONS_BATCH_THRESHOLD=999999999`, repeat the large pull, confirm per-item behavior returns.
- [ ] Watch dispatcher memory in Cloud Monitoring during the backfill (Task 4 Step 8's concern); bump `--memory=512Mi` in `deploy_function.sh` if needed.
- [ ] Compare wall-clock time and ER write load for the same backfill size against a pre-batching baseline; record the numbers in the PR/epic.

---

## Plan self-review notes

- **Spec coverage:** Section 1 → Task 1; Section 2 → Task 6; Section 3 → Task 5; Section 4 → Tasks 3+4; Section 5 → Task 4 (failure semantics block); Section 6 → Tasks 2+4 (`external_id=None` decision encoded in both); Section 7 → Task 7 ordering; Section 8 → each task's tests + Task 7. Phase 2 (events) intentionally unplanned.
- **Spec deviations (both justified, both flagged):** (1) routing does envelope-level dedup via the existing `event_id` mechanism instead of adding per-item Redis dedup — items never had individual event IDs and redelivery is the only duplicate source at that stage; (2) `count` is not a payload field — it's `len(items)` plus the `batch_count` message attribute for pre-parse throttling.
- **Type consistency:** `ObservationsBatch.observations` / `ERObservationsBatch.items` / `ObservationsBatchDeliveryDetails.gundi_ids` names match across Tasks 1, 2, 4, 5, 6. `batch_count` attribute name matches between Task 3 (reader), Task 5 (writer), Task 6 (writer). `provider_key` grouping key matches Task 4's client construction.
- **Known verify-at-execution points (called out inline):** exact gundi-core next version; fixture names in cdip-routing conftest; `ERClientException` import path in dispatcher tests; whether any pre-existing throttling test pins `incr`'s call signature.
