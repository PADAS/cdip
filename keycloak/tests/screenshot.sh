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
