# ER v2 migration, part 1 of 4: smartconnect-client choice helpers

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish smartconnect-client 1.15.0 with the single definition of the SMART-option-key to ER-Choice-value rule and its inverse lookup.

**Architecture:** A new pure module `smartconnect/choices.py` owns the sanitize rule, the over-100-character hash shortening, and `resolve_option_key`. `DataModel` and `ConfigurableDataModel` get a thin method that looks up an attribute's option keys and delegates. Nothing else in the package changes.

**Tech Stack:** Python 3.10+, pydantic 1.x, pytest. Repo: `/Users/chrisdo/padas/smartconnect-client` (branch off `main`). Release is tag-driven: pushing `v1.15.0` runs `.github/workflows/release.yml`, which tests and publishes to PyPI.

**Spec:** `docs/superpowers/specs/2026-10-09-er-smart-sync-v2-migration-design.md` in PADAS/cdip, section "1. smartconnect-client".

## Global Constraints

- The sanitize rule is load-bearing and must stay byte-for-byte: `re.sub(r"[^A-Za-z0-9]+", "_", key).strip("_").lower()`, falling back to `"_"` when the result is empty.
- Values longer than 100 characters are shortened to the first 91 characters, an underscore, and the first 8 hex characters of the SHA-256 of the full sanitized string. Total length is exactly 100.
- `requires-python = ">=3.10,<4.0"` stays as is.
- Version bump is `1.14.0` to `1.15.0` in `pyproject.toml` only; the package has no changelog file.

## Review Focus

1. A value equal to one option key that also equals another key's sanitized form must return the exact key, never the sanitized match. Pinned in Task 1.
2. An attribute whose `options` is `None` (TEXT, NUMERIC) must raise `UnresolvableOptionKey`, not `TypeError`. Pinned in Task 2.
3. A non-string value such as `0` or `True` must raise `UnresolvableOptionKey` rather than crash inside the regex. Pinned in Task 1.
4. An option key longer than 100 characters must resolve from its hash-shortened value. Pinned in Task 1.
5. A `ConfigurableDataModel` attribute whose options carry only `key` and `isActive` (no `display`) must resolve the same as a base-model attribute. Pinned in Task 2.

---

### Task 1: `smartconnect/choices.py`

**Files:**
- Create: `smartconnect/choices.py`
- Test: `tests/test_choices.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `sanitize_choice_value(option_key: str) -> str`
  - `shorten_choice_value(sanitized: str) -> str`
  - `choice_value_for_option_key(option_key: str) -> str` (sanitize then shorten)
  - `resolve_option_key(option_keys: Iterable[str], value: str) -> str`
  - exceptions `OptionKeyResolutionError(ValueError)`, `UnresolvableOptionKey`, `AmbiguousOptionKey`
  - constant `CHOICE_VALUE_MAX_LEN = 100`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_choices.py
import hashlib

import pytest

from smartconnect.choices import (
    CHOICE_VALUE_MAX_LEN,
    AmbiguousOptionKey,
    OptionKeyResolutionError,
    UnresolvableOptionKey,
    choice_value_for_option_key,
    resolve_option_key,
    sanitize_choice_value,
    shorten_choice_value,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("lion", "lion"),
        ("Lion", "lion"),
        ("africa.kenya.nairobi", "africa_kenya_nairobi"),
        ("Côte d'Ivoire", "c_te_d_ivoire"),
        ("  trim me  ", "trim_me"),
        ("!@#$%", "_"),
        ("", "_"),
        ("123abc", "123abc"),
    ],
)
def test_sanitize_choice_value(raw, expected):
    assert sanitize_choice_value(raw) == expected


def test_shorten_leaves_values_up_to_100_unchanged():
    assert shorten_choice_value("a" * 100) == "a" * 100


def test_shorten_hashes_values_over_100_to_exactly_100():
    raw = "b" * 150
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:8]
    out = shorten_choice_value(raw)
    assert out == raw[:91] + "_" + digest
    assert len(out) == CHOICE_VALUE_MAX_LEN


def test_choice_value_for_option_key_sanitizes_then_shortens():
    raw = "Long.Key." * 20  # 180 chars before sanitizing
    assert choice_value_for_option_key(raw) == shorten_choice_value(sanitize_choice_value(raw))


def test_resolve_exact_match_wins_over_sanitized_match():
    # "lion" is both an exact key and the sanitized form of "Lion".
    assert resolve_option_key(["Lion", "lion"], "lion") == "lion"


def test_resolve_case_folded_key():
    assert resolve_option_key(["Lion", "Elephant"], "lion") == "Lion"


def test_resolve_tree_dotted_path():
    keys = ["natural", "natural.disease", "natural.oldage"]
    assert resolve_option_key(keys, "natural_disease") == "natural.disease"


def test_resolve_hash_shortened_long_key():
    long_key = "Very.Long.Option." * 10  # > 100 chars
    value = choice_value_for_option_key(long_key)
    assert resolve_option_key(["short", long_key], value) == long_key


def test_resolve_raises_when_nothing_matches():
    with pytest.raises(UnresolvableOptionKey):
        resolve_option_key(["healthy", "injured"], "dead")


def test_resolve_raises_on_collision():
    with pytest.raises(AmbiguousOptionKey):
        resolve_option_key(["Lion", "LION"], "lion")


def test_resolve_rejects_non_string_value():
    with pytest.raises(UnresolvableOptionKey):
        resolve_option_key(["0", "1"], 0)


def test_exceptions_share_a_base():
    assert issubclass(UnresolvableOptionKey, OptionKeyResolutionError)
    assert issubclass(AmbiguousOptionKey, OptionKeyResolutionError)
    assert issubclass(OptionKeyResolutionError, ValueError)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /Users/chrisdo/padas/smartconnect-client && pytest tests/test_choices.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'smartconnect.choices'`

- [ ] **Step 3: Write the module**

```python
# smartconnect/choices.py
"""Rules shared by er-smart-sync and cdip-routing for ER Choice values.

EarthRanger v2 event types store LIST/MLIST/TREE selections as ``Choice``
records whose ``value`` must match ``^\\w+$`` and is capped at 100
characters. er-smart-sync derives those values from SMART option keys when
it pushes a data model; cdip-routing applies the inverse when an ER event
comes back so SMART Connect receives the option key it knows.

These rules are load-bearing. Sites that already synced carry Choice rows
and historical events derived with them, so changing any function here
means rewriting stored data on every such site.
"""
import hashlib
import re
from typing import Iterable, List

CHOICE_VALUE_MAX_LEN = 100
_VALUE_HASH_LEN = 8
# Readable prefix kept before "_{hash}": 100 - 1 - 8.
_VALUE_PREFIX_LEN = CHOICE_VALUE_MAX_LEN - 1 - _VALUE_HASH_LEN


class OptionKeyResolutionError(ValueError):
    """A Choice value could not be mapped back to exactly one option key."""


class UnresolvableOptionKey(OptionKeyResolutionError):
    """No option key produces the given Choice value."""


class AmbiguousOptionKey(OptionKeyResolutionError):
    """More than one option key produces the given Choice value."""


def sanitize_choice_value(option_key: str) -> str:
    """Map a SMART option key to a ``^\\w+$`` string.

    SMART keys may contain ``.`` (TREE leaf paths), accents, apostrophes and
    spaces. Runs of anything outside ASCII letters and digits collapse to a
    single underscore, leading and trailing underscores are dropped, and the
    result is lower-cased. An empty result becomes ``"_"``.
    """
    sanitized = re.sub(r"[^A-Za-z0-9]+", "_", option_key).strip("_").lower()
    return sanitized or "_"


def shorten_choice_value(sanitized: str) -> str:
    """Hash-suffix values longer than ``CHOICE_VALUE_MAX_LEN``.

    Deterministic: the same input always yields the same output, and two
    inputs sharing the first 91 characters get different hash tails.
    """
    if len(sanitized) <= CHOICE_VALUE_MAX_LEN:
        return sanitized
    digest = hashlib.sha256(sanitized.encode("utf-8")).hexdigest()[:_VALUE_HASH_LEN]
    return f"{sanitized[:_VALUE_PREFIX_LEN]}_{digest}"


def choice_value_for_option_key(option_key: str) -> str:
    """The ER Choice value er-smart-sync stores for ``option_key``."""
    return shorten_choice_value(sanitize_choice_value(option_key))


def resolve_option_key(option_keys: Iterable[str], value: str) -> str:
    """Return the SMART option key that an ER Choice value came from.

    An exact match on a key wins. Otherwise the single key whose Choice
    value equals ``value`` is returned. Raises ``UnresolvableOptionKey``
    when nothing matches or ``value`` is not a string, and
    ``AmbiguousOptionKey`` when several keys collapse to the same value.
    """
    if not isinstance(value, str):
        raise UnresolvableOptionKey(
            f"Choice value must be a string, got {type(value).__name__}: {value!r}"
        )
    keys: List[str] = list(option_keys)
    if value in keys:
        return value
    matches = [key for key in keys if choice_value_for_option_key(key) == value]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise UnresolvableOptionKey(f"No option key maps to choice value {value!r}")
    raise AmbiguousOptionKey(
        f"Choice value {value!r} maps to several option keys: {matches}"
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd /Users/chrisdo/padas/smartconnect-client && pytest tests/test_choices.py -q`
Expected: 19 passed

- [ ] **Step 5: Commit**

```bash
cd /Users/chrisdo/padas/smartconnect-client
git checkout -b feature/choice-value-helpers main
git add smartconnect/choices.py tests/test_choices.py
git commit -m "Add shared SMART option key to ER choice value rules

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: `resolve_option_key` on the data model classes

**Files:**
- Modify: `smartconnect/models.py` (`DataModel` at line 248, `ConfigurableDataModel` at line 409; add one method to each after their `get_attribute`)
- Test: `tests/test_choices.py` (append)

**Interfaces:**
- Consumes: `smartconnect.choices.resolve_option_key`, `UnresolvableOptionKey` from Task 1.
- Produces: `DataModel.resolve_option_key(*, key: str, value: str) -> str` and `ConfigurableDataModel.resolve_option_key(*, key: str, value: str) -> str`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_choices.py`:

```python
from smartconnect.models import ConfigurableDataModel, DataModel

MINIMAL_CM_XML = """<?xml version="1.0" encoding="UTF-8"?>
<ConfigurableModel xmlns="http://www.smartconservationsoftware.org/xml/1.0/configurablemodel">
  <name value="Test CM" language_code="en"/>
  <nodes/>
  <attributeConfig id="cfg-1" attributeKey="Wildlife.State" isDefault="true">
    <listItem keyRef="Healthy" isActive="true"/>
    <listItem keyRef="Injured" isActive="true"/>
  </attributeConfig>
</ConfigurableModel>
"""


def _base_datamodel():
    dm = DataModel(use_language_code="en")
    dm.load(open("tests/data/datamodel.xml").read())
    return dm


def test_datamodel_resolves_tree_leaf_from_sanitized_value():
    dm = _base_datamodel()
    assert dm.resolve_option_key(key="causeofdeath", value="natural_disease") == "natural.disease"


def test_datamodel_returns_exact_key_unchanged():
    dm = _base_datamodel()
    assert dm.resolve_option_key(key="causeofdeath", value="natural.disease") == "natural.disease"


def test_datamodel_raises_for_attribute_without_options():
    dm = _base_datamodel()
    with pytest.raises(UnresolvableOptionKey):
        dm.resolve_option_key(key="amountpaid", value="10")  # NUMERIC: options is None


def test_datamodel_raises_for_unknown_attribute():
    dm = _base_datamodel()
    with pytest.raises(UnresolvableOptionKey, match="no_such_attribute"):
        dm.resolve_option_key(key="no_such_attribute", value="x")


def test_configurable_datamodel_resolves_from_curated_options():
    cdm = ConfigurableDataModel(use_language_code="en", cm_uuid="cm-1")
    cdm.load(MINIMAL_CM_XML)
    assert cdm.resolve_option_key(key="Wildlife.State", value="healthy") == "Healthy"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /Users/chrisdo/padas/smartconnect-client && pytest tests/test_choices.py -q -k "datamodel"`
Expected: FAIL with `AttributeError: 'DataModel' object has no attribute 'resolve_option_key'`

- [ ] **Step 3: Add the methods**

At the top of `smartconnect/models.py`, after the pydantic import on line 7:

```python
from smartconnect.choices import UnresolvableOptionKey, resolve_option_key
```

In `DataModel`, directly after `get_attribute` (ends at line 285):

```python
    def resolve_option_key(self, *, key: str, value: str) -> str:
        """Map an ER Choice value back to the SMART option key of attribute ``key``."""
        attribute = self.get_attribute(key=key)
        if not attribute:
            raise UnresolvableOptionKey(f"Attribute {key!r} not found in data model")
        option_keys = [option["key"] for option in attribute.get("options") or []]
        return resolve_option_key(option_keys, value)
```

In `ConfigurableDataModel`, directly after its `get_attribute` (ends at line 453), the identical method body.

- [ ] **Step 4: Run the whole suite**

Run: `cd /Users/chrisdo/padas/smartconnect-client && pytest -q`
Expected: all passed (the pre-existing suite plus 24 in `test_choices.py`)

- [ ] **Step 5: Commit**

```bash
cd /Users/chrisdo/padas/smartconnect-client
git add smartconnect/models.py tests/test_choices.py
git commit -m "Add resolve_option_key to DataModel and ConfigurableDataModel

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: Version bump, PR and release

**Files:**
- Modify: `pyproject.toml:3`

- [ ] **Step 1: Bump the version**

Change line 3 of `pyproject.toml` from `version = "1.14.0"` to `version = "1.15.0"`.

- [ ] **Step 2: Build check**

Run: `cd /Users/chrisdo/padas/smartconnect-client && uv build && ls dist/ | grep 1.15.0`
Expected: `smartconnect_client-1.15.0-py3-none-any.whl` and the sdist listed.

- [ ] **Step 3: Commit and open the PR**

```bash
cd /Users/chrisdo/padas/smartconnect-client
git add pyproject.toml
git commit -m "chore: bump version to 1.15.0

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
git push -u origin feature/choice-value-helpers
gh pr create --title "Shared choice value rules and resolve_option_key (1.15.0)" --body "$(cat <<'BODY'
Adds smartconnect/choices.py with the sanitize and hash-shortening rules er-smart-sync uses to derive ER Choice values from SMART option keys, plus resolve_option_key for the inverse lookup, exposed on DataModel and ConfigurableDataModel. Needed so cdip-routing can map v2 ER event values back to SMART option keys and so er-smart-sync imports one definition instead of its own copy.

Spec: PADAS/cdip docs/superpowers/specs/2026-10-09-er-smart-sync-v2-migration-design.md

🤖 Generated with [Claude Code](https://claude.com/claude-code)
BODY
)"
```

- [ ] **Step 4: After merge, tag the release**

```bash
cd /Users/chrisdo/padas/smartconnect-client
git checkout main && git pull
git tag v1.15.0 && git push origin v1.15.0
```

Then watch `gh run list --workflow=release.yml --limit 1` until it succeeds and confirm `pip index versions smartconnect-client` shows 1.15.0. Part 2 of this series depends on that PyPI release.
