#!/bin/sh
#
# bootstrap-kong.sh — wire up the dev Kong gateway to mirror prod's
# ingress -> kong -> service flow with the kong-oidc plugin authenticating
# against Keycloak.
#
# Idempotent: uses PUT for services/routes (upsert by name) and replaces the
# oidc plugin on each run so config edits in this script take effect after a
# `docker compose restart kong-bootstrap`.
#
# Run inside the compose network (kong/keycloak/web hostnames are reachable).

set -eu

KONG_ADMIN="${KONG_ADMIN:-http://kong:8001}"
KEYCLOAK_DISCOVERY="${KEYCLOAK_DISCOVERY:-http://keycloak:8080/auth/realms/cdip-dev/.well-known/openid-configuration}"
OIDC_CLIENT_ID="${OIDC_CLIENT_ID:-cdip-kong-gateway}"
OIDC_CLIENT_SECRET="${OIDC_CLIENT_SECRET:-dev-kong-oidc-secret}"
# kong-oidc requires session_secret to be base64-encoded 32 raw bytes
# (lua-resty-session decodes it). This is a fixed dev secret — never reused
# anywhere with real auth value.
OIDC_SESSION_SECRET="${OIDC_SESSION_SECRET:-D5+sOKjh/60/ysGpZoiGsyUSicdU8+UXQP3L1v2GiAA=}"
WEB_HOST="${WEB_HOST:-web.127.0.0.1.nip.io}"
WEB_UPSTREAM_URL="${WEB_UPSTREAM_URL:-http://web:8888}"

echo "[bootstrap-kong] waiting for Kong Admin API at $KONG_ADMIN ..."
until curl -fsS "$KONG_ADMIN/status" >/dev/null 2>&1; do
    sleep 2
done
echo "[bootstrap-kong] Kong Admin API ready."

echo "[bootstrap-kong] waiting for Keycloak discovery at $KEYCLOAK_DISCOVERY ..."
until curl -fsS "$KEYCLOAK_DISCOVERY" >/dev/null 2>&1; do
    sleep 2
done
echo "[bootstrap-kong] Keycloak realm import complete."

echo "[bootstrap-kong] upserting service cdip-web -> $WEB_UPSTREAM_URL"
curl -fsS -o /dev/null -X PUT "$KONG_ADMIN/services/cdip-web" \
    --data "url=$WEB_UPSTREAM_URL"

echo "[bootstrap-kong] upserting route cdip-web-route on host $WEB_HOST"
curl -fsS -o /dev/null -X PUT "$KONG_ADMIN/services/cdip-web/routes/cdip-web-route" \
    --data "hosts[]=$WEB_HOST" \
    --data "preserve_host=true" \
    --data "strip_path=false"

# Tear down any existing plugins on this route (e.g. an oidc plugin from an
# earlier run with a different randomly-assigned id). Filter to UUIDs that
# correspond to plugins specifically — the API response also contains
# route.id; DELETE on a non-plugin uuid returns 404 which we ignore.
echo "[bootstrap-kong] tearing down existing plugins on cdip-web-route"
curl -fsS "$KONG_ADMIN/routes/cdip-web-route/plugins" 2>/dev/null \
    | tr ',{}' '\n' | grep -oE '"id":"[0-9a-f-]{36}"' | cut -d'"' -f4 | sort -u \
    | while read pid; do
        curl -sS -o /dev/null -X DELETE "$KONG_ADMIN/plugins/$pid" || true
    done

echo "[bootstrap-kong] upserting oidc plugin (bearer_only=no, browser SSO)"
# Stable plugin id so PUT acts as an upsert — re-running this script just
# overwrites the config in place, no find-and-delete needed.
# bearer_only=no -> kong-oidc redirects unauthenticated browser requests to
# Keycloak and sets a session cookie; on success it injects X-Userinfo upstream
# which Django's SimpleUserInfoBackend reads.
OIDC_PLUGIN_ID="11111111-2222-3333-4444-555555555555"
# --data-urlencode (not --data) so values with + / = (esp. base64
# session_secret) survive the form-encode/decode round-trip intact.
curl -fsS -o /dev/null -X PUT "$KONG_ADMIN/plugins/$OIDC_PLUGIN_ID" \
    --data-urlencode "name=oidc" \
    --data-urlencode "route.name=cdip-web-route" \
    --data-urlencode "config.client_id=$OIDC_CLIENT_ID" \
    --data-urlencode "config.client_secret=$OIDC_CLIENT_SECRET" \
    --data-urlencode "config.discovery=$KEYCLOAK_DISCOVERY" \
    --data-urlencode "config.realm=cdip-dev" \
    --data-urlencode "config.bearer_only=no" \
    --data-urlencode "config.session_secret=$OIDC_SESSION_SECRET" \
    --data-urlencode "config.scope=openid email profile" \
    --data-urlencode "config.ssl_verify=no" \
    --data-urlencode "config.token_endpoint_auth_method=client_secret_post"

echo "[bootstrap-kong] done."
