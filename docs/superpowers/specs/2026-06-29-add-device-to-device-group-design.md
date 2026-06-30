# Design — add a device to a device group

## Problem

The device group edit slide panel can now list and remove devices, but there is
no way to **add** a device to a group from the panel. Adding currently lives
only in the separate Manage Devices view. Users want a quick add directly in the
panel, next to the devices list.

## Goal

Add an "Add device" control to the "Devices in group" section: a **searchable
autocomplete** (type to search by `external_id`) plus an **Add** button. On add,
the device is linked to the group (`devices` M2M) and the section re-renders in
place — mirroring the existing destination-add and the device-remove flows.

- **Searchable, not a preloaded dropdown.** Devices can be numerous, so the
  select lazy-loads matches from a new device-search endpoint (reusing the
  `makeLazySelect` pattern used for the owner / device-group fields), rather than
  preloading every option like the "Add Destination" control does.
- **Eligibility = same org as the group.** Only devices whose inbound
  integration is owned by the group's organization
  (`device.inbound_configuration.owner == device_group.owner`), excluding
  devices already in the group.
- **Add only.** Removal already exists; bulk management stays in Manage Devices.

## Existing patterns this mirrors

- `device_group_destinations_add` (`integrations/views.py`): `@require_POST` +
  `@permission_required("integrations.change_devicegroup", raise_exception=True)`,
  `permission_can_view`, mutate the relation, re-render the partial.
- `device_group_autocomplete` (`integrations/views.py`): `@require_GET`, filter by
  `q`, scope by permission, return `JsonResponse([{ "id": ..., "name": ... }])`.
- `base.html` `makeLazySelect(el, url)` + `initTomSelects(root)`: `initTomSelects`
  runs on `DOMContentLoaded` (line 89) and on `htmx:afterSettle` (line 93,
  `initTomSelects(evt.detail.elt)`). `makeLazySelect` builds a TomSelect with
  `valueField:'id'`, `labelField:'name'`, `searchField:'name'`, and `load:` that
  does `fetch(url + encodeURIComponent(query))` expecting `[{id, name}]`.

`Device.owner` is a property returning `inbound_configuration.owner`;
`DeviceGroup.owner` is an FK to the owning organization.
`JsonResponse`, `require_GET`, `require_POST`, `permission_required`,
`permission_can_view`, `Device`, and `DeviceGroup` are already imported in
`integrations/views.py`.

## Components

### 1. Shared eligibility helper — `integrations/views.py`

One queryset, used by both the autocomplete and the add-view guard (DRY):

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
```

### 2. Autocomplete view — `integrations/views.py`

```python
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
```

Scoping to the group's org plus `permission_can_view` means the endpoint cannot
leak devices the user shouldn't see.

### 3. Add view — `integrations/views.py`

```python
@require_POST
@permission_required("integrations.change_devicegroup", raise_exception=True)
def device_group_devices_add(request, device_group_id):
    device_group = get_object_or_404(DeviceGroup, pk=device_group_id)
    permission_can_view(request, device_group)
    device_id = request.POST.get("device_id")
    # Eligibility guard (defense against a crafted POST): only add a device that
    # is in the eligible set (same org, not already in the group).
    if device_id and _eligible_devices_for_group(device_group).filter(pk=device_id).exists():
        device_group.devices.add(Device.objects.get(pk=device_id))
    context = {
        "devices": device_group.devices.select_related("inbound_configuration__type"),
        "device_group_id": device_group_id,
    }
    return render(request, "integrations/device_group_devices_partial.html", context)
```

An ineligible or missing `device_id` is a no-op that simply re-renders the
current list (the UI never offers ineligible devices).

### 4. URLs — `integrations/urls.py`

In the "Device Group Devices" block:

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

### 5. Template — `device_group_devices_partial.html`

After the table / empty-state block (so it shows in both states), add the form:

```django
<form hx-post="{% url 'device_group_devices_add' device_group_id=device_group_id %}"
      hx-target="#device-group-devices-section"
      hx-swap="outerHTML"
      class="form-inline mb-3">
    {% csrf_token %}
    <select name="device_id"
            class="form-control form-control-sm mr-2 device-select"
            data-autocomplete-url="{% url 'device_group_devices_autocomplete' device_group_id=device_group_id %}?q="
            required>
    </select>
    <button type="submit" class="btn btn-outline-primary btn-sm">Add device</button>
</form>
```

The `<select>` starts empty; TomSelect lazy-loads options from
`data-autocomplete-url` on focus/typing. `{% csrf_token %}` is included (the form
is serialized by htmx on `hx-post`), consistent with the destinations add form.

### 6. JS wiring — `website/templates/base.html`

Add one block to `initTomSelects(root)` (alongside the `owner` and
`default_devicegroup` blocks), so the device search initializes on initial
lazy-load and on every re-render swap:

```javascript
root.querySelectorAll('select[name="device_id"]').forEach(function(el) {
    if (!el.tomselect) {
        makeLazySelect(el, el.dataset.autocompleteUrl);
    }
});
```

## Permissions / visibility

The Add form renders for anyone who can view the section; the `add` POST is gated
by `change_devicegroup` and the autocomplete by `view_devicegroup` (both plus
`permission_can_view`). This matches the remove and destinations controls.

## Tests — `integrations/tests/test_integration_views.py`

- **add adds an eligible device**: POST a same-org device not yet in the group →
  200, device now in `device_group.devices`, refreshed partial lists it.
- **add rejects an other-org device**: POST a device whose inbound integration is
  owned by a different org → group membership unchanged (no-op), 200.
- **add requires change permission**: a user without `change_devicegroup` → 403,
  membership unchanged.
- **autocomplete returns eligible matches**: returns same-org devices matching
  `q`, excludes devices already in the group and devices from other orgs; result
  items have `id` and `name`.

## Out of scope

- Creating a brand-new Device (this only links existing devices).
- Bulk add (stays in Manage Devices).
- Cross-org device membership.
- Hiding the Add form from non-editors (server-gated, consistent with peers).
