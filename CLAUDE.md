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
