# Add a Device to a Device Group — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user add an existing device to a device group from the edit panel, via a searchable autocomplete + Add button scoped to the group's org.

**Architecture:** A shared eligibility queryset backs two new views — a `@require_GET` autocomplete returning JSON `[{id,name}]` and a `@require_POST` add view that links the device to the group's `devices` M2M and re-renders the partial. The template gains an Add form whose `<select name="device_id">` lazy-loads matches via the existing `makeLazySelect` helper.

**Tech Stack:** Django 4.2, htmx 1.6, TomSelect 2.3 (via `makeLazySelect` in base.html), pytest + pytest-django.

## Global Constraints

- **Eligibility:** a device is addable iff `device.inbound_configuration.owner == device_group.owner` AND it is not already in the group. One shared helper enforces this for both views.
- **Permissions:** add view = `@require_POST` + `@permission_required("integrations.change_devicegroup", raise_exception=True)`; autocomplete = `@require_GET` + `@permission_required("integrations.view_devicegroup", raise_exception=True)`; both also call `permission_can_view(request, device_group)`.
- **Autocomplete response:** `JsonResponse([{ "id": str, "name": "<external_id> — <inbound type>" }], safe=False)`, capped at 50, ordered by `external_id`.
- **Reuse** `makeLazySelect` (base.html); the device select is `select[name="device_id"]` with a `data-autocomplete-url` attribute.
- `Device`, `DeviceGroup`, `JsonResponse`, `require_GET`, `require_POST`, `permission_required`, `get_object_or_404`, `render`, `permission_can_view` are already imported in `integrations/views.py`. `Device`, `reverse`, `base64`, `json` are already imported at the top of the test file.
- Run tests from the review worktree root: `docker compose run --rm pytest --ds=cdip_admin.settings <path> -p no:cacheprovider`. Test paths are container-relative (no `cdip_admin/` prefix).
- Commit ONLY each task's files with explicit `git add <paths>`. NEVER `git add -A`/`.`/`commit -a` — the worktree has unrelated uncommitted files (`cdip_admin/cdip_admin/auth/middleware.py`, `docker-compose.yml`) that must stay out.

## File Structure

- Modify `cdip_admin/integrations/views.py` — eligibility helper + 2 views.
- Modify `cdip_admin/integrations/urls.py` — 2 routes.
- Modify `cdip_admin/integrations/templates/integrations/device_group_devices_partial.html` — Add form.
- Modify `cdip_admin/website/templates/base.html` — one `initTomSelects` block.
- Modify `cdip_admin/integrations/tests/test_integration_views.py` — backend + template tests.

---

### Task 1: Backend — eligibility helper, autocomplete view, add view, URLs

**Files:**
- Modify: `cdip_admin/integrations/views.py`
- Modify: `cdip_admin/integrations/urls.py`
- Test: `cdip_admin/integrations/tests/test_integration_views.py`

**Interfaces:**
- Consumes: `setup_data` fixture (`dg1` owner `org1` with device `d1`; `d2` owner `org2`; `ii1` owner `org1`); `global_admin_user` (superuser + `.user_info`).
- Produces:
  - `_eligible_devices_for_group(device_group, q="")` → `QuerySet[Device]` (same-org, `external_id__icontains=q`, excluding current members).
  - URL `device_group_devices_add` (kwarg `device_group_id`); POSTs `device_id`; returns rendered `device_group_devices_partial.html` (200).
  - URL `device_group_devices_autocomplete` (kwarg `device_group_id`); GET `q`; returns `JsonResponse([{id,name}])`.

- [ ] **Step 1: Write the failing tests**

Append to `cdip_admin/integrations/tests/test_integration_views.py`:

```python
def test_device_group_devices_add_adds_eligible_device(
        client, global_admin_user, setup_data
):
    dg1 = setup_data["dg1"]
    ii1 = setup_data["ii1"]  # owned by org1, same as dg1
    new_device = Device.objects.create(external_id="new-org1-device", inbound_configuration=ii1)
    assert new_device not in dg1.devices.all()

    client.force_login(global_admin_user.user)
    response = client.post(
        reverse("device_group_devices_add", kwargs={"device_group_id": dg1.id}),
        data={"device_id": str(new_device.id)},
        HTTP_X_USERINFO=global_admin_user.user_info,
    )

    assert response.status_code == 200
    dg1.refresh_from_db()
    assert new_device in dg1.devices.all()
    assert new_device.external_id in response.content.decode()


def test_device_group_devices_add_rejects_other_org_device(
        client, global_admin_user, setup_data
):
    dg1 = setup_data["dg1"]   # owned by org1
    d2 = setup_data["d2"]     # device whose inbound integration is owned by org2

    client.force_login(global_admin_user.user)
    response = client.post(
        reverse("device_group_devices_add", kwargs={"device_group_id": dg1.id}),
        data={"device_id": str(d2.id)},
        HTTP_X_USERINFO=global_admin_user.user_info,
    )

    assert response.status_code == 200      # no-op re-render, not an error
    dg1.refresh_from_db()
    assert d2 not in dg1.devices.all()


def test_device_group_devices_add_requires_change_permission(
        client, django_user_model, setup_data
):
    dg1 = setup_data["dg1"]
    ii1 = setup_data["ii1"]
    new_device = Device.objects.create(external_id="perm-test-device", inbound_configuration=ii1)

    user = django_user_model.objects.create_user(
        username="addviewer@example.com", email="addviewer@example.com"
    )
    user_info = base64.b64encode(
        json.dumps({"sub": str(user.id), "username": user.username, "email": user.email}).encode("utf-8")
    )
    client.force_login(user)
    response = client.post(
        reverse("device_group_devices_add", kwargs={"device_group_id": dg1.id}),
        data={"device_id": str(new_device.id)},
        HTTP_X_USERINFO=user_info,
    )

    assert response.status_code == 403
    dg1.refresh_from_db()
    assert new_device not in dg1.devices.all()


def test_device_group_devices_autocomplete_returns_eligible(
        client, global_admin_user, setup_data
):
    dg1 = setup_data["dg1"]
    d1 = setup_data["d1"]   # already in dg1
    d2 = setup_data["d2"]   # other org
    ii1 = setup_data["ii1"]
    eligible = Device.objects.create(external_id="autocomplete-eligible", inbound_configuration=ii1)

    client.force_login(global_admin_user.user)
    response = client.get(
        reverse("device_group_devices_autocomplete", kwargs={"device_group_id": dg1.id}),
        data={"q": ""},
        HTTP_X_USERINFO=global_admin_user.user_info,
    )

    assert response.status_code == 200
    results = response.json()
    ids = {r["id"] for r in results}
    assert str(eligible.id) in ids      # same org, not in group
    assert str(d1.id) not in ids        # already in group
    assert str(d2.id) not in ids        # other org
    assert all("id" in r and "name" in r for r in results)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `docker compose run --rm pytest --ds=cdip_admin.settings "integrations/tests/test_integration_views.py" -k "device_group_devices_add or device_group_devices_autocomplete" -p no:cacheprovider -q`
Expected: FAIL — `NoReverseMatch: Reverse for 'device_group_devices_add' not found` (and the autocomplete name).

- [ ] **Step 3: Add the helper and views**

In `cdip_admin/integrations/views.py`, immediately after the `device_group_devices_remove` function, add:

```python
def _eligible_devices_for_group(device_group, q=""):
    """Devices addable to this group: same owning org, matching external_id,
    not already in the group."""
    return (
        Device.objects
        .filter(inbound_configuration__owner=device_group.owner)
        .filter(external_id__icontains=q)
        .exclude(id__in=device_group.devices.values_list("id", flat=True))
        .select_related("inbound_configuration__type")
        .order_by("external_id")
    )


@require_GET
@permission_required("integrations.view_devicegroup", raise_exception=True)
def device_group_devices_autocomplete(request, device_group_id):
    device_group = get_object_or_404(DeviceGroup, pk=device_group_id)
    permission_can_view(request, device_group)
    q = request.GET.get("q", "")
    devices = _eligible_devices_for_group(device_group, q)[:50]
    results = [
        {"id": str(d.id), "name": f"{d.external_id} — {d.inbound_configuration.type.name}"}
        for d in devices
    ]
    return JsonResponse(results, safe=False)


@require_POST
@permission_required("integrations.change_devicegroup", raise_exception=True)
def device_group_devices_add(request, device_group_id):
    device_group = get_object_or_404(DeviceGroup, pk=device_group_id)
    permission_can_view(request, device_group)
    device_id = request.POST.get("device_id")
    if device_id and _eligible_devices_for_group(device_group).filter(pk=device_id).exists():
        device_group.devices.add(Device.objects.get(pk=device_id))
    context = {
        "devices": device_group.devices.select_related("inbound_configuration__type"),
        "device_group_id": device_group_id,
    }
    return render(request, "integrations/device_group_devices_partial.html", context)
```

- [ ] **Step 4: Add the URLs**

In `cdip_admin/integrations/urls.py`, in the "Device Group Devices" block (next to `device_group_devices_remove`), add:

```python
    path(
        "devicegroups/<uuid:device_group_id>/devices/add",
        views.device_group_devices_add,
        name="device_group_devices_add",
    ),
    path(
        "devicegroups/<uuid:device_group_id>/devices/autocomplete",
        views.device_group_devices_autocomplete,
        name="device_group_devices_autocomplete",
    ),
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `docker compose run --rm pytest --ds=cdip_admin.settings "integrations/tests/test_integration_views.py" -k "device_group_devices_add or device_group_devices_autocomplete" -p no:cacheprovider -q`
Expected: PASS (4 passed).

- [ ] **Step 6: Commit**

```bash
git add cdip_admin/integrations/views.py cdip_admin/integrations/urls.py cdip_admin/integrations/tests/test_integration_views.py
git commit -m "feat: add device_group_devices_add and autocomplete views"
```

---

### Task 2: Frontend — Add form + lazy-select wiring

**Files:**
- Modify: `cdip_admin/integrations/templates/integrations/device_group_devices_partial.html`
- Modify: `cdip_admin/website/templates/base.html`
- Test: `cdip_admin/integrations/tests/test_integration_views.py`

**Interfaces:**
- Consumes: URL names `device_group_devices_add`, `device_group_devices_autocomplete` (Task 1); `makeLazySelect(el, url)` + `initTomSelects(root)` in base.html; context key `device_group_id`.
- Produces: an Add form with `select[name="device_id"]` carrying `data-autocomplete-url`, posting to the add view; `initTomSelects` initializes that select.

- [ ] **Step 1: Write the failing test**

Append to `cdip_admin/integrations/tests/test_integration_views.py`:

```python
def test_device_group_devices_list_shows_add_form(
        client, global_admin_user, setup_data
):
    dg1 = setup_data["dg1"]

    client.force_login(global_admin_user.user)
    response = client.get(
        reverse("device_group_devices_list", kwargs={"device_group_id": dg1.id}),
        HTTP_X_USERINFO=global_admin_user.user_info,
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert 'name="device_id"' in content
    assert reverse("device_group_devices_add", kwargs={"device_group_id": dg1.id}) in content
    assert reverse("device_group_devices_autocomplete", kwargs={"device_group_id": dg1.id}) in content
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `docker compose run --rm pytest --ds=cdip_admin.settings "integrations/tests/test_integration_views.py::test_device_group_devices_list_shows_add_form" -p no:cacheprovider -q`
Expected: FAIL — `assert 'name="device_id"' in content` (no Add form yet).

- [ ] **Step 3: Add the Add form to the partial**

In `cdip_admin/integrations/templates/integrations/device_group_devices_partial.html`, add the following immediately **before** the final closing `</div>` of `#device-group-devices-section` (after the `{% endif %}` that closes the table / empty-state block, so it shows in both states):

```django
    <form hx-post="{% url 'device_group_devices_add' device_group_id=device_group_id %}"
          hx-target="#device-group-devices-section"
          hx-swap="outerHTML"
          class="form-inline mb-1">
        {% csrf_token %}
        <select name="device_id"
                class="form-control form-control-sm mr-2 device-select"
                data-autocomplete-url="{% url 'device_group_devices_autocomplete' device_group_id=device_group_id %}?q="
                required>
        </select>
        <button type="submit" class="btn btn-outline-primary btn-sm">Add device</button>
    </form>
```

- [ ] **Step 4: Wire the lazy-select in base.html**

In `cdip_admin/website/templates/base.html`, inside `function initTomSelects(root) { ... }`, after the `select[name="default_devicegroup"]` block (the one ending around line 85), add:

```javascript
            root.querySelectorAll('select[name="device_id"]').forEach(function(el) {
                if (!el.tomselect) {
                    makeLazySelect(el, el.dataset.autocompleteUrl);
                }
            });
```

- [ ] **Step 5: Run the template test + device_group regression**

Run: `docker compose run --rm pytest --ds=cdip_admin.settings "integrations/tests/test_integration_views.py::test_device_group_devices_list_shows_add_form" -p no:cacheprovider -q`
Expected: PASS.

Run: `docker compose run --rm pytest --ds=cdip_admin.settings "integrations/tests/test_integration_views.py" -k device_group -p no:cacheprovider -q`
Expected: all device_group tests pass.

- [ ] **Step 6: Commit**

```bash
git add cdip_admin/integrations/templates/integrations/device_group_devices_partial.html cdip_admin/website/templates/base.html cdip_admin/integrations/tests/test_integration_views.py
git commit -m "feat: add-device form with searchable autocomplete in device group panel"
```

---

### Task 3: Live verification

**Files:** none (verification in the running stack).

- [ ] **Step 1: Autocomplete endpoint returns JSON (read-only check)**

In the running stack, render-check the partial includes the Add form:
```bash
docker compose exec -T web python3.11 manage.py shell -c "
from django.template.loader import render_to_string
import uuid
html = render_to_string('integrations/device_group_devices_partial.html', {'devices':[], 'device_group_id': uuid.UUID('22222222-2222-2222-2222-222222222222')})
print('add form:', 'name=\"device_id\"' in html)
print('autocomplete url:', '/devices/autocomplete' in html)
print('add url:', '/devices/add' in html)
"
```
Expected: all three print `True`.

- [ ] **Step 2: Browser check (against an env with eligible devices)**

Open a device group in the edit panel. Confirm: the "Add device" search box appears below the list; typing filters devices (by `external_id`) from the same org, excluding ones already in the group; selecting one and clicking **Add device** adds it and the section re-renders with the new row. (The local dev DB may have no eligible devices; verify in a feature env.)

---

## Self-Review

**Spec coverage:** eligibility helper (Task 1), autocomplete view (Task 1), add view + guard (Task 1), URLs (Task 1), template Add form (Task 2), base.html lazy-select wiring (Task 2), permissions (Task 1 decorators + 403 test), tests for add/reject/permission/autocomplete (Task 1) and form render (Task 2), live verification (Task 3). All spec sections covered.

**Placeholder scan:** No TBD/TODO; every code step shows complete code and exact commands.

**Type consistency:** `_eligible_devices_for_group(device_group, q="")`, `device_group_devices_add`/`device_group_devices_autocomplete` view+URL names, the `device_id` POST/select name, the `data-autocomplete-url` attribute, and the `#device-group-devices-section` target are consistent across views, URLs, template, base.html, and tests. Autocomplete returns `{id, name}`, matching what `makeLazySelect` consumes (`valueField:'id'`, `labelField:'name'`).
