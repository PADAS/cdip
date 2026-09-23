#!/usr/bin/env bash
# Usage: keycloak/tests/screenshot.sh <kc11|kc26> <host-port>
# Renders login and error pages of a running local Keycloak to PNG with headless Chrome in Docker.
# Output: keycloak/tests/shots/<version>-{login,login-mobile,login-error,error,error-noclient}.png
set -euo pipefail
version=${1:?usage: screenshot.sh <kc11|kc26> <host-port>}
port=${2:?host port, e.g. 8081}
here=$(cd "$(dirname "$0")" && pwd)
out="$here/shots"
mkdir -p "$out"

auth="http://host.docker.internal:$port/auth/realms/cdip-dev/protocol/openid-connect/auth"
local_auth="http://localhost:$port/auth/realms/cdip-dev/protocol/openid-connect/auth"
ok_redirect="redirect_uri=http%3A%2F%2Flocalhost%3A8000%2F"
bad_redirect="redirect_uri=http%3A%2F%2Fevil.example%2F"

shot() { # <name> <WxH> <url>
  docker run --rm --add-host=host.docker.internal:host-gateway -v "$out:/out" zenika/alpine-chrome:latest \
    --no-sandbox --headless --disable-gpu --hide-scrollbars --virtual-time-budget=3000 \
    --window-size="$2" --screenshot="/out/$version-$1.png" "$3" >/dev/null 2>&1
  echo "wrote $out/$version-$1.png"
}

# The invalid-credentials alert only exists on the POST response, so the form is submitted with
# curl and the returned HTML is rendered from disk. <base> points resources at the live server;
# --disable-web-security lets the file:// page load the theme's fonts cross-origin.
fail() { echo "FAIL: $*" >&2; exit 1; }

shot_login_error() {
  local jar html page action
  jar=$(mktemp) && html="$out/$version-login-error.html"
  trap 'rm -f "$jar" "$html"' RETURN EXIT
  page=$(curl -sf -c "$jar" "$local_auth?client_id=cdip-kong-gateway&response_type=code&scope=openid&$ok_redirect") \
    || fail "login page did not return 200 on port $port"
  action=$(grep -o 'action="[^"]*"' <<<"$page" | head -1 | sed 's/^action="//;s/"$//;s/&amp;/\&/g') \
    || fail "no form action found in the login page"
  curl -sf -b "$jar" -c "$jar" -X POST --data-urlencode "username=theme-tester" --data-urlencode "password=wrong" "$action" \
    | sed -E "s#<head([^>]*)>#<head\\1><base href=\"http://host.docker.internal:$port/\">#" > "$html" \
    || fail "login POST failed"
  grep -q '<base href=' "$html" || fail "no <head> found to inject <base> into"
  docker run --rm --add-host=host.docker.internal:host-gateway -v "$out:/out" zenika/alpine-chrome:latest \
    --no-sandbox --headless --disable-gpu --hide-scrollbars --disable-web-security --virtual-time-budget=3000 \
    --window-size=1280,900 --screenshot="/out/$version-login-error.png" "file:///out/$version-login-error.html" >/dev/null 2>&1
  echo "wrote $out/$version-login-error.png"
}

shot login          1280,900 "$auth?client_id=cdip-kong-gateway&response_type=code&scope=openid&$ok_redirect"
shot login-mobile   375,812  "$auth?client_id=cdip-kong-gateway&response_type=code&scope=openid&$ok_redirect"
shot_login_error
shot error          1280,900 "$auth?client_id=cdip-kong-gateway&response_type=code&scope=openid&$bad_redirect"
shot error-noclient 1280,900 "$auth?client_id=does-not-exist&response_type=code&scope=openid&$ok_redirect"
