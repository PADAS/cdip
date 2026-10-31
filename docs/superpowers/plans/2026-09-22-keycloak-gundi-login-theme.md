# Keycloak Gundi Login Theme Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a `gundi` Keycloak login theme that restyles the stock layout to match the React Gundi portal, builds for Keycloak 11.0.2 and 26.7 from one source folder, and is delivered as custom images with a tested rollout path.

**Architecture:** One theme folder `keycloak/themes/gundi/login/` holds shared assets and a shared stylesheet written only against stable `#kc-*` IDs, plus one small version stylesheet and one properties file per Keycloak major. Two Dockerfiles copy the folder into the official images and pick the matching properties file. A compose file runs both versions locally with the theme bind-mounted; shell scripts smoke-test asset loading and screenshot pages with headless Chrome; a GitHub Actions workflow builds, tests, and pushes both images.

**Tech Stack:** Keycloak FreeMarker theme system (properties + CSS only, no `.ftl` overrides), CSS custom properties, PatternFly 3 (KC 11) and PatternFly 5 (KC 26) class overrides, Docker, Docker Compose, bash, GitHub Actions, the shared `PADAS/gundi-workflows` build workflow.

**Spec:** `docs/superpowers/specs/2026-09-22-keycloak-gundi-login-theme-design.md`

## Global Constraints

- Keycloak 11 base image is exactly `quay.io/keycloak/keycloak:11.0.2`. Keycloak 26 base image is `quay.io/keycloak/keycloak:26.7`.
- Theme folder name is `gundi`. Realm setting `loginTheme` will be set to `gundi`.
- No FreeMarker (`.ftl`) files anywhere under `keycloak/themes/`.
- `resources/css/gundi.css` contains no PatternFly, Bootstrap, or Keycloak framework class selectors. Only `#kc-*` IDs, element selectors, attribute selectors, and pseudo-elements. `keycloak/tests/check-css.sh` enforces this.
- Both properties files list the parent theme's own stylesheet first in `styles=`, because a child `styles=` replaces the parent's list rather than merging.
- The Keycloak 26 properties file sets `darkMode=false`.
- Fonts are bundled (Inter 4.1, weights 400 and 600, woff2). No external font or CDN request from the login page.
- Design tokens are the exact values in the spec's token table (`#006842`, `#00520c`, `#222222`, `#63666A`, `#b1b3b3`, `#dddddd`, `#D0031B`, `#FDF2F4`, `#f7f9f7`, `#ffffff`, radii 8px and 4px).
- Message overrides: `loginAccountTitle=Sign in to Gundi` (title on 26; 11 has no such key and keeps "Log In") and `loginTitle=Sign in to Gundi` (the `<title>` tag on both).
- All shell scripts must run under macOS bash 3.2 and Ubuntu bash 5: no `mapfile`, no `declare -A`.
- Images are pushed to `europe-west3-docker.pkg.dev/serca-artifact-registry/gundi/keycloak` with tags `11.0.2-gundi-<short sha>` and `26.7-gundi-<short sha>`, only from `main`, only after the smoke test passes.
- Nothing deploys automatically. Prod rollout is manual per `keycloak/RUNBOOK.md`.
- Run every command from the repository root unless a step says otherwise.

## Review Focus

1. **Realm `displayNameHtml` containing markup.** The prod realm may carry the Keycloak default `<div class="kc-logo-text"><span>Keycloak</span></div>`. Hiding the header text with `font-size: 0` does not hide a child `div` that draws its own background image, so a Keycloak logo could appear beside the Gundi mark. Expected: only the Gundi mark and wordmark render. Test in Task 4 (rule `#kc-header-wrapper > * { display: none; }`) using the realm fixture from Task 1, which sets that exact `displayNameHtml`.
2. **375px wide viewport.** Expected: card fills the width with a 16px gutter, no horizontal scroll, button and inputs full width. Test: the mobile screenshots in Tasks 5 and 6.
3. **Browser tab title on a realm whose display name is not "Gundi".** The `<title>` uses `loginTitle` with the realm display name, so the tab would read "Sign in to CDIP Dev" or the prod realm's name. Expected: tab reads "Sign in to Gundi". Test: smoke test asserts `<title>Sign in to Gundi</title>` on both versions (Task 1 script, passing from Task 2).
4. **Error page reached with an unknown `client_id`.** No client context exists, and Keycloak renders `error.ftl` with a different message. Expected: still themed. Test: the second error screenshot in Tasks 5 and 6 uses `client_id=does-not-exist`.
5. **Font files failing to load.** If a woff2 is missing or mis-pathed, the page silently falls back to the system font and nobody notices. Expected: the smoke test fails. Test: Task 1 smoke script fetches every `url(...)` referenced from the theme stylesheets; Task 3 makes it pass.

---

### Task 1: Local harness — realm fixture, compose file, smoke, wait, screenshot scripts

**Files:**
- Create: `keycloak/dev/realm-with-theme.json`
- Create: `keycloak/compose.theme-dev.yml`
- Create: `keycloak/tests/wait-ready.sh`
- Create: `keycloak/tests/smoke.sh`
- Create: `keycloak/tests/screenshot.sh`
- Modify: `.gitignore` (append `keycloak/tests/shots/`)

**Interfaces:**
- Consumes: `keycloak/cdip-dev-realm.json` (existing realm export; realm name `cdip-dev`, confidential client `cdip-kong-gateway` with redirect `http://localhost:8000/*`).
- Produces: `keycloak/tests/wait-ready.sh <url> [timeout-seconds]`; `keycloak/tests/smoke.sh <base-url> <realm> <kc11|kc26>` (exit 0 = pass); `keycloak/tests/screenshot.sh <kc11|kc26> <host-port>` writing `keycloak/tests/shots/<version>-{login,login-mobile,error,error-noclient}.png`; compose services `kc11` on `http://localhost:8081/auth` and `kc26` on `http://localhost:8082/auth`, admin login `admin`/`admin`.

- [ ] **Step 1: Generate the realm fixture**

```bash
mkdir -p keycloak/dev keycloak/tests
python3 - <<'EOF'
import json
src = json.load(open("keycloak/cdip-dev-realm.json"))
src["loginTheme"] = "gundi"
src["sslRequired"] = "none"          # containerised Chrome reaches KC over plain http via host.docker.internal
# Simulates the Keycloak default markup a prod realm may carry; the theme must hide it (Review Focus 1).
src["displayNameHtml"] = '<div class="kc-logo-text"><span>Keycloak</span></div>'
src.setdefault("users", []).append({
    "username": "theme-tester",
    "enabled": True,
    "email": "theme-tester@example.com",
    "firstName": "Theme",
    "lastName": "Tester",
    "credentials": [{"type": "password", "value": "theme-tester", "temporary": False}],
    "requiredActions": ["UPDATE_PASSWORD", "CONFIGURE_TOTP"],
})
json.dump(src, open("keycloak/dev/realm-with-theme.json", "w"), indent=2)
print("wrote keycloak/dev/realm-with-theme.json")
EOF
```

- [ ] **Step 2: Write `keycloak/tests/wait-ready.sh`**

```bash
#!/usr/bin/env bash
# Usage: keycloak/tests/wait-ready.sh <url> [timeout-seconds]
# Polls until <url> returns HTTP 200. Keycloak 11 under amd64 emulation can take 3 minutes.
set -euo pipefail
url=${1:?usage: wait-ready.sh <url> [timeout-seconds]}
timeout=${2:-300}
start=$(date +%s)
until curl -sf -o /dev/null "$url"; do
  if (( $(date +%s) - start > timeout )); then
    echo "timed out after ${timeout}s waiting for $url" >&2
    exit 1
  fi
  sleep 3
done
echo "ready: $url"
```

- [ ] **Step 3: Write `keycloak/tests/smoke.sh`**

```bash
#!/usr/bin/env bash
# Usage: keycloak/tests/smoke.sh <base-url> <realm> <kc11|kc26>
# Asserts the login page uses the gundi theme and every theme asset it references is served.
# Catches the silent failures: wrong parent=, mistyped styles= path, missing font or logo.
set -euo pipefail
base=${1:?usage: smoke.sh <base-url> <realm> <kc11|kc26>}
realm=${2:?realm}
version=${3:?kc11|kc26}

fail() { echo "FAIL: $*" >&2; exit 1; }

login_url="$base/auth/realms/$realm/protocol/openid-connect/auth?client_id=cdip-kong-gateway&response_type=code&scope=openid&redirect_uri=http%3A%2F%2Flocalhost%3A8000%2F"
html=$(curl -sf "$login_url") || fail "login page did not return 200: $login_url"

# 1. The page must link our three stylesheets (theme.properties styles= is correct).
for css in tokens gundi "$version"; do
  grep -q "login/gundi/css/$css.css" <<<"$html" || fail "login page does not reference css/$css.css"
done

# 2. Every /resources/ asset the page links must be served.
assets=$(grep -oE '(href|src)="[^"]*/resources/[^"]+"' <<<"$html" | sed -E 's/^(href|src)="//; s/"$//' | sort -u)
[[ -n $assets ]] || fail "no /resources/ links found in login page"
while read -r a; do
  [[ -z $a ]] && continue
  url=$a; [[ $a == /* ]] && url="$base$a"
  curl -sf -o /dev/null "$url" || fail "asset not served: $url"
done <<<"$assets"

# 3. Every url(...) inside our stylesheets (fonts, logo) must be served.
while read -r a; do
  [[ -z $a ]] && continue
  [[ $a == *login/gundi/css/*.css ]] || continue
  css_url=$a; [[ $a == /* ]] && css_url="$base$a"
  css_dir=${css_url%/*}
  refs=$(curl -sf "$css_url" | grep -oE 'url\(["'"'"']?[^)"'"'"']+' | sed -E 's/^url\(["'"'"']?//' | sort -u || true)
  while read -r ref; do
    [[ -z $ref || $ref == data:* || $ref == http* ]] && continue
    curl -sf -o /dev/null "$css_dir/$ref" || fail "css reference not served: $css_dir/$ref (from $css_url)"
  done <<<"$refs"
done <<<"$assets"

# 4. Copy overrides.
grep -qE '<title>[[:space:]]*Sign in to Gundi[[:space:]]*</title>' <<<"$html" || fail "<title> override missing"
if [[ $version == kc26 ]]; then
  grep -q 'Sign in to Gundi' <<<"$html" || fail "loginAccountTitle override missing on kc26"
fi
grep -q 'id="kc-page-title"' <<<"$html" || fail "kc-page-title element missing"

echo "PASS: $version gundi theme serves all assets from $base"
```

- [ ] **Step 4: Write `keycloak/tests/screenshot.sh`**

```bash
#!/usr/bin/env bash
# Usage: keycloak/tests/screenshot.sh <kc11|kc26> <host-port>
# Renders login and error pages of a running local Keycloak to PNG with headless Chrome in Docker.
# Output: keycloak/tests/shots/<version>-{login,login-mobile,error,error-noclient}.png
set -euo pipefail
version=${1:?usage: screenshot.sh <kc11|kc26> <host-port>}
port=${2:?host port, e.g. 8081}
here=$(cd "$(dirname "$0")" && pwd)
out="$here/shots"
mkdir -p "$out"

auth="http://host.docker.internal:$port/auth/realms/cdip-dev/protocol/openid-connect/auth"
ok_redirect="redirect_uri=http%3A%2F%2Flocalhost%3A8000%2F"
bad_redirect="redirect_uri=http%3A%2F%2Fevil.example%2F"

shot() { # <name> <WxH> <url>
  docker run --rm --add-host=host.docker.internal:host-gateway -v "$out:/out" zenika/alpine-chrome:latest \
    --no-sandbox --headless --disable-gpu --hide-scrollbars --virtual-time-budget=3000 \
    --window-size="$2" --screenshot="/out/$version-$1.png" "$3" >/dev/null 2>&1
  echo "wrote $out/$version-$1.png"
}

shot login          1280,900 "$auth?client_id=cdip-kong-gateway&response_type=code&scope=openid&$ok_redirect"
shot login-mobile   375,812  "$auth?client_id=cdip-kong-gateway&response_type=code&scope=openid&$ok_redirect"
shot error          1280,900 "$auth?client_id=cdip-kong-gateway&response_type=code&scope=openid&$bad_redirect"
shot error-noclient 1280,900 "$auth?client_id=does-not-exist&response_type=code&scope=openid&$ok_redirect"
```

- [ ] **Step 5: Write `keycloak/compose.theme-dev.yml`**

```yaml
# Keycloak 11 and 26 side by side with the gundi login theme bind-mounted for live editing.
# From the repo root:   docker compose -f keycloak/compose.theme-dev.yml up
#   KC 11 -> http://localhost:8081/auth      KC 26 -> http://localhost:8082/auth
#   admin console: admin / admin             realm: cdip-dev (users: dev, theme-tester / theme-tester)
# Edit any file under themes/gundi and reload the browser; both versions run with theme caching off.
services:
  kc11:
    image: quay.io/keycloak/keycloak:11.0.2
    platform: linux/amd64          # no arm64 build exists; runs emulated on Apple Silicon
    ports:
      - "8081:8080"
    environment:
      KEYCLOAK_USER: admin
      KEYCLOAK_PASSWORD: admin
      DB_VENDOR: h2
      KEYCLOAK_IMPORT: /tmp/realm.json
    command:
      - -b
      - 0.0.0.0
      - -Dkeycloak.theme.staticMaxAge=-1
      - -Dkeycloak.theme.cacheThemes=false
      - -Dkeycloak.theme.cacheTemplates=false
    volumes:
      - ./dev/realm-with-theme.json:/tmp/realm.json:ro
      - ./themes/gundi:/opt/jboss/keycloak/themes/gundi:ro
      - ./themes/gundi/login/theme.kc11.properties:/opt/jboss/keycloak/themes/gundi/login/theme.properties:ro

  kc26:
    image: quay.io/keycloak/keycloak:26.7
    ports:
      - "8082:8080"
    environment:
      KC_BOOTSTRAP_ADMIN_USERNAME: admin
      KC_BOOTSTRAP_ADMIN_PASSWORD: admin
      KC_HTTP_RELATIVE_PATH: /auth   # match prod URL shape
    command: ["start-dev", "--import-realm"]   # start-dev disables theme caching
    volumes:
      - ./dev/realm-with-theme.json:/opt/keycloak/data/import/realm.json:ro
      - ./themes/gundi:/opt/keycloak/themes/gundi:ro
      - ./themes/gundi/login/theme.kc26.properties:/opt/keycloak/themes/gundi/login/theme.properties:ro
```

- [ ] **Step 6: Make scripts executable and ignore screenshots**

```bash
chmod +x keycloak/tests/wait-ready.sh keycloak/tests/smoke.sh keycloak/tests/screenshot.sh
printf '\n# Keycloak theme screenshots (generated by keycloak/tests/screenshot.sh)\nkeycloak/tests/shots/\n' >> .gitignore
```

- [ ] **Step 7: Create stub properties files so compose can bind them**

Compose fails if a bind-mount source file does not exist. Write the two properties files with only a `parent=` line so Keycloak can render the parent theme's pages; Task 2 fills them in. (An empty file would leave the theme without a parent and Keycloak would return a 500 instead of an unstyled page.)

```bash
mkdir -p keycloak/themes/gundi/login
printf 'parent=keycloak\n' > keycloak/themes/gundi/login/theme.kc11.properties
printf 'parent=keycloak.v2\n' > keycloak/themes/gundi/login/theme.kc26.properties
```

- [ ] **Step 8: Start both instances and wait**

```bash
docker compose -f keycloak/compose.theme-dev.yml up -d
keycloak/tests/wait-ready.sh http://localhost:8082/auth/realms/cdip-dev 300
keycloak/tests/wait-ready.sh http://localhost:8081/auth/realms/cdip-dev 300
```

Expected: both print `ready: ...`. If kc11 times out, run `docker compose -f keycloak/compose.theme-dev.yml logs kc11` and check for the realm import line `Realm 'cdip-dev' imported`.

- [ ] **Step 9: Run the smoke test and confirm it fails for the right reason**

```bash
keycloak/tests/smoke.sh http://localhost:8081 cdip-dev kc11; echo "exit=$?"
keycloak/tests/smoke.sh http://localhost:8082 cdip-dev kc26; echo "exit=$?"
```

Expected: both print `FAIL: login page does not reference css/tokens.css` and `exit=1`. The stub theme has a parent but no `styles=`, so the page renders with the parent's markup and none of our stylesheets. Any other failure (page not 200) means the harness itself is broken; fix that before continuing.

- [ ] **Step 10: Run the screenshot script once to pull the Chrome image and confirm output**

```bash
keycloak/tests/screenshot.sh kc26 8082
ls -la keycloak/tests/shots/
```

Expected: four PNGs named `kc26-*.png`. View `keycloak/tests/shots/kc26-login.png` with the Read tool: it should show the stock Keycloak 26 login page (proves the pipeline; styling comes later).

- [ ] **Step 11: Commit**

```bash
git add keycloak/dev/realm-with-theme.json keycloak/compose.theme-dev.yml keycloak/tests/wait-ready.sh keycloak/tests/smoke.sh keycloak/tests/screenshot.sh keycloak/themes/gundi/login/theme.kc11.properties keycloak/themes/gundi/login/theme.kc26.properties .gitignore
git commit -m "Add local Keycloak 11/26 theme harness with smoke and screenshot scripts"
```

---

### Task 2: Theme skeleton — properties files, empty stylesheets, message overrides

**Files:**
- Modify: `keycloak/themes/gundi/login/theme.kc11.properties`
- Modify: `keycloak/themes/gundi/login/theme.kc26.properties`
- Create: `keycloak/themes/gundi/login/messages/messages_en.properties`
- Create: `keycloak/themes/gundi/login/resources/css/tokens.css` (comment only for now)
- Create: `keycloak/themes/gundi/login/resources/css/gundi.css` (comment only)
- Create: `keycloak/themes/gundi/login/resources/css/kc11.css` (comment only)
- Create: `keycloak/themes/gundi/login/resources/css/kc26.css` (comment only)

**Interfaces:**
- Consumes: Task 1 harness.
- Produces: the stylesheet load order every later task relies on: parent stylesheet, then `tokens.css`, `gundi.css`, `kc11.css` or `kc26.css`.

- [ ] **Step 1: Write the Keycloak 11 properties file**

`keycloak/themes/gundi/login/theme.kc11.properties`:

```properties
# Gundi login theme for Keycloak 11.0.2 (WildFly; parent "keycloak" is PatternFly 3).
# Installed as theme.properties by Dockerfile.kc11 and by compose.theme-dev.yml.
parent=keycloak
import=common/keycloak

# A child `styles=` REPLACES the parent's list, so the parent's login.css is listed first.
# Resources resolve through the parent chain, so css/login.css comes from the keycloak theme.
styles=css/login.css css/tokens.css css/gundi.css css/kc11.css
```

- [ ] **Step 2: Write the Keycloak 26 properties file**

`keycloak/themes/gundi/login/theme.kc26.properties`:

```properties
# Gundi login theme for Keycloak 26.x (Quarkus; parent "keycloak.v2" is PatternFly 5).
# Installed as theme.properties by Dockerfile.kc26 and by compose.theme-dev.yml.
parent=keycloak.v2
import=common/keycloak

# A child `styles=` REPLACES the parent's list, so the parent's styles.css is listed first.
styles=css/styles.css css/tokens.css css/gundi.css css/kc26.css

# The portal is light-only; do not follow the OS colour scheme.
darkMode=false
```

- [ ] **Step 3: Write the message overrides**

`keycloak/themes/gundi/login/messages/messages_en.properties`:

```properties
# Only the two title strings change. Everything else inherits from the parent theme.
# loginAccountTitle is the login page h1 on Keycloak 26. Keycloak 11 has no such key and
# titles the page with doLogIn (also the button label), so 11 keeps the stock "Log In".
loginAccountTitle=Sign in to Gundi
# <title> tag on both versions. Ignores the realm display name placeholder {0} on purpose.
loginTitle=Sign in to Gundi
```

- [ ] **Step 4: Create the four stylesheets with header comments only**

```bash
mkdir -p keycloak/themes/gundi/login/resources/css keycloak/themes/gundi/login/messages
cat > keycloak/themes/gundi/login/resources/css/tokens.css <<'EOF'
/* Gundi design tokens shared by both Keycloak versions. Filled in Task 3. */
EOF
cat > keycloak/themes/gundi/login/resources/css/gundi.css <<'EOF'
/* Shared Gundi rules. Only stable #kc-* ids, element, attribute and pseudo selectors.
   Framework classes (PatternFly 3 / 5) belong in kc11.css / kc26.css.
   Enforced by keycloak/tests/check-css.sh. Filled in Task 4. */
EOF
cat > keycloak/themes/gundi/login/resources/css/kc11.css <<'EOF'
/* Keycloak 11 (PatternFly 3) class overrides for the Gundi theme. Filled in Task 5. */
EOF
cat > keycloak/themes/gundi/login/resources/css/kc26.css <<'EOF'
/* Keycloak 26 (PatternFly 5) class overrides for the Gundi theme. Filled in Task 6. */
EOF
```

- [ ] **Step 5: Restart the instances so they pick up the new mounts and the messages file**

Theme caching is off, but the `messages/` directory did not exist when the containers started, and Keycloak 11 reads the theme directory listing at startup.

```bash
docker compose -f keycloak/compose.theme-dev.yml restart
keycloak/tests/wait-ready.sh http://localhost:8082/auth/realms/cdip-dev 300
keycloak/tests/wait-ready.sh http://localhost:8081/auth/realms/cdip-dev 300
```

- [ ] **Step 6: Run the smoke test on both**

```bash
keycloak/tests/smoke.sh http://localhost:8081 cdip-dev kc11
keycloak/tests/smoke.sh http://localhost:8082 cdip-dev kc26
```

Expected: both print `PASS: ... gundi theme serves all assets ...`. If `kc11` fails on `<title>`, check that Keycloak 11's base messages define `loginTitle` with a `{0}` placeholder (it does at tag 11.0.2) and that the messages file has no BOM.

- [ ] **Step 7: Screenshot both and confirm the pages still render as stock (nothing broken)**

```bash
keycloak/tests/screenshot.sh kc11 8081
keycloak/tests/screenshot.sh kc26 8082
```

View `keycloak/tests/shots/kc11-login.png` and `kc26-login.png`. Expected: stock Keycloak pages, the 26 one titled "Sign in to Gundi". On 11 the header shows the Keycloak logo from the fixture's `displayNameHtml`; that is Review Focus 1 and is fixed in Task 4.

- [ ] **Step 8: Commit**

```bash
git add keycloak/themes/gundi
git commit -m "Add gundi Keycloak theme skeleton for KC 11 and 26 with title overrides"
```

---

### Task 3: Assets and tokens — Inter fonts, logo mark, tokens.css

**Files:**
- Create: `keycloak/themes/gundi/login/resources/fonts/Inter-Regular.woff2`
- Create: `keycloak/themes/gundi/login/resources/fonts/Inter-SemiBold.woff2`
- Create: `keycloak/themes/gundi/login/resources/fonts/LICENSE.txt`
- Create: `keycloak/themes/gundi/login/resources/img/gundi-mark.png`
- Modify: `keycloak/themes/gundi/login/resources/css/tokens.css`

**Interfaces:**
- Consumes: `cdip_admin/website/static/logo.png` (3089×2572 RGBA sail mark).
- Produces: CSS custom properties every later stylesheet uses: `--gundi-primary`, `--gundi-primary-hover`, `--gundi-text`, `--gundi-text-secondary`, `--gundi-field-outline`, `--gundi-divider`, `--gundi-error`, `--gundi-error-bg`, `--gundi-page-bg`, `--gundi-card-bg`, `--gundi-font`, `--gundi-radius-card`, `--gundi-radius-control`, `--gundi-focus-ring`, `--gundi-shadow-card`; font family `Inter` at 400 and 600; image at `../img/gundi-mark.png` relative to the css folder.

- [ ] **Step 1: Download Inter 4.1 and extract the two weights plus licence**

```bash
curl -sL -o /tmp/inter-4.1.zip https://github.com/rsms/inter/releases/download/v4.1/Inter-4.1.zip
mkdir -p keycloak/themes/gundi/login/resources/fonts
unzip -o -j /tmp/inter-4.1.zip web/Inter-Regular.woff2 web/Inter-SemiBold.woff2 LICENSE.txt -d keycloak/themes/gundi/login/resources/fonts/
ls -la keycloak/themes/gundi/login/resources/fonts/
```

Expected: `Inter-Regular.woff2` (~111 KB), `Inter-SemiBold.woff2` (~115 KB), `LICENSE.txt` (SIL Open Font License).

- [ ] **Step 2: Export the logo mark at 2× display size**

Displayed at 48px tall (about 58px wide); export 128px wide for retina.

```bash
mkdir -p keycloak/themes/gundi/login/resources/img
sips -Z 128 cdip_admin/website/static/logo.png --out keycloak/themes/gundi/login/resources/img/gundi-mark.png
file keycloak/themes/gundi/login/resources/img/gundi-mark.png
```

Expected: `PNG image data, 128 x 107, 8-bit/color RGBA`. View it with the Read tool to confirm the green-and-navy sail mark is intact on a transparent background.

- [ ] **Step 3: Write tokens.css**

`keycloak/themes/gundi/login/resources/css/tokens.css`:

```css
/* Gundi design tokens shared by both Keycloak versions.
   Colour values come from gundi-portal/tailwind.config.js (names in comments). */

@font-face {
  font-family: "Inter";
  font-style: normal;
  font-weight: 400;
  font-display: swap;
  src: url("../fonts/Inter-Regular.woff2") format("woff2");
}
@font-face {
  font-family: "Inter";
  font-style: normal;
  font-weight: 600;
  font-display: swap;
  src: url("../fonts/Inter-SemiBold.woff2") format("woff2");
}

:root {
  --gundi-primary: #006842;            /* route-green */
  --gundi-primary-hover: #00520c;      /* dark-green */
  --gundi-text: #222222;               /* off-black */
  --gundi-text-secondary: #63666A;     /* secondary-text */
  --gundi-field-outline: #b1b3b3;      /* field-outline */
  --gundi-divider: #dddddd;            /* divider-lines */
  --gundi-error: #D0031B;              /* remove-red */
  --gundi-error-bg: #FDF2F4;           /* remove-red-bg */
  --gundi-success-bg: #E8F2E9;         /* light-green */
  --gundi-warning: #9d6900;            /* warning-dark-yellow */
  --gundi-warning-bg: #fdfaf4;         /* warning-yellow */
  --gundi-info-bg: #f2f6fc;            /* light-blue-50 */
  --gundi-page-bg: #f7f9f7;            /* white-green */
  --gundi-card-bg: #ffffff;

  --gundi-font: "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", "Helvetica Neue", sans-serif;

  --gundi-radius-card: 8px;
  --gundi-radius-control: 4px;
  --gundi-focus-ring: rgba(0, 104, 66, 0.3);
  --gundi-shadow-card: 0 4px 16px rgba(0, 0, 0, 0.06);
}
```

- [ ] **Step 4: Run the smoke test; it now also verifies the font and image URLs**

```bash
keycloak/tests/smoke.sh http://localhost:8081 cdip-dev kc11
keycloak/tests/smoke.sh http://localhost:8082 cdip-dev kc26
```

Expected: `PASS` on both. A `css reference not served` failure means a path in `url(...)` is wrong relative to `resources/css/`.

Note the image is not referenced from any stylesheet yet, so only the fonts are exercised here. Task 4 adds the logo reference.

- [ ] **Step 5: Commit**

```bash
git add keycloak/themes/gundi/login/resources
git commit -m "Add Inter fonts, Gundi logo mark and design tokens to the theme"
```

---

### Task 4: Shared stylesheet and cascade guard

**Files:**
- Modify: `keycloak/themes/gundi/login/resources/css/gundi.css`
- Create: `keycloak/tests/check-css.sh`

**Interfaces:**
- Consumes: tokens from Task 3. Stable IDs verified in the spec: `kc-header`, `kc-header-wrapper`, `kc-page-title`, `kc-form`, `kc-form-wrapper`, `kc-form-login`, `kc-info`, `kc-info-wrapper`, `kc-login`, `username`, `password`, `reset-login`.
- Produces: `keycloak/tests/check-css.sh` (exit 0 = clean). Header, title, primary button, and link styling that Tasks 5 and 6 must not duplicate.

- [ ] **Step 1: Write the cascade guard**

`keycloak/tests/check-css.sh`:

```bash
#!/usr/bin/env bash
# Cascade guard: gundi.css is shared by Keycloak 11 (PatternFly 3) and 26 (PatternFly 5),
# so it may only use #kc-* ids, element, attribute and pseudo selectors.
# Any framework class selector must live in kc11.css or kc26.css instead.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
file="$here/../themes/gundi/login/resources/css/gundi.css"
pattern='\.(pf-|btn|card-pf|login-pf|form-|alert|checkbox|control-label)'
if grep -nE "$pattern" "$file"; then
  echo "FAIL: framework class selectors found in $file (move them to kc11.css / kc26.css)" >&2
  exit 1
fi
echo "PASS: gundi.css has no framework class selectors"
```

```bash
chmod +x keycloak/tests/check-css.sh
```

- [ ] **Step 2: Prove the guard detects a violation**

```bash
printf '.btn-primary { color: red; }\n' >> keycloak/themes/gundi/login/resources/css/gundi.css
keycloak/tests/check-css.sh; echo "exit=$?"
```

Expected: prints the offending line and `FAIL: ...`, `exit=1`. Then remove the line:

```bash
sed -i '' '/^\.btn-primary { color: red; }$/d' keycloak/themes/gundi/login/resources/css/gundi.css
keycloak/tests/check-css.sh
```

Expected: `PASS`. (On Linux use `sed -i` without the empty string.)

- [ ] **Step 3: Write gundi.css**

`keycloak/themes/gundi/login/resources/css/gundi.css`:

```css
/* Shared Gundi rules. Only stable #kc-* ids, element, attribute and pseudo selectors.
   Framework classes (PatternFly 3 / 5) belong in kc11.css / kc26.css.
   Enforced by keycloak/tests/check-css.sh. Loads after tokens.css. */

html,
body {
  font-family: var(--gundi-font);
  color: var(--gundi-text);
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

/* ---- Header: replace the realm display name with the Gundi mark + wordmark ----
   The wrapper prints realm.displayNameHtml. We collapse its text to nothing and draw
   the brand with pseudo-elements, so no realm content needs to change. */
#kc-header {
  color: var(--gundi-text);
  padding: 0;
}
#kc-header-wrapper {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  margin: 0 auto 28px;
  padding: 0;
  font-size: 0;          /* hides the text node */
  line-height: 0;
  letter-spacing: 0;     /* reset parent theme's letter-spacing so ::after is not affected */
  text-transform: none;
  color: transparent;
}
/* A realm may carry markup in displayNameHtml (e.g. Keycloak's default logo div). Hide it. */
#kc-header-wrapper > * {
  display: none;
}
#kc-header-wrapper::before {
  content: "";
  display: block;
  width: 58px;
  height: 48px;
  background: url("../img/gundi-mark.png") no-repeat center / contain;
}
#kc-header-wrapper::after {
  content: "GUNDI";
  display: block;
  font-family: var(--gundi-font);
  font-size: 26px;
  font-weight: 600;
  line-height: 1;
  letter-spacing: 0.08em;
  color: var(--gundi-text);
}

/* ---- Page title ---- */
#kc-page-title {
  font-family: var(--gundi-font);
  font-size: 22px;
  font-weight: 600;
  line-height: 1.3;
  color: var(--gundi-text);
  text-align: center;
  margin: 0 0 20px;
}

/* ---- Primary submit button (same id on 11 and 26) ---- */
#kc-login {
  display: block;
  width: 100%;
  min-height: 44px;
  padding: 0 16px;
  border: 0;
  border-radius: var(--gundi-radius-control);
  background: var(--gundi-primary);
  color: #ffffff;
  font-family: var(--gundi-font);
  font-size: 15px;
  font-weight: 600;
  line-height: 44px;
  cursor: pointer;
  transition: background-color 120ms ease;
}
#kc-login:hover {
  background: var(--gundi-primary-hover);
  color: #ffffff;
}
#kc-login:focus-visible {
  outline: 3px solid var(--gundi-focus-ring);
  outline-offset: 2px;
}

/* ---- Links inside the form and the info block ---- */
#kc-form a,
#kc-form-login a,
#kc-info a {
  color: var(--gundi-primary);
  font-weight: 500;
  text-decoration: none;
}
#kc-form a:hover,
#kc-form-login a:hover,
#kc-info a:hover {
  color: var(--gundi-primary-hover);
  text-decoration: underline;
}
#kc-info {
  color: var(--gundi-text-secondary);
  font-size: 14px;
}

/* ---- Username / password inputs by id (other pages' inputs are styled per version) ---- */
#username,
#password {
  font-family: var(--gundi-font);
  font-size: 15px;
  color: var(--gundi-text);
}
```

- [ ] **Step 4: Run the guard and the smoke test**

```bash
keycloak/tests/check-css.sh
keycloak/tests/smoke.sh http://localhost:8081 cdip-dev kc11
keycloak/tests/smoke.sh http://localhost:8082 cdip-dev kc26
```

Expected: all three `PASS`. The smoke test now also fetches `../img/gundi-mark.png`.

- [ ] **Step 5: Screenshot both versions and check the header**

```bash
keycloak/tests/screenshot.sh kc11 8081
keycloak/tests/screenshot.sh kc26 8082
```

View `kc11-login.png` and `kc26-login.png`. Expected on both: the sail mark with "GUNDI" beside it above the card, and **no** Keycloak logo (the fixture's `displayNameHtml` div is hidden; Review Focus 1). The green button reads "Log In" on 11 and "Sign In" on 26. Card, background, and inputs are still stock; that is Tasks 5 and 6.

- [ ] **Step 6: Commit**

```bash
git add keycloak/themes/gundi/login/resources/css/gundi.css keycloak/tests/check-css.sh
git commit -m "Add shared Gundi login stylesheet and cascade guard"
```

---

### Task 5: Keycloak 11 overrides (PatternFly 3)

**Files:**
- Modify: `keycloak/themes/gundi/login/resources/css/kc11.css`

**Interfaces:**
- Consumes: tokens (Task 3), shared rules (Task 4). PatternFly 3 classes from the KC 11 `keycloak` theme: `.login-pf`, `.login-pf-page`, `.card-pf`, `.login-pf-header`, `.form-control`, `.control-label`, `.btn-primary`, `.btn-default`, `.checkbox`, `.alert-error|-success|-warning|-info`, `.login-pf-settings`, `.login-pf-signup`, `#kc-form-options`, `#kc-form-buttons`.
- Produces: nothing consumed by later tasks.

- [ ] **Step 1: Write kc11.css**

`keycloak/themes/gundi/login/resources/css/kc11.css`:

```css
/* Keycloak 11 (PatternFly 3) class overrides for the Gundi theme. Loads after gundi.css. */

/* Flat page background instead of the keycloak-bg.png photo */
.login-pf body {
  background: var(--gundi-page-bg);
}
.login-pf-page {
  padding-top: 48px;
  padding-bottom: 48px;
}
/* Ids that exist only on 11 */
#kc-content-wrapper {
  margin-top: 0;
}

/* Card */
.login-pf-page .card-pf {
  max-width: 400px;
  margin: 0 auto;
  padding: 32px 32px 24px;
  background: var(--gundi-card-bg);
  border: 1px solid var(--gundi-divider);
  border-radius: var(--gundi-radius-card);
  box-shadow: var(--gundi-shadow-card);
}
.login-pf-page .login-pf-header {
  margin-bottom: 0;
}

/* Inputs */
.card-pf .form-control {
  height: 40px;
  padding: 0 12px;
  border: 1px solid var(--gundi-field-outline);
  border-radius: var(--gundi-radius-control);
  box-shadow: none;
  background: #ffffff;
  font-family: var(--gundi-font);
  font-size: 15px;
  color: var(--gundi-text);
}
.card-pf .form-control:focus {
  border-color: var(--gundi-primary);
  box-shadow: 0 0 0 3px var(--gundi-focus-ring);
  outline: 0;
}
.card-pf .control-label {
  font-family: var(--gundi-font);
  font-size: 14px;
  font-weight: 500;
  color: var(--gundi-text);
  margin-bottom: 6px;
}
.card-pf .form-group {
  margin-bottom: 16px;
}

/* Buttons (the primary submit is styled by #kc-login in gundi.css; these cover other pages) */
.login-pf-page .btn {
  font-family: var(--gundi-font);
  font-weight: 600;
  border-radius: var(--gundi-radius-control);
}
.login-pf-page .btn-primary,
.login-pf-page .btn-primary:focus {
  background: var(--gundi-primary);
  border-color: var(--gundi-primary);
  color: #ffffff;
}
.login-pf-page .btn-primary:hover,
.login-pf-page .btn-primary:active {
  background: var(--gundi-primary-hover);
  border-color: var(--gundi-primary-hover);
}
.login-pf-page .btn-default {
  background: #ffffff;
  border-color: var(--gundi-field-outline);
  color: var(--gundi-primary);
}
.login-pf-page .btn-default:hover {
  border-color: var(--gundi-primary);
  color: var(--gundi-primary-hover);
}
#kc-form-buttons {
  margin-top: 8px;
}

/* Remember me + forgot password row */
#kc-form-options .checkbox input[type="checkbox"] {
  accent-color: var(--gundi-primary);
}
#kc-form-options .checkbox label {
  color: var(--gundi-text-secondary);
  font-size: 14px;
}
.login-pf-page .login-pf-settings a,
.login-pf-page .login-pf-signup a {
  color: var(--gundi-primary);
}

/* Alerts as inline bands with a status-coloured left border */
.login-pf-page .alert {
  border: 0;
  border-left: 4px solid var(--gundi-text-secondary);
  border-radius: var(--gundi-radius-control);
  padding: 12px 14px;
  color: var(--gundi-text);
  background: var(--gundi-info-bg);
}
.login-pf-page .alert-error {
  background: var(--gundi-error-bg);
  border-left-color: var(--gundi-error);
}
.login-pf-page .alert-error .pficon {
  color: var(--gundi-error);
}
.login-pf-page .alert-success {
  background: var(--gundi-success-bg);
  border-left-color: var(--gundi-primary);
}
.login-pf-page .alert-success .pficon {
  color: var(--gundi-primary);
}
.login-pf-page .alert-warning {
  background: var(--gundi-warning-bg);
  border-left-color: var(--gundi-warning);
}
.login-pf-page .alert-warning .pficon {
  color: var(--gundi-warning);
}
.login-pf-page .alert-info {
  background: var(--gundi-info-bg);
  border-left-color: var(--gundi-text-secondary);
}

/* Phones */
@media (max-width: 480px) {
  .login-pf-page {
    padding-top: 24px;
  }
  .login-pf-page .card-pf {
    margin: 0 16px;
    padding: 24px 20px;
  }
}
```

- [ ] **Step 2: Smoke test and screenshots**

```bash
keycloak/tests/smoke.sh http://localhost:8081 cdip-dev kc11
keycloak/tests/screenshot.sh kc11 8081
```

View all four `kc11-*.png` files. Check against the spec:

- `kc11-login.png`: flat `#f7f9f7` page, white card with hairline border and rounded corners, Gundi header, inputs with light-gray outline, full-width green button, "Forgot Password?" link in green, remember-me checkbox present.
- `kc11-login-mobile.png`: card spans the width with a 16px gutter, no horizontal scrollbar.
- `kc11-error.png`: themed page with the error band (red left border on pale red).
- `kc11-error-noclient.png`: same treatment for the "Client not found" error (Review Focus 4).

Adjust padding or spacing values in `kc11.css` and re-run the screenshot until each matches. Do not add rules to `gundi.css` for 11-specific fixes.

- [ ] **Step 3: Commit**

```bash
git add keycloak/themes/gundi/login/resources/css/kc11.css
git commit -m "Style Keycloak 11 login pages with PatternFly 3 overrides"
```

---

### Task 6: Keycloak 26 overrides (PatternFly 5)

**Files:**
- Modify: `keycloak/themes/gundi/login/resources/css/kc26.css`

**Interfaces:**
- Consumes: tokens (Task 3), shared rules (Task 4). PatternFly 5 classes from the KC 26 `keycloak.v2` theme: `.pf-v5-c-login__main`, `.pf-v5-c-login__main-header`, `.pf-v5-c-login__main-body`, `.pf-v5-c-form-control` (a `span` wrapping the `input`), `.pf-v5-c-form__label`, `.pf-v5-c-button.pf-m-primary|.pf-m-secondary|.pf-m-link|.pf-m-control`, `.pf-v5-c-check__input`, `.pf-v5-c-alert.pf-m-inline.pf-m-danger|success|warning|info`, `#keycloak-bg` (the `body`), CSS variable `--keycloak-card-top-color`.
- Produces: nothing consumed by later tasks.

- [ ] **Step 1: Write kc26.css**

`keycloak/themes/gundi/login/resources/css/kc26.css`:

```css
/* Keycloak 26 (PatternFly 5) class overrides for the Gundi theme. Loads after gundi.css.
   Strategy: retheme PatternFly through its global tokens first, then patch the few
   components that still show blue or Red Hat defaults. */

:root {
  --pf-v5-global--FontFamily--text: var(--gundi-font);
  --pf-v5-global--FontFamily--heading: var(--gundi-font);
  --pf-v5-global--FontFamily--sans-serif: var(--gundi-font);
  --pf-v5-global--primary-color--100: var(--gundi-primary);
  --pf-v5-global--primary-color--200: var(--gundi-primary-hover);
  --pf-v5-global--active-color--100: var(--gundi-primary);
  --pf-v5-global--link--Color: var(--gundi-primary);
  --pf-v5-global--link--Color--hover: var(--gundi-primary-hover);
  --pf-v5-global--BorderRadius--sm: var(--gundi-radius-control);
  --pf-v5-global--BorderColor--100: var(--gundi-field-outline);
  --pf-v5-global--BorderColor--300: var(--gundi-field-outline);
  --pf-v5-global--danger-color--100: var(--gundi-error);
  --pf-v5-global--Color--100: var(--gundi-text);
  --pf-v5-global--Color--200: var(--gundi-text-secondary);
  --pf-v5-global--BackgroundColor--100: var(--gundi-card-bg);
  --keycloak-card-top-color: var(--gundi-primary);
}

/* Flat page background instead of the darkened Keycloak backdrop */
.login-pf body,
body#keycloak-bg {
  background: var(--gundi-page-bg);
}

/* Card */
.pf-v5-c-login__main {
  max-width: 400px;
  margin-left: auto;
  margin-right: auto;
  background: var(--gundi-card-bg);
  border: 1px solid var(--gundi-divider);
  border-top-width: 1px;                     /* remove the thick coloured top band */
  border-radius: var(--gundi-radius-card);
  box-shadow: var(--gundi-shadow-card);
}
.pf-v5-c-login__main-header {
  padding-top: 32px;
}
.pf-v5-c-login__main-body {
  padding-bottom: 24px;
}
.pf-v5-c-login__header {
  padding-bottom: 0;
}

/* Inputs: PF5 draws the border on the wrapping span via ::after */
.pf-v5-c-form-control {
  --pf-v5-c-form-control--BorderRadius: var(--gundi-radius-control);
  --pf-v5-c-form-control--BorderWidth: 1px;
  --pf-v5-c-form-control--after--BorderBottomColor: var(--gundi-field-outline);
  --pf-v5-c-form-control--hover--after--BorderBottomColor: var(--gundi-primary);
  --pf-v5-c-form-control--focus--after--BorderBottomColor: var(--gundi-primary);
  --pf-v5-c-form-control--focus--after--BorderBottomWidth: 1px;
  border: 1px solid var(--gundi-field-outline);
  border-radius: var(--gundi-radius-control);
  min-height: 40px;
}
.pf-v5-c-form-control:focus-within {
  border-color: var(--gundi-primary);
  box-shadow: 0 0 0 3px var(--gundi-focus-ring);
}
.pf-v5-c-form-control input {
  font-family: var(--gundi-font);
  font-size: 15px;
  color: var(--gundi-text);
}
.pf-v5-c-form__label-text {
  font-weight: 500;
  color: var(--gundi-text);
}

/* Buttons (the primary submit is styled by #kc-login in gundi.css; these cover other pages) */
.pf-v5-c-button {
  font-family: var(--gundi-font);
  font-weight: 600;
  border-radius: var(--gundi-radius-control);
}
.pf-v5-c-button.pf-m-primary {
  --pf-v5-c-button--m-primary--BackgroundColor: var(--gundi-primary);
  --pf-v5-c-button--m-primary--hover--BackgroundColor: var(--gundi-primary-hover);
  --pf-v5-c-button--m-primary--focus--BackgroundColor: var(--gundi-primary-hover);
  --pf-v5-c-button--m-primary--active--BackgroundColor: var(--gundi-primary-hover);
}
.pf-v5-c-button.pf-m-secondary {
  --pf-v5-c-button--m-secondary--Color: var(--gundi-primary);
  --pf-v5-c-button--m-secondary--BorderColor: var(--gundi-field-outline);
  --pf-v5-c-button--m-secondary--hover--Color: var(--gundi-primary-hover);
  --pf-v5-c-button--m-secondary--hover--BorderColor: var(--gundi-primary);
}
.pf-v5-c-button.pf-m-link {
  --pf-v5-c-button--m-link--Color: var(--gundi-primary);
  --pf-v5-c-button--m-link--hover--Color: var(--gundi-primary-hover);
}
/* Password visibility toggle */
.pf-v5-c-button.pf-m-control {
  color: var(--gundi-primary);
  border: 0;
}

/* Remember me */
.pf-v5-c-check__input {
  accent-color: var(--gundi-primary);
}
.pf-v5-c-check__label {
  color: var(--gundi-text-secondary);
  font-size: 14px;
}

/* Alerts as inline bands with a status-coloured left border */
.pf-v5-c-alert.pf-m-inline {
  --pf-v5-c-alert--BorderTopWidth: 0;
  border-left: 4px solid var(--gundi-text-secondary);
  border-radius: var(--gundi-radius-control);
  box-shadow: none;
  background: var(--gundi-info-bg);
  color: var(--gundi-text);
}
.pf-v5-c-alert.pf-m-inline.pf-m-danger {
  background: var(--gundi-error-bg);
  border-left-color: var(--gundi-error);
  --pf-v5-c-alert__icon--Color: var(--gundi-error);
}
.pf-v5-c-alert.pf-m-inline.pf-m-success {
  background: var(--gundi-success-bg);
  border-left-color: var(--gundi-primary);
  --pf-v5-c-alert__icon--Color: var(--gundi-primary);
}
.pf-v5-c-alert.pf-m-inline.pf-m-warning {
  background: var(--gundi-warning-bg);
  border-left-color: var(--gundi-warning);
  --pf-v5-c-alert__icon--Color: var(--gundi-warning);
}
.pf-v5-c-alert.pf-m-inline.pf-m-info {
  background: var(--gundi-info-bg);
  border-left-color: var(--gundi-text-secondary);
  --pf-v5-c-alert__icon--Color: var(--gundi-text-secondary);
}

/* Phones */
@media (max-width: 480px) {
  .pf-v5-c-login__main {
    margin-left: 16px;
    margin-right: 16px;
  }
}
```

- [ ] **Step 2: Smoke test and screenshots**

```bash
keycloak/tests/smoke.sh http://localhost:8082 cdip-dev kc26
keycloak/tests/screenshot.sh kc26 8082
```

View all four `kc26-*.png` files. Check against the spec:

- `kc26-login.png`: flat page, white rounded card without the blue top band, Gundi header, "Sign in to Gundi" title, outlined inputs, password eye icon in green, full-width green "Sign In" button, green "Forgot Password?" link.
- `kc26-login-mobile.png`: card spans the width with a 16px gutter.
- `kc26-error.png` and `kc26-error-noclient.png`: themed with a red-left-border error band, no blue anywhere.

If a control still shows PatternFly blue, find its variable name in the served `vendor/patternfly-v5/patternfly.min.css` (search for the component class) and override that variable on the component selector inside `kc26.css`. Do not touch `gundi.css`.

- [ ] **Step 3: Confirm dark mode is off**

```bash
docker run --rm --add-host=host.docker.internal:host-gateway -v "$PWD/keycloak/tests/shots:/out" zenika/alpine-chrome:latest \
  --no-sandbox --headless --disable-gpu --hide-scrollbars --virtual-time-budget=3000 \
  --force-dark-mode --enable-features=WebContentsForceDark --window-size=1280,900 \
  --screenshot=/out/kc26-login-forced-dark.png \
  "http://host.docker.internal:8082/auth/realms/cdip-dev/protocol/openid-connect/auth?client_id=cdip-kong-gateway&response_type=code&scope=openid&redirect_uri=http%3A%2F%2Flocalhost%3A8000%2F"
```

View `kc26-login-forced-dark.png`. Expected: identical light design. With `darkMode=true` the 26 template emits a script that adds the `pf-v5-theme-dark` class from `prefers-color-scheme`; with `darkMode=false` that script is absent, so the string must not appear in the HTML at all:

```bash
curl -s "http://localhost:8082/auth/realms/cdip-dev/protocol/openid-connect/auth?client_id=cdip-kong-gateway&response_type=code&scope=openid&redirect_uri=http%3A%2F%2Flocalhost%3A8000%2F" | grep -c 'pf-v5-theme-dark' || true
```

Expected: `0`.

- [ ] **Step 4: Commit**

```bash
git add keycloak/themes/gundi/login/resources/css/kc26.css
git commit -m "Style Keycloak 26 login pages with PatternFly 5 overrides"
```

---

### Task 7: Dockerfiles and local image verification

**Files:**
- Create: `keycloak/Dockerfile.kc11`
- Create: `keycloak/Dockerfile.kc26`

**Interfaces:**
- Consumes: the theme folder from Tasks 2–6; Task 1 fixture and scripts.
- Produces: images buildable from the repo root with `docker build -f keycloak/Dockerfile.kc11 -t gundi-keycloak:kc11 .` and `docker build -f keycloak/Dockerfile.kc26 -t gundi-keycloak:kc26 .`, each containing `/…/themes/gundi/login/theme.properties` for its version and no `theme.kc*.properties` files. Task 8 builds these in CI.

- [ ] **Step 1: Write Dockerfile.kc11**

`keycloak/Dockerfile.kc11`:

```dockerfile
# Production Keycloak 11 image with the Gundi login theme baked in.
# Build from the repo root:   docker build -f keycloak/Dockerfile.kc11 -t gundi-keycloak:kc11 .
# The base image runs as uid 1000, so files are chowned to it. Only the KC 11 properties
# file is copied, renamed to theme.properties. No RUN step, no shell, nothing else changes.
FROM quay.io/keycloak/keycloak:11.0.2

COPY --chown=1000:0 keycloak/themes/gundi/login/resources  /opt/jboss/keycloak/themes/gundi/login/resources
COPY --chown=1000:0 keycloak/themes/gundi/login/messages   /opt/jboss/keycloak/themes/gundi/login/messages
COPY --chown=1000:0 keycloak/themes/gundi/login/theme.kc11.properties /opt/jboss/keycloak/themes/gundi/login/theme.properties
```

- [ ] **Step 2: Write Dockerfile.kc26**

`keycloak/Dockerfile.kc26`:

```dockerfile
# Keycloak 26 image with the Gundi login theme baked in. Input to the KC 26 upgrade rehearsal.
# Build from the repo root:   docker build -f keycloak/Dockerfile.kc26 -t gundi-keycloak:kc26 .
# Deliberately does not run `kc.sh build`; the upgrade design owns the optimized-build decision
# and can layer on top of this image or copy the theme folder into its own.
FROM quay.io/keycloak/keycloak:26.7

COPY --chown=1000:0 keycloak/themes/gundi/login/resources  /opt/keycloak/themes/gundi/login/resources
COPY --chown=1000:0 keycloak/themes/gundi/login/messages   /opt/keycloak/themes/gundi/login/messages
COPY --chown=1000:0 keycloak/themes/gundi/login/theme.kc26.properties /opt/keycloak/themes/gundi/login/theme.properties
```

- [ ] **Step 3: Build both images**

```bash
docker build --platform linux/amd64 -f keycloak/Dockerfile.kc11 -t gundi-keycloak:kc11 .
docker build -f keycloak/Dockerfile.kc26 -t gundi-keycloak:kc26 .
```

Expected: both succeed. Confirm the file layout inside each image:

```bash
docker run --rm --platform linux/amd64 --entrypoint ls gundi-keycloak:kc11 -la /opt/jboss/keycloak/themes/gundi/login/
docker run --rm --entrypoint ls gundi-keycloak:kc26 /opt/keycloak/themes/gundi/login/
```

Expected: `messages`, `resources`, `theme.properties` and nothing else; owner `1000` on kc11.

- [ ] **Step 4: Stop the compose harness and run the built images without bind mounts**

```bash
docker compose -f keycloak/compose.theme-dev.yml down
docker run -d --name kc11-img --platform linux/amd64 -p 8081:8080 \
  -e KEYCLOAK_USER=admin -e KEYCLOAK_PASSWORD=admin -e DB_VENDOR=h2 \
  -e KEYCLOAK_IMPORT=/tmp/realm.json \
  -v "$PWD/keycloak/dev/realm-with-theme.json:/tmp/realm.json:ro" \
  gundi-keycloak:kc11 -b 0.0.0.0
docker run -d --name kc26-img -p 8082:8080 \
  -e KC_BOOTSTRAP_ADMIN_USERNAME=admin -e KC_BOOTSTRAP_ADMIN_PASSWORD=admin \
  -e KC_HTTP_RELATIVE_PATH=/auth \
  -v "$PWD/keycloak/dev/realm-with-theme.json:/opt/keycloak/data/import/realm.json:ro" \
  gundi-keycloak:kc26 start-dev --import-realm
keycloak/tests/wait-ready.sh http://localhost:8082/auth/realms/cdip-dev 300
keycloak/tests/wait-ready.sh http://localhost:8081/auth/realms/cdip-dev 300
```

- [ ] **Step 5: Smoke test the images**

```bash
keycloak/tests/smoke.sh http://localhost:8081 cdip-dev kc11
keycloak/tests/smoke.sh http://localhost:8082 cdip-dev kc26
```

Expected: `PASS` on both. This proves the theme works from the image alone, with Keycloak 11's theme caching on (the image runs without the `-Dkeycloak.theme.*` flags).

- [ ] **Step 6: Clean up the image containers and bring the dev harness back**

```bash
docker rm -f kc11-img kc26-img
docker compose -f keycloak/compose.theme-dev.yml up -d
```

- [ ] **Step 7: Commit**

```bash
git add keycloak/Dockerfile.kc11 keycloak/Dockerfile.kc26
git commit -m "Add Dockerfiles baking the Gundi theme into Keycloak 11 and 26 images"
```

---

### Task 8: CI workflow — build, smoke test, push on main

**Files:**
- Create: `.github/workflows/keycloak-theme.yml`

**Interfaces:**
- Consumes: Dockerfiles (Task 7), `keycloak/tests/*.sh` (Tasks 1 and 4), `keycloak/dev/realm-with-theme.json` (Task 1), the shared reusable workflow `PADAS/gundi-workflows/.github/workflows/build_docker.yml@v11` (inputs: `workload_identity_provider`, `repository`, `tag`, `dockerfile`; it always pushes, so it runs only after the test job), repository variable `WORKLOAD_IDENTITY_PROVIDER` (already used by `main.yml`).
- Produces: images at `europe-west3-docker.pkg.dev/serca-artifact-registry/gundi/keycloak:11.0.2-gundi-<sha>` and `:26.7-gundi-<sha>` on every push to `main` touching `keycloak/**`.

- [ ] **Step 1: Write the workflow**

`.github/workflows/keycloak-theme.yml`:

```yaml
name: Keycloak Gundi theme images

on:
  push:
    branches: [main]
    paths:
      - 'keycloak/**'
      - '.github/workflows/keycloak-theme.yml'
  pull_request:
    paths:
      - 'keycloak/**'
      - '.github/workflows/keycloak-theme.yml'

jobs:
  test:
    # Builds each image locally (no push), boots it with the dev realm, and runs the smoke test.
    # The shared build_docker workflow always pushes, so it must not run before this passes.
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        include:
          - version: kc11
            port: 8081
          - version: kc26
            port: 8082
    steps:
      - uses: actions/checkout@v4

      - name: Cascade guard (shared stylesheet has no framework classes)
        run: keycloak/tests/check-css.sh

      - name: Build image
        run: docker build -f keycloak/Dockerfile.${{ matrix.version }} -t gundi-keycloak:${{ matrix.version }} .

      - name: Start Keycloak 11
        if: matrix.version == 'kc11'
        run: |
          docker run -d --name kc -p 8081:8080 \
            -e KEYCLOAK_USER=admin -e KEYCLOAK_PASSWORD=admin -e DB_VENDOR=h2 \
            -e KEYCLOAK_IMPORT=/tmp/realm.json \
            -v "$PWD/keycloak/dev/realm-with-theme.json:/tmp/realm.json:ro" \
            gundi-keycloak:kc11 -b 0.0.0.0

      - name: Start Keycloak 26
        if: matrix.version == 'kc26'
        run: |
          docker run -d --name kc -p 8082:8080 \
            -e KC_BOOTSTRAP_ADMIN_USERNAME=admin -e KC_BOOTSTRAP_ADMIN_PASSWORD=admin \
            -e KC_HTTP_RELATIVE_PATH=/auth \
            -v "$PWD/keycloak/dev/realm-with-theme.json:/opt/keycloak/data/import/realm.json:ro" \
            gundi-keycloak:kc26 start-dev --import-realm

      - name: Wait for Keycloak
        run: keycloak/tests/wait-ready.sh http://localhost:${{ matrix.port }}/auth/realms/cdip-dev 300

      - name: Smoke test
        run: keycloak/tests/smoke.sh http://localhost:${{ matrix.port }} cdip-dev ${{ matrix.version }}

      - name: Keycloak logs
        if: failure()
        run: docker logs kc

  vars:
    runs-on: ubuntu-latest
    outputs:
      sha: ${{ steps.vars.outputs.sha }}
    steps:
      - uses: actions/checkout@v4
      - id: vars
        run: echo "sha=$(git rev-parse --short HEAD)" >> "$GITHUB_OUTPUT"

  push:
    # Only from main, only after both smoke tests pass. Nothing deploys; see keycloak/RUNBOOK.md.
    if: github.ref == 'refs/heads/main'
    needs: [test, vars]
    strategy:
      matrix:
        include:
          - version: kc11
            keycloak: "11.0.2"
          - version: kc26
            keycloak: "26.7"
    uses: PADAS/gundi-workflows/.github/workflows/build_docker.yml@v11
    with:
      workload_identity_provider: ${{ vars.WORKLOAD_IDENTITY_PROVIDER }}
      repository: europe-west3-docker.pkg.dev/serca-artifact-registry/gundi/keycloak
      tag: ${{ matrix.keycloak }}-gundi-${{ needs.vars.outputs.sha }}
      dockerfile: keycloak/Dockerfile.${{ matrix.version }}
```

- [ ] **Step 2: Lint the workflow**

```bash
docker run --rm -v "$PWD:/repo" -w /repo rhysd/actionlint:latest -color .github/workflows/keycloak-theme.yml
```

Expected: no output (clean). Fix any reported YAML or expression errors.

- [ ] **Step 3: Dry-run the test job steps locally for kc26 (fast path)**

The `test` job is plain shell; run its steps by hand to be sure they compose:

```bash
docker compose -f keycloak/compose.theme-dev.yml down
keycloak/tests/check-css.sh
docker build -f keycloak/Dockerfile.kc26 -t gundi-keycloak:kc26 .
docker run -d --name kc -p 8082:8080 \
  -e KC_BOOTSTRAP_ADMIN_USERNAME=admin -e KC_BOOTSTRAP_ADMIN_PASSWORD=admin \
  -e KC_HTTP_RELATIVE_PATH=/auth \
  -v "$PWD/keycloak/dev/realm-with-theme.json:/opt/keycloak/data/import/realm.json:ro" \
  gundi-keycloak:kc26 start-dev --import-realm
keycloak/tests/wait-ready.sh http://localhost:8082/auth/realms/cdip-dev 300
keycloak/tests/smoke.sh http://localhost:8082 cdip-dev kc26
docker rm -f kc
docker compose -f keycloak/compose.theme-dev.yml up -d
```

Expected: `PASS`.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/keycloak-theme.yml
git commit -m "Add CI workflow that builds, smoke-tests and pushes Keycloak theme images"
```

- [ ] **Step 5: Push the branch and open a draft PR to exercise the `test` job on GitHub**

```bash
git push -u origin HEAD
gh pr create --draft --title "Gundi Keycloak login theme (KC 11 + 26)" --body "$(cat <<'EOF'
Implements docs/superpowers/specs/2026-09-22-keycloak-gundi-login-theme-design.md.

- `keycloak/themes/gundi`: CSS-only login theme, one source for Keycloak 11.0.2 and 26.7
- `keycloak/Dockerfile.kc11` / `.kc26`: official image + theme folder
- `keycloak/compose.theme-dev.yml` + `keycloak/tests/*`: local harness, smoke test, screenshots
- `.github/workflows/keycloak-theme.yml`: build, smoke-test, push on main
- `keycloak/RUNBOOK.md`: manual prod rollout and rollback

Nothing deploys automatically.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
gh run watch --exit-status
```

Expected: the `test` matrix passes for both versions on the PR. The `push` job is skipped on pull requests. If `kc11` times out in CI, raise the `wait-ready.sh` timeout argument in the workflow to `420`.

---

### Task 9: Runbook

**Files:**
- Create: `keycloak/RUNBOOK.md`

**Interfaces:**
- Consumes: image tags produced by Task 8; realm names `cdip-dev` and `cdip-prod`; prod Deployment `keycloak`, container `keycloak`, namespace `cdip-auth`, kubectl context `cdip-prod`.
- Produces: the operator document referenced by the spec and the PR.

- [ ] **Step 1: Write the runbook**

`keycloak/RUNBOOK.md`:

````markdown
# Gundi Keycloak login theme — operations

Theme source: `keycloak/themes/gundi`. Design: `docs/superpowers/specs/2026-09-22-keycloak-gundi-login-theme-design.md`.
Images are built and pushed by `.github/workflows/keycloak-theme.yml` on every push to `main` that touches `keycloak/**`.
Nothing deploys automatically.

## Local development

```bash
docker compose -f keycloak/compose.theme-dev.yml up -d     # KC 11 on :8081, KC 26 on :8082, admin/admin
keycloak/tests/wait-ready.sh http://localhost:8081/auth/realms/cdip-dev
keycloak/tests/smoke.sh http://localhost:8081 cdip-dev kc11
keycloak/tests/smoke.sh http://localhost:8082 cdip-dev kc26
keycloak/tests/screenshot.sh kc11 8081                      # PNGs in keycloak/tests/shots/
keycloak/tests/check-css.sh                                 # shared stylesheet has no framework classes
```

Login page URL (either port):
`/auth/realms/cdip-dev/protocol/openid-connect/auth?client_id=cdip-kong-gateway&response_type=code&scope=openid&redirect_uri=http%3A%2F%2Flocalhost%3A8000%2F`

Test users in the imported realm: `dev` (plain login) and `theme-tester` / `theme-tester`, which is forced through
the update-password and configure-OTP pages on first login. `keycloak/dev/realm-with-theme.json` is a copy of
`keycloak/cdip-dev-realm.json` with `loginTheme`, `sslRequired: none`, a `displayNameHtml` fixture and that user; regenerate
it from the Task 1 script in the implementation plan if the base realm export changes.

## Prod rollout — Keycloak 11 (`cdip-prod01`, namespace `cdip-auth`)

Prod Keycloak is a single replica applied from a raw manifest, not ArgoCD. Order matters: image first, then realms.

### 1. Confirm the base image and pick the tag

```bash
kubectl --context cdip-prod -n cdip-auth get deploy keycloak \
  -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
```

Must print `quay.io/keycloak/keycloak:11.0.2`. If it prints anything else, stop: `keycloak/Dockerfile.kc11` must be
rebased on the running image before continuing.

Pick the tag from the latest successful `Keycloak Gundi theme images` run on `main`:
`europe-west3-docker.pkg.dev/serca-artifact-registry/gundi/keycloak:11.0.2-gundi-<short sha>`.

### 2. Swap the image (restart; do this in the 02:00 UTC window or an agreed off-hours slot)

```bash
TAG=11.0.2-gundi-<short sha>
kubectl --context cdip-prod -n cdip-auth set image deploy/keycloak \
  keycloak=europe-west3-docker.pkg.dev/serca-artifact-registry/gundi/keycloak:$TAG
kubectl --context cdip-prod -n cdip-auth rollout status deploy/keycloak --timeout=5m
```

If the pod reports `ImagePullBackOff`, the node service account lacks read access to the `gundi` Artifact Registry
repository; the portal in the same cluster pulls from `gundi/admin-portal`, so compare that Deployment's
`imagePullSecrets`. Roll back (below) rather than leaving the Deployment in that state.

Verify the stock page still renders (realms are not flipped yet):

```bash
curl -sf -o /dev/null -w '%{http_code}\n' \
  'https://cdip-auth.pamdas.org/auth/realms/cdip-dev/protocol/openid-connect/auth?client_id=cdip-admin-portal&response_type=code&scope=openid&redirect_uri=https%3A%2F%2Fexample.invalid%2F'
```

Expected `200` (Keycloak renders an error page for the bad redirect, which is fine here).

### 3. Stage on the `cdip-dev` realm

Admin console `https://cdip-auth.pamdas.org/auth/admin/` → realm **cdip-dev** → **Realm Settings** → **Themes** tab →
**Login Theme** = `gundi` → **Save**. No restart.

Before flipping, check the same tab and **Login** tab for `cdip-prod` later: if **User registration** or any
identity provider is enabled there, add the register and social-provider pages to the manual walk below.

Log out of the dev portal and log back in. Walk every row:

| Page | How to reach |
|---|---|
| Login | dev portal → Login |
| Forgot password | "Forgot Password?" link |
| Info | submit the forgot-password form |
| Update password | log in as a user with the `Update Password` required action set in the admin console |
| Configure OTP / OTP login | same, with `Configure OTP` |
| Error | change `redirect_uri` in the auth URL to a value the client does not allow |

Check on a phone or a 375px-wide browser window that the card fills the width with a gutter and nothing scrolls sideways.

### 4. Flip `cdip-prod`

Same setting on realm **cdip-prod**. Log in through the prod portal and repeat the login row at minimum.

## Rollback

- **Visual problem:** realm → Realm Settings → Themes → Login Theme = `keycloak` → Save. Immediate, no restart.
- **Image problem:** revert every realm that points at `gundi` first (a realm pointing at a theme the image lacks
  logs an error and falls back to the built-in theme, but do not rely on it), then

```bash
kubectl --context cdip-prod -n cdip-auth rollout undo deploy/keycloak
kubectl --context cdip-prod -n cdip-auth rollout status deploy/keycloak --timeout=5m
```

## Keycloak 26 upgrade hand-off

The realm `loginTheme` value lives in the database, so after the upgrade copies the auth DB both realms already point at
`gundi`. The 26 image used at cutover **must** contain the theme: base it on `keycloak/Dockerfile.kc26` or copy
`keycloak/themes/gundi/login/{resources,messages}` plus `theme.kc26.properties` (renamed to `theme.properties`) into
`/opt/keycloak/themes/gundi/login/`. Add the verification table above to the rehearsal checklist. The upgrade design doc
(`2026-07-14-keycloak-upgrade-design.md`, branch `keycloak-26-upgrade-doc`) still lists the theme as stock and needs
updating when that doc lands.
````

- [ ] **Step 2: Check every command in the runbook is copy-pasteable**

```bash
grep -nE '<[a-z ]+>' keycloak/RUNBOOK.md
```

Expected: only the two intentional `<short sha>` placeholders (in the tag lines). Anything else is a placeholder to fill.

- [ ] **Step 3: Commit and push**

```bash
git add keycloak/RUNBOOK.md
git commit -m "Add Keycloak theme runbook: local dev, prod rollout, rollback, 26 hand-off"
git push
```

---

### Task 10: Manual verification walk (human, both local versions)

This task needs a person with a browser. It completes the spec's "Manual visual" test row before the PR leaves draft.

**Files:** none.

- [ ] **Step 1: Bring up the harness**

```bash
docker compose -f keycloak/compose.theme-dev.yml up -d
keycloak/tests/wait-ready.sh http://localhost:8081/auth/realms/cdip-dev 300
keycloak/tests/wait-ready.sh http://localhost:8082/auth/realms/cdip-dev 300
```

- [ ] **Step 2: Walk the table on Keycloak 11 (`http://localhost:8081`)**

Open the login URL from the runbook on port 8081.

| Page | How to reach | Pass criteria |
|---|---|---|
| Login | the URL | Gundi header, no Keycloak logo, white rounded card, green button "Log In" |
| Forgot password | "Forgot Password?" | same card, green "Submit", green back link |
| Info | submit forgot-password with `dev` | success band with green left border |
| Update password | log in as `theme-tester` / `theme-tester` | two outlined inputs, green submit |
| Configure OTP | continue after update password | QR code visible, outlined OTP input, green submit |
| Error | change `redirect_uri` to `http://evil.example/` | red-left-border error band |

- [ ] **Step 3: Walk the table on Keycloak 26 (`http://localhost:8082`)**

Same rows plus:

| Page | How to reach | Pass criteria |
|---|---|---|
| Logout confirmation | `http://localhost:8082/auth/realms/cdip-dev/protocol/openid-connect/logout` (no `id_token_hint`) | themed card with green "Logout" button |
| Password visibility toggle | login page eye icon | icon green, toggles the field |

Title reads "Sign in to Gundi" on 26 and "Log In" on 11 (expected, see spec). Tab title reads "Sign in to Gundi" on both.

- [ ] **Step 4: Phone width**

Resize the window to 375px wide on both versions' login pages. Pass: card fills the width with a visible gutter, no horizontal scroll.

- [ ] **Step 5: Record the outcome and mark the PR ready**

Add a comment on the PR listing any row that failed and the fix commit, then:

```bash
gh pr ready
```
