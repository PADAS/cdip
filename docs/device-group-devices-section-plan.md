# Plan — devices section in the device group edit panel

> **This PR is for discussion and planning only.** It contains no production
> code changes — just this plan document and an HTML mock. Someone else will
> implement and test it. The author cannot run the portal locally, so the plan
> was derived by reading the code, not by running the UI.

## Problem

On the **Device Groups** list (`/integrations/devicegroups`), the only action on a
group is **Edit**, which opens a slide panel showing the group's form fields and
its **Destinations** section. There is no way to see the **list of devices** that
belong to the group, and no deep link from a device to its configuration.

The `DeviceGroupDetail` view (`devicegroups/<uuid:module_id>`) does render a device
table, but it is not reachable from the current list UI (rows open the Edit panel,
not the detail page).

## Goal

Add a **read-only** "Devices in group" section to the device group **Edit** slide
panel, listing each device by `external_id`, where each device links to its own
configuration. The device config opens in the **same** slide panel (content
swapped), exactly like clicking an outbound destination does today.

- Devices section appears **above** the Destinations section.
- Read-only — adding/removing devices stays in the existing **Manage Devices** view.

## How it works today (verified in code)

- The edit panel partial `integrations/device_group_update_partial.html` lazy-loads
  the destinations section via HTMX:
  ```django
  <div id="device-group-destinations-section"
       hx-get="{% url 'device_group_destinations_list' device_group_id=form.instance.id %}"
       hx-trigger="load" hx-swap="outerHTML">
  ```
- `device_group_destinations_list` (in `integrations/views.py`) renders
  `device_group_destinations_partial.html`.
- In that partial, clicking a destination swaps the outbound config form into the
  **same** panel:
  ```django
  <a href="#"
     hx-get="{% url 'outbound_integration_configuration_update' configuration_id=dest.id %}"
     hx-target="#slide-panel-body" hx-swap="innerHTML">{{ dest.name }}</a>
  ```
  This is not an illusion — `OutboundIntegrationConfigurationUpdateView.get` detects
  the `HX-Request` header and returns `..._update_partial.html` (panel body only),
  which HTMX swaps into `#slide-panel-body`.
- `DeviceUpdateView.get` already does the same: on `HX-Request` it renders
  `device_update_partial.html`. So a device link with
  `hx-target="#slide-panel-body" hx-swap="innerHTML"` will behave identically.
- `DeviceGroup.devices` is a `ManyToManyField(Device)`, so the device list is just
  `device_group.devices.all()`.

## Suggested implementation

### 1. New view function — `integrations/views.py`

Place next to `device_group_destinations_list`.

```python
def device_group_devices_list(request, device_group_id):
    device_group = get_object_or_404(DeviceGroup, pk=device_group_id)
    permission_can_view(request, device_group)
    context = {
        "devices": device_group.devices.all(),
        "device_group_id": device_group_id,
    }
    return render(request, "integrations/device_group_devices_partial.html", context)
```

### 2. New URL — `integrations/urls.py`

Place next to the device group destinations routes.

```python
path(
    "devicegroups/<uuid:device_group_id>/devices",
    views.device_group_devices_list,
    name="device_group_devices_list",
),
```

### 3. New partial — `integrations/templates/integrations/device_group_devices_partial.html`

Read-only table. Each `external_id` is a link that swaps the device config into the
same slide panel.

```django
<div id="device-group-devices-section" class="mt-4">
    <h5>Devices in group</h5>
    {% if devices %}
    <table class="table table-sm table-bordered">
        <thead class="thead-light">
            <tr>
                <th>External ID</th>
                <th>Created</th>
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
                <td class="text-muted">{{ dev.created_at }}</td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
    {% else %}
    <p class="text-muted">No devices in this group.</p>
    {% endif %}
</div>
```

### 4. Wire it into the edit panel — `device_group_update_partial.html`

Add the lazy-load div **before** the existing destinations div:

```django
<div class="slide-panel-content">
    {% include "integrations/_form_errors.html" %}
    {% crispy form %}

    {# NEW — devices section, loads before destinations #}
    <div id="device-group-devices-section"
         hx-get="{% url 'device_group_devices_list' device_group_id=form.instance.id %}"
         hx-trigger="load"
         hx-swap="outerHTML">
        <p class="text-muted">Loading devices...</p>
    </div>

    <div id="device-group-destinations-section"
         hx-get="{% url 'device_group_destinations_list' device_group_id=form.instance.id %}"
         hx-trigger="load"
         hx-swap="outerHTML">
        <p class="text-muted">Loading destinations...</p>
    </div>
</div>
```

## Notes / open questions for the implementer

- **Device label**: plan uses `external_id`. Confirm this is the right field to show
  (it's the manufacturer/source id). `default:dev` falls back to the model's
  `__str__` if `external_id` is empty.
- **Created column**: `Device.created_at` field name should be confirmed against the
  model (uses `TimestampedModel`); drop the column if not wanted.
- **Permissions**: reuses `permission_can_view` like the destinations list — same
  visibility rules. Confirm that's the intended access level for the device list.
- **Pagination**: not included. Groups can be large (e.g. addonp has 31 devices,
  some have more). Consider a scroll container or pagination if a group has many
  devices.
- **Not testable by author**: the portal can't be run locally here, so this must be
  verified in a feature env / locally by whoever implements it.

## Mock

See [`device-group-devices-section-mock.html`](./device-group-devices-section-mock.html)
(open in a browser) for a visual of the resulting edit panel. The boxed/highlighted
section is the new part; everything else already exists.
