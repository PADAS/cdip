# Design — remove a device from a device group

## Problem

The device group edit slide panel now shows a read-only "Devices in group"
section (see `docs/device-group-devices-section-plan.md`). There is no way to
remove a device from a group directly from this panel — removal currently
requires the separate Manage Devices view.

## Goal

Let a user remove a device from a device group directly in the edit panel:
a clickable trash icon on each device row, with an inline confirmation before
the removal takes effect.

- **Removal = M2M unlink.** `DeviceGroup.devices` is a `ManyToManyField`, so
  removing means `device_group.devices.remove(device)`. The `Device` row itself
  is **not** deleted.
- **Removal only.** Adding new devices to a group stays in the existing Manage
  Devices view; this change does not add device-creation here.
- Mirrors the existing destination-removal pattern in the same panel for
  consistency (`device_group_destinations_remove`).

## How removal works today for destinations (pattern to mirror)

`device_group_destinations_partial.html` renders, per destination row, a
"Remove" button that reveals an inline confirm via hyperscript:

```django
<span class="remove-btn-{{ dest.id }}">
    <button class="btn btn-outline-danger btn-sm"
            _="on click hide .remove-btn-{{ dest.id }} then show .confirm-remove-{{ dest.id }} with display:flex">
        Remove
    </button>
</span>
<span class="confirm-remove-{{ dest.id }} ..." style="display: none; ...">
    <small>Remove {{ dest.name|default:dest }}?</small>
    <button class="btn btn-danger btn-sm"
            hx-post="{% url 'device_group_destinations_remove' device_group_id=device_group_id outbound_id=dest.id %}"
            hx-target="#device-group-destinations-section"
            hx-swap="outerHTML">Confirm</button>
    <button class="btn btn-secondary btn-sm"
            _="on click hide .confirm-remove-{{ dest.id }} then show .remove-btn-{{ dest.id }}">Cancel</button>
</span>
```

The backing view:

```python
@require_POST
@permission_required("integrations.change_devicegroup", raise_exception=True)
def device_group_destinations_remove(request, device_group_id, outbound_id):
    device_group = get_object_or_404(DeviceGroup, pk=device_group_id)
    permission_can_view(request, device_group)
    ...
    device_group.destinations.remove(outbound)
    context = _device_group_destinations_context(device_group, request)
    return render(request, "integrations/device_group_destinations_partial.html", context)
```

CSRF for the `hx-post` rides on the global `htmx:configRequest` handler in
`base.html`, which sets the `X-CSRFToken` header — no per-row `{% csrf_token %}`
needed. (This is the handler made reliable by the CSRF token-rotation fix.)

## Components

### 1. View — `integrations/views.py`

Add next to `device_group_destinations_remove`:

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

### 2. URL — `integrations/urls.py`

Add next to the devices-list route:

```python
path(
    "devicegroups/<uuid:device_group_id>/devices/<uuid:device_id>/remove",
    views.device_group_devices_remove,
    name="device_group_devices_remove",
),
```

### 3. Template — `device_group_devices_partial.html`

Add a right-aligned action column. Each row gets a trash-icon button that
reveals the inline confirm, mirroring destinations:

```django
<th></th>   {# action column header #}
...
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
```

The empty-state and scroll container are unchanged.

### 4. Tests — `integrations/tests/test_integration_views.py`

- `test_device_group_devices_remove_unlinks_device`: POST as global admin
  removes the device from the group (M2M); response 200; the removed device is
  absent from the refreshed `devices` context; the `Device` row still exists.
- `test_device_group_devices_remove_requires_change_permission`: a view-only
  org member gets 403.

## Permissions / visibility

The trash icon renders for any user who can view the section; the POST is gated
server-side by `change_devicegroup` (a view-only user who clicks Confirm gets
403). This matches the existing destinations behavior in the same panel. Hiding
the icon for non-editors is intentionally out of scope for consistency.

## Out of scope

- Adding devices to a group (stays in Manage Devices).
- Deleting the `Device` record (removal is M2M unlink only).
- Hiding the icon for non-editors.
