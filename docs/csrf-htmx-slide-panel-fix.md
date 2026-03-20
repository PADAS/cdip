# CSRF Token Mismatch in HTMX Slide Panels

## Problem

When a slide panel was opened (e.g. Edit Inbound Integration), saving the form returned a
**403 Forbidden** from Django's CSRF middleware even though the page had rendered a valid
token.

### Root cause

The partial template rendered `{{ csrf_token }}` server-side and baked it into the
`hx-headers` attribute of the wrapper `<div>`:

```html
<div hx-headers='{"X-CSRFToken": "{{ csrf_token }}"}' hx-params="not csrfmiddlewaretoken">
```

At the same time, the slide panel fired several concurrent `hx-trigger="load"` sub-requests
(API key panel, connections panel, etc.). Each sub-request caused Django's CSRF middleware
to issue a `Set-Cookie: csrftoken=…` response header containing a **new raw secret**. The
last sub-request to complete overwrote the browser cookie.

The `hx-headers` token had been derived from the **old** secret. When the form POSTed, the
`X-CSRFToken` header no longer corresponded to the current cookie value, so Django rejected
it.

This could be confirmed in the browser console:

```javascript
function unmaskCsrfToken(t) {
    var chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
    var mask = t.slice(0, 32), masked = t.slice(32);
    return masked.split('').map(function(c, i) {
        return chars[(chars.indexOf(c) - chars.indexOf(mask[i]) + chars.length) % chars.length];
    }).join('');
}

// After a failed save, grab X-CSRFToken from the POST in the Network tab:
unmaskCsrfToken('PASTE_HEADER_VALUE') === document.cookie.match(/csrftoken=([^;]+)/)[1];
// → false  (mismatch confirmed)
```

## Fix

Two changes were required.

### 1. Generate a fresh token on every HTMX request (`base.html`)

The `htmx:configRequest` listener was replaced with one that reads the **current**
`csrftoken` cookie at request time and generates a freshly masked token using Django's own
masking algorithm: choose a random 32-character mask, then for each position `i` emit
`chars[(chars.index(secret[i]) + chars.index(mask[i])) % len(chars)]`. The 64-character
result (`mask + cipher`) is what Django's `_unmask_cipher_token` reverses server-side.

```javascript
document.addEventListener('htmx:configRequest', function(evt) {
    var secret = (document.cookie.match(/csrftoken=([^;]+)/) || [])[1];
    if (secret) {
        var chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
        var mask = Array.from({length: 32}, function() {
            return chars[Math.floor(Math.random() * chars.length)];
        }).join('');
        var cipher = secret.split('').map(function(c, i) {
            return chars[(chars.indexOf(c) + chars.indexOf(mask[i])) % chars.length];
        }).join('');
        evt.detail.headers['X-CSRFToken'] = mask + cipher;
    }
});
```

The `<meta name="csrf-token">` tag was also removed since nothing reads it anymore.

### 2. Remove stale `hx-headers` from the four update partial templates

The baked-in `hx-headers` attribute was removed from the outer `<div>` in each of:

- `inbound_integration_configuration_update_partial.html`
- `outbound_integration_configuration_update_partial.html`
- `bridge_integration_update_partial.html`
- `device_group_update_partial.html`

`hx-params="not csrfmiddlewaretoken"` was **kept** so that crispy-forms' POST body field
(also stale) is excluded, leaving the fresh `X-CSRFToken` header as the sole token Django
validates against.

Before:

```html
<div hx-headers='{"X-CSRFToken": "{{ csrf_token }}"}' hx-params="not csrfmiddlewaretoken">
```

After:

```html
<div hx-params="not csrfmiddlewaretoken">
```

## Verification

1. Open a page with slide panels and open DevTools → Network tab.
2. Click a row to open a slide panel and wait for all sub-requests to settle.
3. Click **Save**.
4. Confirm the POST returns **200**, not 403.
5. Grab the `X-CSRFToken` value from the POST request in the Network tab and run:

```javascript
unmaskCsrfToken('PASTE_HEADER_VALUE') === document.cookie.match(/csrftoken=([^;]+)/)[1];
// → true
```
