# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Gundi Portal (CDIP Admin Portal) — a Django web application and REST API for managing wildlife conservation data integrations. It provides a web UI and API for configuring integrations, organizations, deployments, and data synchronization between conservation platforms (EarthRanger, SMART, Movebank, etc.).

## Key Commands

### Running Tests
```bash
cd cdip_admin
# Run all tests
pytest

# Run a single test file
pytest integrations/tests/test_models.py

# Run a specific test
pytest integrations/tests/test_models.py::TestClassName::test_method_name

# Run with coverage
pytest --cov=.
```

Tests use `cdip_admin.local_settings` (configured in `pytest.ini`), which requires a `cdip_admin/cdip_admin/local_settings.py` file. The `local_settings_nodb.py` variant uses SQLite and disables GCP/tracing/pubsub for lightweight testing.

### Building Docker Image
```bash
docker build -t cdip-portal:latest -f docker/Dockerfile .
# Or via Make:
make build_and_push
```

### Django Management
```bash
cd cdip_admin
python3 manage.py migrate
python3 manage.py runserver
python3 manage.py collectstatic --no-input
```

### Dependencies
Managed via pip-compile in `dependencies/`:
- `requirements.in` / `requirements.txt` — production deps
- `requirements-dev.in` / `requirements-dev.txt` — dev/test deps

### Pre-commit Hooks
Configured in `.pre-commit-config.yaml`: merge conflict checks, debug statement detection, end-of-file fixer, detect-secrets, and ggshield (GitGuardian).

## Architecture

### Django Apps (under `cdip_admin/`)

- **integrations/** — Core domain. Contains v1 and v2 integration models, views, and admin config.
  - `models/v1/` — Legacy models: `InboundIntegrationType`, `OutboundIntegrationType`, `InboundIntegrationConfiguration`, `OutboundIntegrationConfiguration`, Device/DeviceGroup
  - `models/v2/` — Gundi 2.0 models: `Integration`, `IntegrationType`, `Route`, `Source`, `IntegrationWebhook`
- **api/** — REST API v1 endpoints (DRF)
- **api/v2/** — Gundi 2.0 API endpoints (mounted at `/v2/`)
- **organizations/** — Organization/tenant management
- **accounts/** — User accounts, EULA, profiles
- **deployments/** — Deployment and dispatcher management
- **sync_integrations/** — Celery background tasks for syncing integration data
- **event_consumers/** — Webhook event handling
- **core/** — Shared models, permissions (`core/permissions.py`), caching, tracing utilities
- **activity_log/** — Audit trail via SimpleHistory
- **website/** — Web UI templates (Bootstrap 4)

### API Versioning
- `/api/` — Legacy v1 API
- `/v2/` — Gundi 2.0 API (separate URL namespace)

### Background Processing
Celery with Redis broker. Celery Beat for scheduled tasks (database-backed via django-celery-beat). Task deduplication via celery-once.

### Authentication
OIDC/OAuth via Keycloak (social-auth-app-django). Organization-based access control with Django groups.

### Configuration
Django settings use `django-environ` for environment-based config. Key env vars: database credentials, Keycloak settings, GCP project/pubsub/storage, Kafka/Confluent Cloud config.

### CI/CD
GitHub Actions (`.github/workflows/main.yml`):
- Push to `main` → deploy to dev
- Push to `release-**` → deploy to stage, then prod
- Helm chart deployments to GKE

## Conventions

- Python 3.10+ (3.11 in Docker)
- Django 4.2.x
- Tests alongside app code (e.g., `integrations/tests/`)
- Fixtures in `cdip_admin/conftest.py` (large shared fixture file)
- Sensitive data encrypted via Fernet fields
- Model history tracked via django-simple-history

## Code Comments (Strict)

### Don't

- **No preamble, no summary.** Deliver the code. Skip "Here's the modified version" and "Hope this helps".
- **Don't narrate the past.** How the code used to look, or what you just changed, belongs in the commit message and the PR description — not in the source.
- **Don't comment the obvious.** If the syntax already says it, the comment is noise. `# Get the user's organizations` above `get_user_organizations_qs(user)` is noise.
- **Don't leave a trail of review fixes.** Successive "fixed X", "handle Y too" comments accumulating above one block is a smell. Collapse them into one statement of the current invariant before pushing, or delete them.

### Do

- **Comment only what the code cannot say.** A comment earns its place when it documents a cross-service contract, a non-obvious ordering or performance trade-off, a security constraint, or business logic subtle enough that the next reader would reasonably "fix" it into a bug.
- **Write the *why*, in the present tense**, as a statement about how the system works — not about what you did to it.

### What that means here

The comments worth keeping in this repo are the ones documenting an invariant that spans a
boundary — the v2 API contract, the Pub/Sub event contract with cdip-routing and the action
runners, or the tenant-isolation rules. Two in-repo references for the style:

- `api/v2/serializers.py` — `FIELD_MAPPING_ACTION_TYPES` explains that it derives from every
  stream type the platform routes, not just the ones the portal UI edits, and cites the ticket
  where narrowing it caused a regression.
- `api/v2/serializers.py` — `RouteConfigurationSerializer.validate_data` explains that *presence*
  of the `field_mappings` key, not its truthiness, gates validation, so `null` and `[]` are
  rejected rather than silently passing.

Both describe a rule that stays true tomorrow and that a reasonable person would otherwise
break. That is the bar.

## Testing (Required)

Tests ship with the change. A model, serializer, view, permission or task change is not
complete without its tests in the same commit.

### Conventions

- **pytest**, not `unittest`. `pytest.ini` sets `DJANGO_SETTINGS_MODULE = cdip_admin.local_settings`
  and `--reuse-db`.
- **Tests live beside the app**, in `<app>/tests/` — `api/v2/tests/test_sources_api.py`,
  `integrations/tests/test_models.py`. There is no top-level `tests/` directory.
- **`pytestmark = pytest.mark.django_db`** at module level for anything touching the database.
- **Fixtures go in the shared `cdip_admin/conftest.py`**, which is the single large fixture file
  for the whole project. Plain pytest fixtures creating model instances directly — this repo does
  not use factory_boy.
- **API tests** use `reverse("<basename>-list")` / `reverse("<basename>-detail", kwargs={"pk": ...})`,
  `api_client.force_authenticate(user)`, and `format="json"`. Assert with the response body attached
  so failures are readable: `assert response.status_code == status.HTTP_200_OK, response.content`.
- **Shared assertion bodies** go in a `_test_*` private helper parameterized by user, so the same
  expectations can be reused across superuser / org admin / org viewer.

### Coverage expected

- **Happy path**, and the stored side effect — not just the status code. Assert what landed in the
  database, not only what came back.
- **Invalid input**, as a parametrized table of cases with the expected error fragment. The pattern
  is `INVALID_FIELD_MAPPING_CASES` in `api/v2/tests/test_routes_api.py`.
- **Boundaries** — empty collections, `None`, missing optional fields, values at a configured cap.
- **Permissions, every time an endpoint changes.** Superuser, org admin, org viewer, and a user from
  another organization. Cross-organization access is the highest-risk failure mode in this codebase,
  so an endpoint without a cross-org test is not covered.
- **Idempotency** where a client will re-send what it just read. Writing the value back unchanged
  must not start failing validation.

### Don't

- **Don't let external calls escape.** Patch Pub/Sub publishers, Keycloak, and third-party HTTP.
  `local_settings_nodb.py` disables GCP, tracing and Pub/Sub for lightweight runs; `PUBSUB_ENABLED=False`
  swaps in `NullPublisher`.
- **Don't assert on exact DRF error structures** when a substring will do. Error envelopes shift
  between DRF versions; the message content is the contract.
