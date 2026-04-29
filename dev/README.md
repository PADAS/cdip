# Local development stack

The compose stack mirrors the prod auth flow:

    browser → Caddy (TLS edge) → Kong (kong-oidc plugin) → Django web

Kong's `oidc` plugin authenticates against the local Keycloak, then injects
`X-Userinfo` (base64 JSON) on the upstream request. Django reads the header
via `cdip_admin.auth.middleware.OidcRemoteUserMiddleware` and resolves the
user through `SimpleUserInfoBackend`. No Django-side OIDC client is involved
in the request path; Django trusts what Kong forwards.

## First run

```bash
./dev.sh setup     # builds, migrates, seeds the dev superuser
./dev.sh start     # docker compose up -d
```

## Opt-in services

Two services are sibling-repo dependent and **can't start without local
clones of those repos**. They're env-var-configurable and (where possible)
profile-gated so the default stack always comes up cleanly.

| Service | Sibling repo | Override | Profile-gated? |
|---|---|---|---|
| `kong` | `gundi-kp-dynamic-routing` | `KONG_DIR=/abs/path` | No (kong is required for the auth flow) |
| `portal` | `gundi-portal` (React) | `PORTAL_DIR=/abs/path` | Yes — `--profile portal` |

Set the paths in a `.env` file at the worktree root (already gitignored):

```bash
cat >> .env <<EOF
KONG_DIR=/Users/me/padas/gundi-kp-dynamic-routing
PORTAL_DIR=/Users/me/padas/gundi-portal
EOF
```

Bring up the portal explicitly when you want it:

```bash
docker compose --profile portal up -d portal
# or set the env once for the whole shell:
COMPOSE_PROFILES=portal ./dev.sh start
```

Without the profile, `https://portal.127.0.0.1.nip.io` will return 502 from
Caddy — informative, not broken.

The `kong-bootstrap` one-shot service runs after Kong + Keycloak are healthy
and registers the `cdip-web` service, the `cdip-web-route` route, and the
`oidc` plugin via Kong's Admin API. Idempotent — re-run with:

```bash
docker compose run --rm kong-bootstrap
```

## Logging in

Browse to <https://web.127.0.0.1.nip.io/> (accept Caddy's self-signed cert).
You'll be redirected to Keycloak — sign in as `dev` / `dev` (defined in
`keycloak/cdip-dev-realm.json`). After the callback you should land on the
portal home logged in.

## Files

| File | Role |
|---|---|
| `../Caddyfile` | TLS edge. `web.127.0.0.1.nip.io` proxies to `kong:8000` with `X-Forwarded-Proto: https`. |
| `../docker-compose.yml` (`kong` env) | `KONG_TRUSTED_IPS=0.0.0.0/0,::/0`, `KONG_REAL_IP_HEADER=X-Forwarded-For` so kong-oidc honors Caddy's forwarded headers when building the OIDC redirect URI. |
| `../docker-compose.yml` (`keycloak`) | `KC_HOSTNAME_URL=https://keycloak.127.0.0.1.nip.io/auth` (browser-facing); `--import-realm` mounts the dev realm. |
| `../docker-compose.yml` (`kong-bootstrap`) | One-shot init container, runs `bootstrap-kong.sh`. |
| `bootstrap-kong.sh` | Idempotent — upserts service, route, and `oidc` plugin via Admin API. Uses a stable plugin id so PUT acts as upsert. |
| `../keycloak/cdip-dev-realm.json` | Realm `cdip-dev` + clients (`cdip-kong-gateway` confidential, `cdip-admin-portal` legacy) + userinfo mapper for `username ← preferred_username` + test user `dev/dev`. |

## Gotchas (worth knowing before debugging)

1. **`session_secret` must be base64-encoded 32 raw bytes.** kong-oidc uses
   lua-resty-session which decodes it. The bootstrap script hardcodes a fixed
   dev value (`D5+sOKjh/...=`) that contains `+`/`/`/`=` characters, so the
   curls use **`--data-urlencode`** rather than `--data` — the latter would
   form-encode `+` as space and corrupt the secret on Kong's side. Symptom:
   `[oidc] Invalid plugin configuration, session secret could not be decoded`.

2. **`KC_HOSTNAME_URL` is what makes the OIDC discovery doc advertise the
   *public* authorization endpoint** while keeping `token_endpoint` /
   `userinfo_endpoint` on the internal `http://keycloak:8080` URL. That's
   exactly what kong-oidc needs: the browser hits the public URL,
   server-to-server back-channels stay internal. If you only set
   `KC_HOSTNAME_STRICT=false`, all endpoints come back as internal hostnames
   and the browser redirect will go to a name it can't resolve.

3. **kong-oidc caches the OIDC discovery doc.** If you change Keycloak's
   hostname or realm config, **restart Kong** (`docker compose restart kong`)
   to flush the cache. Restarting Keycloak alone won't propagate.

4. **`username` claim on the userinfo response is required.** Django's
   `SimpleUserInfoBackend` reads `user_info.get("username")` — Keycloak's
   default userinfo includes `preferred_username`, *not* `username`. The
   realm export wires up an `oidc-usermodel-property-mapper` on the
   `cdip-kong-gateway` client that copies `username ← user.attribute=username`
   into the userinfo response. Without that mapper, login appears to succeed
   at Keycloak but Django silently fails to authenticate.

5. **`redirect_uri_path` was removed in newer kong-oidc.** The plugin
   auto-builds the redirect URI from the current request. The bootstrap
   script omits this field. Symptom: `400 schema violation
   (config.redirect_uri_path: unknown field)`.

6. **Curl tests through the auth flow can return spurious 403s.** Django's
   CSRF middleware rejects POSTs without a Referer (or with a non-HTTPS one).
   When `curl -L` follows redirects, it preserves the original POST method,
   so the trailing redirect to `/` after the callback ends up as a `POST /`
   without a Referer. In a browser the trailing redirect is a GET and the
   Referer is set, so this is a curl-test artifact, not a real auth bug.
   Confirm a successful login by issuing a fresh GET with the cookie jar.

7. **Kong needs ~5–8 seconds after `restart` before the proxy listener is
   fully ready.** The healthcheck flips to up earlier. Add a short sleep when
   scripting against it.

## Resetting auth state

If anything gets stuck (cached discovery doc, broken session cookie, stale
plugin config), the cheapest reset is:

```bash
docker compose down keycloak keycloak-db
docker volume rm dispatcher-deployments_keycloak_db_data   # forces realm re-import
docker compose up -d keycloak
docker compose restart kong
docker compose run --rm kong-bootstrap
```
