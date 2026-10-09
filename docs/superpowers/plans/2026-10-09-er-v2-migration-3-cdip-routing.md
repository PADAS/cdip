# ER v2 migration, part 3 of 4: cdip-routing choice value lookup

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** cdip-routing maps the bare Choice values ER returns for v2 event types back to the SMART option keys SMART Connect expects, using smartconnect-client 1.15.0's `resolve_option_key`.

**Architecture:** Two commits in one PR. First a platform bump: Python 3.8 to 3.10 and the dependency chain that smartconnect-client 1.15 requires (httpx 0.28, which drags FastAPI, Starlette, uvicorn, the OpenTelemetry packages and the gundi clients forward). Then the transformer change: both `_resolve_attribute` methods collect the matched attribute's option keys and translate the value through a small module-level helper that logs and passes the value through on failure.

**Tech Stack:** Python 3.10, FastAPI, pydantic 1.x, pytest-asyncio, uv for dependency resolution. Repo: `/Users/chrisdo/padas/cdip-routing` (branch off `origin/main` after `git fetch`; the local `main` is behind). CI runs the suite through the reusable `.github/workflows/_tests.yml` (called by `tests.yml` on PRs and by `main.yml` before the image build).

**Spec:** `docs/superpowers/specs/2026-10-09-er-smart-sync-v2-migration-design.md` in PADAS/cdip, section "3. cdip-routing". Depends on part 1 (smartconnect-client 1.15.0 on PyPI). Must deploy before any portal site syncs as v2 (part 4).

## Global Constraints

- Target interpreter is Python 3.10 everywhere: `docker/Dockerfile`, `.github/workflows/_tests.yml`, the `.python-version` file, the lockfile header, `AGENTS.md` and `docs/python-version.md`. 3.11 is blocked by aioredis 2.0.1, which fails at import there.
- `gundi-core` stays at `1.13.0`, the pin main moved to on 2026-09-18 for batch envelopes. Do not let the upgrade pull it anywhere else.
- Exact pins in `requirements.in` as today; `requirements.txt` is regenerated, never hand-edited.
- Existing v1 sites must see no change: an ER value that equals a SMART option key is returned untouched. The helper tries the exact match first.
- On a lookup failure the value is passed through unchanged and an error is logged with the attribute key and the value, so SMART's rejection stays observable.
- The helper never raises into the transform.

## Review Focus

1. An event whose choice attribute value is not a string (ER can return `None` for a cleared field, or a number) must pass through untouched. Pinned in Task 2.
2. A value that resolves through the base data model but not the configurable model's curated subset (the CM dropped an option after the event was recorded) must still resolve. Pinned in Task 2 (union of option keys).
3. `_resolve_attributes_for_event` takes the first element of list values before calling `_resolve_attribute`, so MLIST values arrive as scalars; the helper must not special-case lists. Covered by Task 2's scalar tests; no list handling is added.
4. Tracing must still export after the OpenTelemetry jump: the Cloud Trace exporter and propagator import paths used in `app/core/tracing` must resolve. Pinned in Task 1 by the suite importing `app` and by the stage soak step in Task 3.
5. The TestClient-based request tests must pass on httpx 0.28, which changed how Starlette's client is built. Pinned in Task 1 by the full suite.

---

### Task 1: Python 3.10 and dependency bump

**Files:**
- Modify: `requirements.in`
- Regenerate: `requirements.txt`
- Modify: `docker/Dockerfile:1`
- Modify: `.github/workflows/_tests.yml:23-26`
- Modify: `.python-version`
- Modify: `AGENTS.md:27-28,59-60,64`
- Modify: `docs/python-version.md`

**Interfaces:**
- Produces: `smartconnect-client==1.15.0` importable; Python 3.10 runtime.

- [ ] **Step 1: Rewrite `requirements.in`**

Replace the file with (duplicates removed, walrus dropped because nothing imports it beyond the import line in `app/core/utils.py`, which Step 3 deletes):

```
environs==9.5.0
pydantic==1.10.15
fastapi==0.125.0
gcloud-aio-pubsub==6.0.0
gcloud-aio-storage==9.2.0
Pillow==9.4.0
urllib3==1.26.14
uvicorn==0.54.0
aioredis==2.0.1
hiredis==2.3.2
packaging==23.0
https://github.com/PADAS/er-client/releases/download/v1.3.0/earthranger_client-1.3.0-py3-none-any.whl
smartconnect-client==1.15.0
gundi-client==1.1.0
gundi-client-v2==3.7.1
gundi-core==1.13.0
opentelemetry-api==1.45.1
opentelemetry-sdk==1.45.1
opentelemetry-exporter-gcp-trace==1.15.0
opentelemetry-propagator-gcp==1.15.0
opentelemetry-exporter-otlp-proto-http==1.45.1
opentelemetry-instrumentation-requests==0.66b1
opentelemetry-instrumentation-aiohttp-client==0.66b1
opentelemetry-instrumentation-httpx==0.66b1
pytest==7.2.1
pytest-asyncio==0.20.3
pytest-mock==3.10.0
backoff==2.2.1
```

- [ ] **Step 2: Regenerate the lock and switch the interpreter**

```bash
cd /Users/chrisdo/padas/cdip-routing
git fetch origin && git checkout -b feature/er-v2-choice-values origin/main
echo "3.10" > .python-version
sed -i '' 's/^FROM python:3.8-slim/FROM python:3.10-slim/' docker/Dockerfile
sed -i '' "s/python-version: '3.8'/python-version: '3.10'/" .github/workflows/_tests.yml
uv pip compile --python-version 3.10 -o requirements.txt requirements.in
grep -nE "^(httpx|redis|smartconnect-client|gundi-client-v2|gundi-core|fastapi|opentelemetry-api)==" requirements.txt
```

Expected pins: httpx 0.28.1, redis 6.4.0, smartconnect-client 1.15.0, gundi-client-v2 3.7.1, gundi-core 1.13.0, fastapi 0.125.0, opentelemetry-api 1.45.1.

Then fix the three places that state the version in prose:

- `.github/workflows/_tests.yml` lines 23 to 25: replace the comment with `# Matches the runtime image (docker/Dockerfile: python:3.10-slim). See docs/python-version.md.`
- `AGENTS.md` line 27 to 28: `python3.8` becomes `python3.10`; line 59: `**Python 3.8**` becomes `**Python 3.10**`; line 60: replace "the upgrade path to 3.11 is written up" with "3.11 is blocked by aioredis until the client moves to redis.asyncio"; line 64: `--python-version 3.8` becomes `--python-version 3.10`.
- `docs/python-version.md`: replace the whole file with:

```markdown
# Python version

## Current state

cdip-routing targets **Python 3.10** (since 2026-10, PR "Resolve ER v2 choice
values to SMART option keys"):
- `docker/Dockerfile` → `python:3.10-slim`
- `requirements.txt` is compiled with `uv pip compile --python-version 3.10`
- CI (`.github/workflows/_tests.yml`) runs the suite on 3.10 to match

The move off 3.8 was forced by smartconnect-client 1.15 (`requires-python >= 3.10`),
which routing needs for `resolve_option_key`. The same change lifted httpx to 0.28
and the chain it drags (FastAPI, Starlette, uvicorn, OpenTelemetry, gundi-client,
gundi-client-v2, redis-py 6).

## Why not 3.11 yet

`aioredis==2.0.1` (archived upstream, last release 2021) declares its timeout
exception with both `asyncio.TimeoutError` and the builtin `TimeoutError` as
bases. Python 3.11 made those the same class, so the package fails at import
with `TypeError: duplicate base class TimeoutError`. Nothing in routing's code
triggers it; importing the package is enough.

## Path to 3.11

redis-py absorbed aioredis in 4.2 and routing already carries redis-py 6, so:

1. `app/core/utils.py`: replace `aioredis.from_url(...)` with
   `redis.asyncio.from_url(...)` (same arguments); drop `aioredis` from
   `requirements.in`. Every method routing calls (get, set, setex, incr, decr,
   expire, pipeline) has the same async signature; explicit closes become
   `aclose()`.
2. `docker/Dockerfile` → `python:3.11-slim`; `.python-version` → `3.11`.
3. `uv pip compile --python-version 3.11 -o requirements.txt requirements.in`.
4. `.github/workflows/_tests.yml` → `python-version: '3.11'`; update `AGENTS.md`.
5. Run `pytest` and smoke the Redis client against a real server once.

Do it as its own PR so the interpreter change can be reverted independently.
``` If `marshmallow` resolves to 4.x the compile is wrong (smartconnect-client pins it below 4); stop and check the smartconnect-client version that was picked.

- [ ] **Step 3: Drop the unused walrus import**

In `app/core/utils.py` delete line 4, `import walrus`.

- [ ] **Step 4: Build a 3.10 environment and run the suite**

```bash
cd /Users/chrisdo/padas/cdip-routing
rm -rf venv && uv venv --python 3.10 venv && uv pip install --python venv/bin/python -r requirements.txt
venv/bin/python -m pytest -q
```

Expected: 96 passed. The same resolution against `origin/main` as of 2026-10-09 (gundi-core 1.13.0 included) passed 96 in a scratch venv.

- [ ] **Step 5: Smoke the Redis client against a real server**

aioredis is unmaintained and now sits next to redis-py 6; the suite mocks the cache, so check it once for real:

```bash
docker run -d --rm --name tmp-redis-routing -p 36379:6379 redis:7-alpine
venv/bin/python - <<'PY'
import asyncio, aioredis
async def main():
    r = aioredis.from_url("redis://localhost:36379/0", encoding="utf-8", decode_responses=True)
    await r.setex("t", 5, "x"); print("ttl", await r.ttl("t")); print("incr", await r.incr("c"))
    await r.close()
asyncio.run(main())
PY
docker stop tmp-redis-routing
```

Expected: `ttl 5` and `incr 1`.

- [ ] **Step 6: Commit**

```bash
git add requirements.in requirements.txt docker/Dockerfile .github/workflows/_tests.yml .python-version app/core/utils.py AGENTS.md docs/python-version.md
git commit -m "Move to Python 3.10 and smartconnect-client 1.15

Lifts httpx to 0.28 (FastAPI 0.125, Starlette 0.50, OpenTelemetry 1.45,
gundi-client 1.1.0, gundi-client-v2 3.7.1) and drops the unused walrus
dependency. Required for smartconnect-client's resolve_option_key.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: Map ER choice values back to SMART option keys

**Files:**
- Modify: `app/services/transformers.py` (imports at `:28`; `SMARTTransformer._resolve_attribute` at `:349-386`; `SMARTTransformerV2._resolve_attribute` at `:1079-1116`)
- Test: `app/tests/test_transform_observations_v1.py`, `app/tests/test_transform_observations_v2.py`

**Interfaces:**
- Consumes: `smartconnect.choices.resolve_option_key`, `OptionKeyResolutionError` (part 1).
- Produces (module-level in `transformers.py`): `_option_keys(*attributes: Optional[dict]) -> List[str]` and `map_choice_value_to_option_key(*, attribute_key: str, value: Any, option_keys: List[str]) -> Any`.

- [ ] **Step 1: Write the failing tests**

Append to `app/tests/test_transform_observations_v1.py`:

```python
from app.services.transformers import SmartEventTransformer, map_choice_value_to_option_key


def test_map_choice_value_exact_key_unchanged():
    assert map_choice_value_to_option_key(
        attribute_key="wildlifestate", value="healthy", option_keys=["healthy", "injured"]
    ) == "healthy"


def test_map_choice_value_resolves_sanitized_tree_path():
    assert map_choice_value_to_option_key(
        attribute_key="causeofdeath",
        value="natural_disease",
        option_keys=["natural", "natural.disease"],
    ) == "natural.disease"


def test_map_choice_value_passes_non_strings_through():
    assert map_choice_value_to_option_key(
        attribute_key="x", value=None, option_keys=["a"]
    ) is None
    assert map_choice_value_to_option_key(
        attribute_key="x", value=3, option_keys=["a"]
    ) == 3


def test_map_choice_value_logs_and_passes_through_when_unresolvable(caplog):
    with caplog.at_level("ERROR"):
        out = map_choice_value_to_option_key(
            attribute_key="wildlifestate", value="nope", option_keys=["healthy"]
        )
    assert out == "nope"
    assert "wildlifestate" in caplog.text and "nope" in caplog.text


@pytest.mark.asyncio
async def test_smart_transformer_resolves_v2_choice_values(
    mocker, mock_smart_async_client_class, smart_outbound_configuration_gcp_pubsub
):
    mocker.patch(
        "app.services.transformers.AsyncSmartClient", mock_smart_async_client_class
    )
    transformer = SmartEventTransformer(
        config=smart_outbound_configuration_gcp_pubsub, ca_uuid=None
    )
    # TREE leaf stored by ER as its sanitized Choice value.
    assert await transformer._resolve_attribute("causeofdeath", "natural_disease") == (
        "causeofdeath",
        "natural.disease",
    )
    # v1 sites: exact key stays untouched.
    assert await transformer._resolve_attribute("wildlifestate", "healthy") == (
        "wildlifestate",
        "healthy",
    )
    # Unknown attribute still falls through to the transformation rules path.
    assert await transformer._resolve_attribute("not_an_attribute", "x") == (None, None)
```

Append to `app/tests/test_transform_observations_v2.py`:

```python
from app.services.transformers import SmartEventTransformerV2


@pytest.mark.asyncio
async def test_smart_transformer_v2_resolves_v2_choice_values(
    mocker, mock_smart_async_client_class, destination_integration_v2_smart
):
    mocker.patch(
        "app.services.transformers.AsyncSmartClient", mock_smart_async_client_class
    )
    transformer = SmartEventTransformerV2(config=destination_integration_v2_smart)
    assert await transformer._resolve_attribute("causeofdeath", "natural_disease") == (
        "causeofdeath",
        "natural.disease",
    )
    assert await transformer._resolve_attribute("wildlifestate", "healthy") == (
        "wildlifestate",
        "healthy",
    )
```

The fixture data model is `app/tests/test_datamodel.xml`: `wildlifestate` is a LIST with keys `healthy`, `injured`, `dead`; `causeofdeath` is a TREE with `natural.disease` among its leaves.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `venv/bin/python -m pytest app/tests/test_transform_observations_v1.py app/tests/test_transform_observations_v2.py -q -k "choice_value"`
Expected: `ImportError: cannot import name 'map_choice_value_to_option_key'`.

- [ ] **Step 3: Implement**

In `app/services/transformers.py`, after `from smartconnect import AsyncSmartClient` (line 28):

```python
from smartconnect.choices import OptionKeyResolutionError, resolve_option_key
```

After `ADMIN_PORTAL_HOST = ...` (line 56), add:

```python
def _option_keys(*attributes: Optional[dict]) -> List[str]:
    """Option keys of the given data model attribute dicts, deduplicated in order.

    Base-model attributes carry {key, type, options}; configurable-model
    attributes carry {key, options, ...} with a curated subset. The union is
    used so a value recorded before a CM dropped an option still resolves.
    """
    keys: List[str] = []
    for attribute in attributes:
        for option in (attribute or {}).get("options") or []:
            key = option.get("key")
            if key and key not in keys:
                keys.append(key)
    return keys


def map_choice_value_to_option_key(
    *, attribute_key: str, value: Any, option_keys: List[str]
) -> Any:
    """Translate an ER choice value back to the SMART option key it came from.

    ER v2 event types store LIST/MLIST/TREE selections as Choice values
    derived from the SMART key (lower-cased, non-alphanumerics collapsed to
    underscores, hash-shortened over 100 chars). SMART Connect only accepts
    the original key. Exact matches (all v1 sites) return unchanged. On a
    failed lookup the value is returned unchanged and an error is logged so
    SMART's rejection stays traceable to the attribute.
    """
    if not option_keys or not isinstance(value, str):
        return value
    try:
        return resolve_option_key(option_keys, value)
    except OptionKeyResolutionError as e:
        logger.error(
            "Could not map ER choice value %r for SMART attribute %r to an option key: %s",
            value,
            attribute_key,
            e,
            extra={"attribute_key": attribute_key, "value": value},
        )
        return value
```

Replace the body of `SMARTTransformer._resolve_attribute` from `attr = None` through `return key, value` (lines 352 to 366) with:

```python
        # Favor a match in a configurable model, then the CA data model.
        cm_attr = None
        for cm in await self.get_configurable_models():
            cm_attr = cm.get_attribute(key=key)
            if cm_attr:
                break
        ca_attr = (await self.get_ca_datamodel()).get_attribute(key=key)

        if cm_attr or ca_attr:
            value = map_choice_value_to_option_key(
                attribute_key=key,
                value=value,
                option_keys=_option_keys(cm_attr, ca_attr),
            )
            return key, value
```

Make the identical replacement in `SMARTTransformerV2._resolve_attribute` (lines 1082 to 1096). The transformation-rules fallthrough below each method stays as is.

- [ ] **Step 4: Run the suite**

Run: `venv/bin/python -m pytest -q`
Expected: 96 previously passing plus 6 new, all passed. `test_transform_events_for_smart` still asserts `{"ageofsign": "days", "species": "lion"}` because both are exact option keys.

- [ ] **Step 5: Commit**

```bash
git add app/services/transformers.py app/tests/test_transform_observations_v1.py app/tests/test_transform_observations_v2.py
git commit -m "Map ER v2 choice values back to SMART option keys

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: PR and stage soak

- [ ] **Step 1: Open the PR**

```bash
git push -u origin feature/er-v2-choice-values
gh pr create --title "Resolve ER v2 choice values to SMART option keys (Python 3.10, smartconnect-client 1.15)" --body "$(cat <<'BODY'
Two commits, revertable separately:

1. Platform bump: Python 3.10, smartconnect-client 1.15.0 from PyPI, httpx 0.28 and the chain it forces (FastAPI 0.125, Starlette 0.50, uvicorn 0.54, OpenTelemetry 1.45 / 0.66b1, gundi-client 1.1.0, gundi-client-v2 3.7.1, redis 6). Unused walrus dropped. Suite passes; aioredis smoke-tested against Redis 7.
2. Both SMART transformers translate bare ER choice values (v2 event types) back to SMART option keys via resolve_option_key. Exact keys pass through unchanged, so v1 sites see no difference.

Must be deployed before the portal starts syncing SMART data models as ER v2 event types.

Spec: PADAS/cdip docs/superpowers/specs/2026-10-09-er-smart-sync-v2-migration-design.md

🤖 Generated with [Claude Code](https://claude.com/claude-code)
BODY
)"
```

- [ ] **Step 2: Stage soak checklist (before the prod deploy)**

After the stage deploy from `main`:

1. Confirm spans arrive: open Cloud Trace in the stage project and find a `transform_observation` span newer than the deploy. The OpenTelemetry jump is the one change the suite cannot cover.
2. Push one ER event with a TREE-valued attribute through a v1 SMART connection on stage and confirm SMART Connect accepts the waypoint (no `Unknown option` rejection in the dispatcher logs).
3. Confirm the portal and route lookups still resolve: one event each through a Gundi v1 and a Gundi v2 SMART connection, since gundi-client-v2 jumped a major version.

Then promote to prod. Part 4 may start its prod rollout once this is live.
