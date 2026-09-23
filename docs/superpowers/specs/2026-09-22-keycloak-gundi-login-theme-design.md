# Keycloak Gundi Login Theme — Design

**Date:** 2026-09-22
**Author:** Chris Doehring (with Claude)
**Status:** Design — pending review

## Background

Gundi authenticates portal users through Keycloak. Production runs Keycloak
11.0.2 (WildFly) in the `cdip-auth` namespace of the `cdip-prod01` cluster, applied
from a raw Deployment manifest rather than through ArgoCD. It hosts two realms that
the portal uses: `cdip-dev` (dev and stage portals) and `cdip-prod` (prod portal).
Both realms use the stock Keycloak login theme, so users redirected from the Gundi
portal land on a page that carries Keycloak branding, not Gundi's.

A separate design (`docs/superpowers/specs/2026-07-14-keycloak-upgrade-design.md`,
currently on the `keycloak-26-upgrade-doc` branch) plans an upgrade to Keycloak
26.x. That design lists theme work as a non-goal and records the current theme as
stock. This design changes that: the theme ships for 11 now and the 26 variant
becomes an input to the upgrade.

The local portal stack (`docker-compose.yml`) runs Keycloak 23.0. It is not a
target of this work.

### Brand reference

The React Gundi portal (`padas/gundi-portal`) is the visual reference, not the
legacy Django templates in this repo. Its `tailwind.config.js` and `index.css`
define the palette and font used below. The logo is the green-and-navy sail mark
(`gundi-portal/src/images/gundi-logo.png`, identical to
`cdip_admin/website/static/logo.png`) with the "GUNDI" wordmark.

## Goals

- A `gundi` login theme that restyles the stock Keycloak layout to match the
  React portal: logo, colors, font, controls.
- The same theme source builds for Keycloak 11.0.2 and Keycloak 26.x.
- Zero FreeMarker template overrides, so every login-flow page inherits the
  styling and Keycloak upgrades within a major version do not break it.
- Shipped to production Keycloak 11 with a realm-by-realm rollout and an
  immediate, restart-free rollback.
- A 26 image containing the theme, handed to the upgrade rehearsal.

## Non-goals

- Custom page layouts (split screen, custom header, footer links). Each would
  require a FreeMarker override maintained twice.
- Keycloakify or any React/Node build. Not supported on 11; overkill for a
  username-and-password realm.
- Account console theme, email theme, admin console theme.
- Theming the Keycloak 23 instance in the portal's local compose stack.
- Changing realm content (display name, `displayNameHtml`).
- Moving the prod Keycloak 11 manifest into GitOps or into this repo. The
  upgrade design owns manifest and secret changes.

## Design

### Theme layout

One theme folder in this repo, next to the existing realm export:

```
keycloak/
  cdip-dev-realm.json                  existing
  themes/gundi/login/
    theme.kc11.properties              parent=keycloak     (PatternFly 3)
    theme.kc26.properties              parent=keycloak.v2  (PatternFly 5)
    messages/messages_en.properties    loginAccountTitle override
    resources/
      css/tokens.css                   colors, font, radii as CSS custom properties
      css/gundi.css                    shared rules against stable #kc-* IDs
      css/kc11.css                     PatternFly 3 class overrides
      css/kc26.css                     PatternFly 5 class overrides
      fonts/inter-*.woff2              Inter 400 and 600, bundled
      img/gundi-logo.svg               sail mark + wordmark, or a small PNG
  Dockerfile.kc11
  Dockerfile.kc26
  compose.theme-dev.yml                local KC 11 + KC 26 with theme bind-mounted
  dev/realm-with-theme.json            dev realm export + loginTheme + test user
  tests/smoke.sh                       asserts theme assets load
  tests/check-css.sh                   cascade guard: no framework classes in gundi.css
  tests/wait-ready.sh                  polls a realm URL until Keycloak answers
  tests/screenshot.sh                  headless Chrome screenshot of login and error pages
  RUNBOOK.md                           prod rollout and rollback commands
```

Keycloak requires the properties file to be named `theme.properties`. The two
version files carry a suffix in source and the Dockerfile renames the matching one
during the image build. Local compose does the same via a bind mount of the whole
folder plus a second mount of the right properties file over `theme.properties`.

Each properties file lists only the stylesheets it needs, in cascade order:
`tokens.css`, `gundi.css`, then its version file. The 26 file also sets
`darkMode=false` so Keycloak 26 does not switch palettes with the OS scheme; the
portal is light only.

### Why IDs, not framework classes

Verified against the Keycloak source at tags `11.0.2` and `26.7.4`: the login
markup keeps these IDs across both versions.

| Element | ID |
|---|---|
| Header block and realm name wrapper | `kc-header`, `kc-header-wrapper` |
| Page title | `kc-page-title` |
| Form container and login form | `kc-form`, `kc-form-wrapper`, `kc-form-login` |
| Info block under the form | `kc-info`, `kc-info-wrapper` |
| Username and password inputs | `username`, `password` |
| Reset-flow link | `reset-login` |

IDs that exist only on 11 (`kc-form-options`, `kc-form-buttons`, `kc-login`,
`kc-content`) or only on 26 (`keycloak-bg`, `kc-registration-container`) go in the
version file. Framework classes (`btn btn-primary` on 11, `pf-v5-c-button pf-m-primary`
on 26) also go in the version file. `gundi.css` must contain no PatternFly class
selectors.

### Visual design

**Tokens** (`tokens.css`), from the React portal palette:

| Token | Value | Source name |
|---|---|---|
| `--gundi-primary` | `#006842` | route-green |
| `--gundi-primary-hover` | `#00520c` | dark-green |
| `--gundi-text` | `#222222` | off-black |
| `--gundi-text-secondary` | `#63666A` | secondary-text |
| `--gundi-field-outline` | `#b1b3b3` | field-outline |
| `--gundi-divider` | `#dddddd` | divider-lines |
| `--gundi-error` | `#D0031B` | remove-red |
| `--gundi-error-bg` | `#FDF2F4` | remove-red-bg |
| `--gundi-page-bg` | `#f7f9f7` | white-green |
| `--gundi-card-bg` | `#ffffff` | white |
| `--gundi-font` | `Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif` | index.css |
| `--gundi-radius-card` | `8px` | |
| `--gundi-radius-control` | `4px` | |

Inter is bundled as woff2 at weights 400 and 600 and declared with `@font-face`
in `tokens.css`. The login page must not depend on a third-party CDN.

**Layout.** Stock structure, restyled:

- Page background flat `--gundi-page-bg`. On 11 this replaces the `keycloak-bg.png`
  photo set on `.login-pf body`; on 26 it hides the `#keycloak-bg` panel.
- `#kc-header-wrapper` shows the Gundi logo as a CSS background image with its
  text hidden (`font-size: 0` or `color: transparent`, plus fixed height). This
  keeps the realm's `displayNameHtml` untouched and works identically on both
  versions. Logo renders at roughly 48px tall, centered.
- The card (`.card-pf` on 11, `.pf-v5-c-login__main` on 26) is white, hairline
  `--gundi-divider` border, `--gundi-radius-card`, soft shadow, max width 400px,
  centered. On viewports under 480px it is full width with a 16px gutter.
- `#kc-page-title` in `--gundi-text`, 600 weight.

**Controls.**

- Inputs: 1px `--gundi-field-outline`, `--gundi-radius-control`, 40px tall. On
  focus the border becomes `--gundi-primary` with a 3px translucent green ring.
- Primary button: full width, `--gundi-primary` background, white text, 600
  weight, `--gundi-radius-control`, hover `--gundi-primary-hover`, visible focus
  ring. Secondary and link-style buttons use `--gundi-primary` text.
- Links (`forgot password`, `back to login`) in `--gundi-primary`, underline on
  hover.
- Checkbox (`rememberMe`) and the 26 password-visibility toggle: `accent-color`
  and icon color `--gundi-primary`.
- Alerts: inline band, 4px left border in the status color, error uses
  `--gundi-error` on `--gundi-error-bg`. Success and info reuse the primary green
  and a neutral gray respectively.

**Copy.** `messages/messages_en.properties` overrides one key:
`loginAccountTitle=Sign in to Gundi`. Keycloak 26 titles the login page with that
key. Keycloak 11 has no such key; its login page reuses `doLogIn`, the button
label, for the title, so overriding it would also rename the button. On 11 the
title therefore stays the stock "Log In". All other strings stay stock on both.

**Accessibility.** Body text and primary green on white both exceed WCAG AA
contrast. Every interactive control keeps a visible focus indicator. No
`outline: none` without a replacement ring.

### Pages covered

All pages the login theme renders inherit the shared stylesheet. The following
are the pages users of these realms can reach and are the verification set:

| Page | 11 | 26 | How to reach locally |
|---|---|---|---|
| Login | yes | yes | account console redirect |
| Forgot password (`login-reset-password`) | yes | yes | link on login page |
| Info (after reset request) | yes | yes | submit forgot-password |
| Update password (`login-update-password`) | yes | yes | test user required action |
| Configure OTP / OTP login | yes | yes | test user required action |
| Error | yes | yes | auth URL with bad `redirect_uri` |
| Logout confirmation | no | yes | logout URL without `id_token_hint` |

Registration and social login are disabled in the `cdip-dev` realm export and are
not verified. Confirm the same for `cdip-prod` in the admin console before the
prod flip; if either is enabled there, add the register and social-provider pages
to the manual walk.

### Images

`Dockerfile.kc11`:

```
FROM quay.io/keycloak/keycloak:11.0.2
COPY keycloak/themes/gundi /opt/jboss/keycloak/themes/gundi
RUN mv /opt/jboss/keycloak/themes/gundi/login/theme.kc11.properties \
       /opt/jboss/keycloak/themes/gundi/login/theme.properties \
 && rm /opt/jboss/keycloak/themes/gundi/login/theme.kc26.properties
```

`Dockerfile.kc26` is the same shape against `quay.io/keycloak/keycloak:26.x`,
copying to `/opt/keycloak/themes/gundi`. It does not run `kc.sh build`; the
upgrade design owns the optimized-build decision and can layer on top of this
image or copy the theme folder into its own.

The 11 base image is `quay.io/keycloak/keycloak:11.0.2`, confirmed from the
running prod Deployment on 2026-09-22. The stale manifest copy in
`padas/keycloak.yaml` says `jboss/keycloak:11.0.2` and should not be used as a
reference. Both images share the same `/opt/jboss/keycloak` layout.

### CI

New workflow `.github/workflows/keycloak-theme.yml`, triggered on push and pull
request when paths under `keycloak/**` or the workflow itself change. It:

1. Builds both images with the shared `PADAS/gundi-workflows` `build_docker.yml`
   workflow the portal already uses.
2. Starts each image with the dev realm import (`keycloak/dev/realm-with-theme.json`)
   and runs `keycloak/tests/smoke.sh` against it.
3. On success on `main`, pushes to
   `europe-west3-docker.pkg.dev/serca-artifact-registry/gundi/keycloak` with tags
   `11.0.2-gundi-<short sha>` and `26.<minor>-gundi-<short sha>`.

Nothing deploys automatically. Prod Keycloak 11 is not ArgoCD-managed and the 26
image is consumed by the upgrade work.

### Smoke test

`keycloak/tests/smoke.sh <base-url> <realm>`:

1. `GET {base}/auth/realms/{realm}/protocol/openid-connect/auth?client_id=account-console&response_type=code&redirect_uri=...&scope=openid`
   with a valid redirect URI for the built-in `account-console` client, and assert
   HTTP 200.
2. Assert the body contains `/resources/` URLs for `login/gundi/css/tokens.css`,
   `login/gundi/css/gundi.css`, and the version stylesheet.
3. Fetch every `<link rel="stylesheet">`, `url(...)` font, and the logo image
   referenced from the theme and assert HTTP 200 for each.
4. On 26, assert the body contains `Sign in to Gundi`. On 11, assert the page
   title element `id="kc-page-title"` is present.

A wrong `parent=`, a mistyped `styles=` path, or a missing font all fail this test.
A silently unstyled page is the most common theme failure and the one this guards.

### Local iteration

`keycloak/compose.theme-dev.yml` runs two services:

- `kc11`: the 11 base image on port 8081, theme folder bind-mounted to
  `/opt/jboss/keycloak/themes/gundi`, `theme.kc11.properties` bind-mounted over
  `login/theme.properties`, realm import via `KEYCLOAK_IMPORT`, and
  `JAVA_OPTS_APPEND=-Dkeycloak.theme.staticMaxAge=-1 -Dkeycloak.theme.cacheThemes=false -Dkeycloak.theme.cacheTemplates=false`.
- `kc26`: the 26 base image on port 8082, `start-dev --import-realm` (dev mode
  already disables theme caching), the same two bind mounts to `/opt/keycloak/themes/gundi`,
  and `KC_HTTP_RELATIVE_PATH=/auth` so URLs match prod.

Both use the embedded H2 database; no Postgres needed. `keycloak/dev/realm-with-theme.json`
is a copy of `cdip-dev-realm.json` with `"loginTheme": "gundi"`, `"sslRequired": "none"`
so a containerized browser can reach it over plain HTTP, and a test user
`theme-tester` carrying the `UPDATE_PASSWORD` and `CONFIGURE_TOTP` required
actions. Editing any CSS file and reloading the browser shows the change on both.

`keycloak/tests/screenshot.sh` renders the login page and the error page of a
running instance to PNG with a headless Chrome container, so an implementer
without a browser can check the result. Pages behind a form submission (update
password, OTP, info) are walked by hand per the verification table.

### Prod rollout (Keycloak 11)

Recorded in `keycloak/RUNBOOK.md`. Order matters:

1. **Image swap.** `kubectl --context cdip-prod -n cdip-auth set image deploy/keycloak keycloak=<registry>/gundi/keycloak:11.0.2-gundi-<sha>`.
   Single replica, so this is a restart of the same length as the existing
   nightly restart. Schedule it in the 02:00 UTC window or an agreed off-hours
   slot. Confirm the pod is Ready and `curl` the stock login page still renders.
2. **Stage via `cdip-dev`.** Admin console → realm `cdip-dev` → Realm Settings →
   Themes → Login Theme = `gundi` → Save. Log out of the dev portal and log back
   in. Walk the verification table above by hand.
3. **Flip `cdip-prod`.** Same setting on the `cdip-prod` realm. Log in through the
   prod portal.

Steps 2 and 3 cause no restart. Theme selection is a per-realm lookup.

### Rollback

- **Visual problem:** set the realm's Login Theme back to `keycloak` (the stock
  value). Immediate, no restart.
- **Image problem:** `kubectl --context cdip-prod -n cdip-auth rollout undo deploy/keycloak`.
  Restores the stock image. Any realm still pointing at `gundi` would then fail to
  render the login page, so revert the realm setting first if both are needed.

### Hand-off to the Keycloak 26 upgrade

The login theme setting is stored in the realm table. When the upgrade copies the
auth database, both realms will already point at `gundi`. The 26 image used at
cutover **must** include the theme or the login page returns an error. Concretely,
the upgrade work must:

- Base its image on `Dockerfile.kc26` or copy `keycloak/themes/gundi` into its own
  image with the 26 properties file renamed.
- Add the verification table above to its rehearsal checklist.
- Update the upgrade design doc: remove "theme work (confirmed stock)" from
  non-goals and add the gundi 26 image as an input. That doc is on the
  `keycloak-26-upgrade-doc` branch and is edited there, not in this change.

## Testing summary

| Layer | What | Where it runs |
|---|---|---|
| Smoke | Theme assets referenced and served, title override present | CI on both images; locally against compose |
| Manual visual | Verification table, both versions, desktop and 375px wide viewport | Locally before merge; on `cdip-dev` realm before flipping `cdip-prod` |
| Cascade guard | `gundi.css` contains no `pf-`, `btn`, `card-pf`, or `login-pf` selectors | Grep step in CI |

## Risks

- **Base image drift.** If prod's image ever changes, a theme image built from the
  old base would change the WildFly configuration prod relies on. Mitigation: the
  runbook re-reads the image from the live Deployment before each build.
- **Realm points at a missing theme.** Happens only if the realm is flipped before
  the image swap, or the 26 upgrade ships without the theme. Mitigation: runbook
  ordering and the hand-off requirement above.
- **PatternFly 5 specificity.** Keycloak 26 styles use CSS custom properties and
  fairly specific selectors. Some overrides may need to target the PatternFly
  variables (`--pf-v5-c-button--m-primary--BackgroundColor`) rather than classes.
  That stays in `kc26.css` and does not affect the shared file.
- **Font licensing and size.** Inter is OFL licensed; two woff2 weights are about
  200 KB total, cached after first load. Acceptable for a login page.

## Follow-ups (not in this change)

- Update the upgrade design doc as described in the hand-off section, once it is
  on `main` or on its own branch.
- Move the portal's local compose from Keycloak 23 to 26 and mount the theme, so
  the regular local stack shows the branded login.
- Commit the prod Keycloak 11 Deployment manifest to this repo with secrets moved
  to a Kubernetes Secret. The upgrade design already plans the secret move.
