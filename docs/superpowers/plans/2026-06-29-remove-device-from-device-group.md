# Remove a Device from a Device Group — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user remove a device from a device group via a trash icon with inline confirmation in the device group edit slide panel.

**Architecture:** Mirror the existing destination-removal flow in the same panel. A new `@require_POST` view unlinks the device from the group's `devices` M2M and re-renders the devices partial; htmx swaps the section in place. The trash icon reveals an inline "Remove …? Confirm/Cancel" via hyperscript, exactly like destinations.

**Tech Stack:** Django 4.2, htmx 1.6, hyperscript, FontAwesome (all already loaded in `base.html`), pytest + pytest-django.

## Global Constraints

- Removal is an **M2M unlink** (`device_group.devices.remove(device)`) — never deletes the `Device` row.
- Mirror `device_group_destinations_remove` for the view, URL, and template patterns.
- CSRF for `hx-post` rides on the global `htmx:configRequest` handler in `base.html` — no per-row `{% csrf_token %}`.
- Run tests from the review worktree root with:
  `docker compose run --rm pytest --ds=cdip_admin.settings <path> -p no:cacheprovider`
  Test paths are container-relative (no `cdip_admin/` prefix), e.g. `integrations/tests/test_integration_views.py`.
- `Device`, `require_POST`, and `permission_required` are already imported in `integrations/views.py`.

## File Structure

- Modify `cdip_admin/integrations/views.py` — add `device_group_devices_remove` view.
- Modify `cdip_admin/integrations/urls.py` — add `device_group_devices_remove` route.
- Modify `cdip_admin/integrations/templates/integrations/device_group_devices_partial.html` — add action column with trash icon + inline confirm.
- Modify `cdip_admin/integrations/tests/test_integration_views.py` — add backend + template tests.

---

### Task 1: Backend — remove view + URL

**Files:**
- Modify: `cdip_admin/integrations/views.py` (add view next to `device_group_destinations_remove`)
- Modify: `cdip_admin/integrations/urls.py` (add route next to `device_group_devices_list`)
- Test: `cdip_admin/integrations/tests/test_integration_views.py`

**Interfaces:**
- Consumes: `DeviceGroup.devices` (M2M), `permission_can_view(request, target)`, `setup_data` fixture (`dg1` owned by `org1`, with device `d1`), `global_admin_user` fixture (superuser + `.user_info` header).
- Produces: URL name `device_group_devices_remove` with kwargs `device_group_id`, `device_id`; view `device_group_devices_remove(request, device_group_id, device_id)` returning the rendered `device_group_devices_partial.html` (HTTP 200) after unlinking.

- [ ] **Step 1: Write the failing tests**

Append to `cdip_admin/integrations/tests/test_integration_views.py`:

```python
def test_device_group_devices_remove_unlinks_device(
        client, global_admin_user, setup_data
):
    dg1 = setup_data["dg1"]
    d1 = setup_data["d1"]
    assert d1 in dg1.devices.all()

    client.force_login(global_admin_user.user)

    response = client.post(
        reverse(
            "device_group_devices_remove",
            kwargs={"device_group_id": dg1.id, "device_id": d1.id},
        ),
        HTTP_X_USERINFO=global_admin_user.user_info,
    )

    assert response.status_code == 200
    dg1.refresh_from_db()
    # Unlinked from the group...
    assert d1 not in dg1.devices.all()
    # ...but the Device row still exists.
    assert Device.objects.filter(pk=d1.id).exists()
    # dg1 had only d1, so the refreshed partial shows the empty state.
    assert "No devices in this group." in response.content.decode()


def test_device_group_devices_remove_requires_change_permission(
        client, django_user_model, setup_data
):
    import base64
    import json

    dg1 = setup_data["dg1"]
    d1 = setup_data["d1"]

    # Plain user (no perms) -- create_user, NOT create_superuser.
    user = django_user_model.objects.create_user(
        username="viewer@example.com", email="viewer@example.com"
    )
    user_info = base64.b64encode(
        json.dumps(
            {"sub": str(user.id), "username": user.username, "email": user.email}
        ).encode("utf-8")
    )
    client.force_login(user)

    response = client.post(
        reverse(
            "device_group_devices_remove",
            kwargs={"device_group_id": dg1.id, "device_id": d1.id},
        ),
        HTTP_X_USERINFO=user_info,
    )

    assert response.status_code == 403
    assert d1 in dg1.devices.all()  # unchanged
```

Note: `Device` and `reverse` are already imported at the top of this test file (used by existing tests).

- [ ] **Step 2: Run the tests to verify they fail**

Run: `docker compose run --rm pytest --ds=cdip_admin.settings "integrations/tests/test_integration_views.py::test_device_group_devices_remove_unlinks_device" "integrations/tests/test_integration_views.py::test_device_group_devices_remove_requires_change_permission" -p no:cacheprovider -q`
Expected: FAIL — `NoReverseMatch: Reverse for 'device_group_devices_remove' not found`.

- [ ] **Step 3: Add the view**

In `cdip_admin/integrations/views.py`, immediately after the `device_group_destinations_remove` function, add:

```python
@require_POST
@permission_required("integrations.change_devicegroup", raise_exception=True)
def device_group_devices_remove(request, device_group_id, device_id):
    device_group = get_object_or_404(DeviceGroup, pk=device_group_id)
    permission_can_view(request, device_group)
    device = get_object_or_404(Device, pk=device_id)
    device_group.devices.remove(device)
    context = {
        "devices": device_group.devices.all(),
        "device_group_id": device_group_id,
    }
    return render(request, "integrations/device_group_devices_partial.html", context)
```

- [ ] **Step 4: Add the URL**

In `cdip_admin/integrations/urls.py`, in the "Device Group Devices" block (next to the `device_group_devices_list` route), add:

```python
    path(
        "devicegroups/<uuid:device_group_id>/devices/<uuid:device_id>/remove",
        views.device_group_devices_remove,
        name="device_group_devices_remove",
    ),
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `docker compose run --rm pytest --ds=cdip_admin.settings "integrations/tests/test_integration_views.py::test_device_group_devices_remove_unlinks_device" "integrations/tests/test_integration_views.py::test_device_group_devices_remove_requires_change_permission" -p no:cacheprovider -q`
Expected: PASS (2 passed).

- [ ] **Step 6: Commit**

```bash
git add cdip_admin/integrations/views.py cdip_admin/integrations/urls.py cdip_admin/integrations/tests/test_integration_views.py
git commit -m "feat: add device_group_devices_remove view and URL"
```

---

### Task 2: Template — trash icon + inline confirm

**Files:**
- Modify: `cdip_admin/integrations/templates/integrations/device_group_devices_partial.html`
- Test: `cdip_admin/integrations/tests/test_integration_views.py`

**Interfaces:**
- Consumes: URL name `device_group_devices_remove` (from Task 1); `device_group_id` and `devices` in the partial context; section id `#device-group-devices-section`.
- Produces: each device row renders a remove control posting to `device_group_devices_remove`, targeting `#device-group-devices-section` with `outerHTML` swap.

- [ ] **Step 1: Write the failing test**

Append to `cdip_admin/integrations/tests/test_integration_views.py`:

```python
def test_device_group_devices_list_shows_remove_control(
        client, global_admin_user, setup_data
):
    dg1 = setup_data["dg1"]
    d1 = setup_data["d1"]

    client.force_login(global_admin_user.user)

    response = client.get(
        reverse("device_group_devices_list", kwargs={"device_group_id": dg1.id}),
        HTTP_X_USERINFO=global_admin_user.user_info,
    )

    assert response.status_code == 200
    content = response.content.decode()
    # Trash icon present...
    assert "fa-trash" in content
    # ...wired to the remove endpoint for this device.
    assert reverse(
        "device_group_devices_remove",
        kwargs={"device_group_id": dg1.id, "device_id": d1.id},
    ) in content
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `docker compose run --rm pytest --ds=cdip_admin.settings "integrations/tests/test_integration_views.py::test_device_group_devices_list_shows_remove_control" -p no:cacheprovider -q`
Expected: FAIL — `assert 'fa-trash' in content` (the partial has no remove control yet).

- [ ] **Step 3: Add the action column to the partial**

Replace the entire contents of `cdip_admin/integrations/templates/integrations/device_group_devices_partial.html` with:

```django
<div id="device-group-devices-section" class="mt-4">
    <h5>Devices in group</h5>
    {% if devices %}
    <div style="max-height: 240px; overflow-y: auto;">
        <table class="table table-sm table-bordered">
            <thead class="thead-light">
                <tr>
                    <th>External ID</th>
                    <th>Created</th>
                    <th></th>
                </tr>
            </thead>
            <tbody>
                {% for dev in devices %}
                <tr>
                    <td>
                        <a href="#"
                           hx-get="{% url 'device_update' module_id=dev.id %}"
                           hx-target="#slide-panel-body"
                           hx-swap="innerHTML">{{ dev.external_id|default:dev }}</a>
                    </td>
                    <td class="text-muted">{{ dev.created_at|date:"M j, Y" }}</td>
                    <td class="text-right">
                        <span class="remove-device-btn-{{ dev.id }}">
                            <button class="btn btn-outline-danger btn-sm"
                                    title="Remove from group"
                                    _="on click hide .remove-device-btn-{{ dev.id }} then show .confirm-remove-device-{{ dev.id }} with display:flex">
                                <i class="fas fa-trash"></i>
                            </button>
                        </span>
                        <span class="confirm-remove-device-{{ dev.id }} align-items-center justify-content-end"
                              style="display: none; gap: .4rem;">
                            <small class="text-muted">Remove {{ dev.external_id|default:dev }}?</small>
                            <button class="btn btn-danger btn-sm"
                                    hx-post="{% url 'device_group_devices_remove' device_group_id=device_group_id device_id=dev.id %}"
                                    hx-target="#device-group-devices-section"
                                    hx-swap="outerHTML">Confirm</button>
                            <button class="btn btn-secondary btn-sm"
                                    _="on click hide .confirm-remove-device-{{ dev.id }} then show .remove-device-btn-{{ dev.id }}">Cancel</button>
                        </span>
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
    {% else %}
    <p class="text-muted">No devices in this group.</p>
    {% endif %}
</div>
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `docker compose run --rm pytest --ds=cdip_admin.settings "integrations/tests/test_integration_views.py::test_device_group_devices_list_shows_remove_control" -p no:cacheprovider -q`
Expected: PASS.

- [ ] **Step 5: Re-run the device-group tests to confirm no regression**

Run: `docker compose run --rm pytest --ds=cdip_admin.settings "integrations/tests/test_integration_views.py" -k device_group -p no:cacheprovider -q`
Expected: all `device_group` tests pass (list, devices list, devices remove, remove permission, remove control).

- [ ] **Step 6: Commit**

```bash
git add cdip_admin/integrations/templates/integrations/device_group_devices_partial.html cdip_admin/integrations/tests/test_integration_views.py
git commit -m "feat: trash icon + inline confirm to remove a device from a group"
```

---

### Task 3: Live verification

**Files:** none (manual verification in the running stack).

- [ ] **Step 1: Confirm the partial renders the remove control (read-only, no DB writes)**

Run:
```bash
docker compose exec -T web python3.11 manage.py shell -c "
from django.template.loader import render_to_string
from integrations.models.v1.models import Device
import uuid, datetime
d = Device(id=uuid.UUID('11111111-1111-1111-1111-111111111111'), external_id='012345-67-8901')
d.created_at = datetime.datetime(2023,5,26)
print(render_to_string('integrations/device_group_devices_partial.html', {'devices':[d], 'device_group_id': uuid.uuid4()}))
"
```
Expected: HTML contains the `fa-trash` button, the `confirm-remove-device-…` span, and an `hx-post` to `/integrations/devicegroups/…/devices/11111111-…/remove`.

- [ ] **Step 2: Browser check (against an env with a populated group)**

Open a device group with devices in the edit panel. Confirm: trash icon on each row → click reveals inline "Remove <external_id>? Confirm / Cancel" → Confirm removes the row and the section re-renders (or shows "No devices in this group."); Cancel restores the icon. (The local dev DB has no populated group; verify in a feature env.)

---

## Self-Review

**Spec coverage:** View (Task 1), URL (Task 1), template trash icon + inline confirm (Task 2), M2M-unlink semantics (Task 1 test asserts Device still exists), permission gate (Task 1 403 test), tests (Tasks 1–2), live verification (Task 3). All spec sections covered.

**Placeholder scan:** No TBD/TODO; every code step shows complete code and exact commands.

**Type consistency:** `device_group_devices_remove(request, device_group_id, device_id)` and URL kwargs `device_group_id`/`device_id` match across view, URL, template, and tests. Section id `#device-group-devices-section` matches the partial root and the `hx-target`. Hyperscript class names `remove-device-btn-<id>` / `confirm-remove-device-<id>` are paired consistently.
