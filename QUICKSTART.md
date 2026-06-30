# Local Quickstart

Bring up the full Gundi Portal stack locally — Django app, Kong gateway,
Keycloak (auth), Postgres, Redis, Celery, and Caddy (TLS) — with one command.

## Prerequisites

- **Docker Desktop** running (Docker Compose v2).
- **The Kong gateway repo cloned next to this one** (the Kong image builds from it):

  ```bash
  git clone git@github.com:PADAS/gundi-kp-dynamic-routing.git ../gundi-kp-dynamic-routing
  ```

  Keep the two repos as siblings, or point `KONG_DIR` at wherever you cloned it.
  (No credentials needed — `./dev.sh setup` auto-generates the placeholder
  `application_default_credentials.json` the Kong image expects.)

## Bring it up

```bash
./dev.sh setup
```

One idempotent command. It:

1. generates an `OIDC_SESSION_SECRET` (in `.env`) if missing,
2. builds the images,
3. starts the stack and waits for the core services to be healthy,
4. runs migrations — which also create the `GlobalAdmin` / `OrganizationMember`
   access groups,
5. registers the Kong service/route + `oidc` plugin,
6. seeds the local `dev` user as a Django superuser.

Safe to re-run. For a clean slate, run `./dev.sh clean` first (drops containers
and volumes), then `./dev.sh setup`.

## Sign in

Browse to **<https://web.127.0.0.1.nip.io/>** — accept Caddy's self-signed
certificate (one-time, local CA) — and log in as **`dev` / `dev`**. That account
is a superuser, so you land in the portal with full admin access. This is the
real path: browser → Caddy (TLS) → Kong (auth) → Django.

## Endpoints

| URL | What |
|---|---|
| `https://web.127.0.0.1.nip.io` | Portal, through Caddy + Kong (auth) — **use this** |
| `http://localhost:8888` | Django directly — bypasses Kong/auth, handy for debugging |
| `https://keycloak.127.0.0.1.nip.io/auth` | Keycloak admin console (`admin` / `admin`) |
| `http://localhost:8001` | Kong Admin API |

## Everyday commands

```bash
./dev.sh start | stop | restart | status   # control the stack
./dev.sh logs [service]                     # tail logs
./dev.sh migrate | makemigrations           # database
./dev.sh shell | dbshell                     # Django / psql shell
./dev.sh test [path]                         # run tests
./dev.sh clean                               # stop + remove containers and volumes
```

## Troubleshooting

- **`Cannot connect to the Docker daemon`** — start Docker Desktop, then re-run.
- **`Kong repo not found at ...`** — clone `gundi-kp-dynamic-routing` as a sibling
  (see Prerequisites), or run with `KONG_DIR=/abs/path/to/gundi-kp-dynamic-routing ./dev.sh setup`.
- **Kong build fails on `COPY application_default_credentials.json`** — a fresh
  Kong clone lacks that gitignored file; `./dev.sh setup` generates a local
  placeholder automatically, so just re-run setup.
- **Browser certificate warning** at `web.127.0.0.1.nip.io` — expected; Caddy
  uses a local CA. Accept/proceed (or trust Caddy's root CA to silence it).
- **Re-running `./dev.sh setup`** is always safe — every step is idempotent.

## Running tests

```bash
docker compose run --rm pytest --ds=cdip_admin.settings [path]
```

Pass `--ds=cdip_admin.settings` explicitly — `pytest.ini` points at a
`local_settings` module that isn't present in a fresh checkout.
