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

# 3. Every url(...) inside OUR stylesheets (fonts, logo) must be served.
#    Only tokens/gundi/kc11/kc26: the parent theme's own stylesheet is also served under
#    our theme path and stock Keycloak 11's login.css carries a dead image reference.
while read -r a; do
  [[ -z $a ]] && continue
  case $a in
    *login/gundi/css/tokens.css|*login/gundi/css/gundi.css|*login/gundi/css/kc11.css|*login/gundi/css/kc26.css) ;;
    *) continue ;;
  esac
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
  # The h1 text follows a newline (and, in dev mode, a <!-- template: … --> comment) after the
  # opening tag, so collapse newlines and allow whitespace/comments before matching.
  tr -d '\n' <<<"$html" | grep -qE 'id="kc-page-title"[^>]*>([[:space:]]|<!--[^>]*-->)*Sign in to Gundi' \
    || fail "loginAccountTitle override missing on kc26 (h1 #kc-page-title does not read 'Sign in to Gundi')"
fi
grep -q 'id="kc-page-title"' <<<"$html" || fail "kc-page-title element missing"

echo "PASS: $version gundi theme serves all assets from $base"
