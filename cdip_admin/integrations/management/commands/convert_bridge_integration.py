"""Convert a CDIP v1 BridgeIntegration into its Gundi v2 equivalents."""

import json

import requests
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from integrations.models import (
    BridgeIntegration,
    Integration,
    IntegrationConfiguration,
    IntegrationType,
    Route,
    RouteConfiguration,
    WebhookConfiguration,
)


# Configuration keys whose values are credentials. The report redacts these by
# default so a conversion run can be pasted into a ticket; --show-secrets opts
# out. Redaction only ever affects the report, never what is written to the DB.
SECRET_CONFIG_KEYS = frozenset({"token", "password"})
REDACTED = "***"


def er_base_url(er_site):
    """Return the base URL Integration._pre_save stores for an ER site."""
    return f"https://{er_site}/"


def redact(data, show_secrets):
    """Return ``data`` with credential values masked unless ``show_secrets``."""
    if show_secrets or not isinstance(data, dict):
        return data
    return {
        key: (REDACTED if key in SECRET_CONFIG_KEYS and value else value)
        for key, value in data.items()
    }


# Integration type slugs this command depends on. These are database rows, not
# code, so every lookup reports the missing slug rather than raising DoesNotExist.
TYPE_INREACH = "inreach"
TYPE_EARTH_RANGER = "earth_ranger"
TYPE_API_PUSH = "api_push"
TYPE_GENERIC_WEBHOOKS = "generic_webhooks"

WEBHOOK_INREACH = "inreach_webhook"
WEBHOOK_GENERIC_JSON = "generic_json_webhook"

# Stamped into Integration.additional so a repeat run can be detected, and so
# the provenance of a converted integration stays visible in the portal.
MARKER_KEY = "converted_from_bridge_integration"

# ER exposes the authenticated account at this path; the conversion uses it to
# tell whether two different tokens belong to the same ER user.
ER_USER_PATH = "api/v1.0/user/me"
ER_REQUEST_TIMEOUT = 10

# Keys the conversion reads out of BridgeIntegration.additional.
REQUIRED_KEYS = (
    "er_site",
    "er_token",
    "er_source_provider",
    "inreach_url",
    "inreach_username",
    "inreach_password",
    "append_recipients_to_message",
)

# Webhook payload transform for the Everywhere Hub alert feed. The jq filter
# renames Everywhere Hub alert types to ER event types and flattens the payload
# into Gundi's event shape; the schema describes the raw inbound payload.
EVERYWHERE_HUB_JQ_FILTER = """{ "CHECK-IN I'M OK": "ew_check_in_im_ok",
  "CHECK-IN NOT OK": "ew_check_in_not_ok",
  "EMERGENCY ENTERED": "ew_emergency_entered",
  "EMERGENCY EXITED": "ew_emergency_exited",
  "FACTAL NEWS ALERT": "ew_factal_news_alert",
  "GEOFENCE ENTERED": "ew_geofence_entered",
  "GEOFENCE EXITED": "ew_geofence_exited",
  "MISSED CHECK-IN": "ew_missed_check_in",
  "MISSED CHECK-IN ESCALATION": "ew_missed_check_in_escalation",
  "SELF CHECK-IN STARTED": "ew_self_check_in_started",
  "SELF CHECK-IN STOPPED": "ew_self_check_in_stopped"} as $am
| .alertType = (if $am[.alertType] then $am[.alertType] else . end)
| .createTimeMs = (.createTimeMs | floor)
| .location.gpsTimeMs = (.location.gpsTimeMs | floor)
| { source: .deviceName,
  title: .description,
  event_type: .alertType,
  recorded_at: (if (.createTimeMs | tostring | length) == 13 then .createTimeMs | . / 1000 | todate else .createTimeMs | todate end),
  location: { lat: .location.latitudeDegrees, lon: .location.longitudeDegrees },
  event_details: { device_name: .deviceName, device_alias: .deviceAlias, speed_mph: .location.speedMph, course_degrees: .location.courseDegrees, fence_id: .fenceId, gps_time_ms: (if (.location.gpsTimeMs| tostring | length) == 13 then .location.gpsTimeMs|. / 1000 | todate else .location.gpsTimeMs | todate end), conversation_id: 0, processed_message_id: .processedMessageId } }"""

EVERYWHERE_HUB_JSON_SCHEMA = {
    "type": "object",
    "title": "Model",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "properties": {
        "fenceId": {
            "type": "number"
        },
        "location": {
            "type": "object",
            "properties": {
                "speedMph": {
                    "type": "number"
                },
                "gpsTimeMs": {
                    "type": "number"
                },
                "hdopMeters": {
                    "type": "number"
                },
                "vdopMeters": {
                    "type": "number"
                },
                "courseDegrees": {
                    "type": "number"
                },
                "accuracyMeters": {
                    "type": "number"
                },
                "altitudeMeters": {
                    "type": "number"
                },
                "latitudeDegrees": {
                    "type": "number"
                },
                "longitudeDegrees": {
                    "type": "number"
                }
            }
        },
        "alertType": {
            "type": "string"
        },
        "deviceName": {
            "type": "string"
        },
        "description": {
            "type": "string"
        },
        "deviceAlias": {
            "type": "string"
        },
        "createTimeMs": {
            "type": "number"
        },
        "processedMessageId": {
            "type": "number"
        }
    }
}

EVERYWHERE_HUB_WEBHOOK_CONFIG = {
    "jq_filter": EVERYWHERE_HUB_JQ_FILTER,
    "json_schema": EVERYWHERE_HUB_JSON_SCHEMA,
    "output_type": "ev",
    "diagnostic_destination_url": "",
}


class Command(BaseCommand):
    help = "Convert a v1 BridgeIntegration into Gundi v2 integrations and routes."

    def add_arguments(self, parser):
        parser.add_argument(
            "bridge_integration_id",
            type=str,
            help="ID of the BridgeIntegration to convert.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help=(
                "Convert again even if this BridgeIntegration has already been "
                "converted. Creates a second, independent set of objects."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be created, then roll it all back.",
        )
        parser.add_argument(
            "--er-integration",
            type=str,
            help=(
                "Reuse this EarthRanger integration by ID instead of searching "
                "for one. Skips the credential check, so the caller takes "
                "responsibility for the destination being the right one."
            ),
        )
        parser.add_argument(
            "--no-reuse-er",
            action="store_true",
            help=(
                "Always create a new EarthRanger destination, even when one "
                "already exists for this site."
            ),
        )
        parser.add_argument(
            "--show-secrets",
            action="store_true",
            help=(
                "Print credentials verbatim in the JSON output instead of "
                "redacting them."
            ),
        )

    def handle(self, *args, **options):
        self.created_integrations = []
        self.created_routes = []
        self.created_route_configurations = []
        self.reused_integrations = []

        bridge = self._load_bridge(options["bridge_integration_id"])
        additional = bridge.additional or {}
        self._check_required_keys(additional)
        types = self._load_types()
        if not options["force"]:
            self._check_not_already_converted(bridge)

        # Finding and verifying the ER destination is read-only and may make
        # network calls, so it happens before the transaction opens: no reason
        # to hold a write transaction open across an HTTP timeout.
        reusable_er = self._find_reusable_earth_ranger(bridge, additional, options)

        dry_run = options["dry_run"]
        with transaction.atomic():
            report = self._convert(bridge, additional, types, options, reusable_er)
            if dry_run:
                # Roll back the whole conversion: the report above describes
                # what would have been written. Celery work scheduled through
                # transaction.on_commit never fires on a rolled-back block.
                transaction.set_rollback(True)

        self.stderr.write(
            f"{'Would convert' if dry_run else 'Converted'} BridgeIntegration "
            f"'{bridge.name}': {len(self.created_integrations)} integrations, "
            f"{len(self.created_routes)} routes."
        )
        self.stdout.write(json.dumps(report, indent=2))

    def _convert(self, bridge, additional, types, options, reusable_er):
        inreach = self._create_inreach(bridge, additional, types[TYPE_INREACH])
        earth_ranger = reusable_er or self._create_earth_ranger(
            bridge, additional, types[TYPE_EARTH_RANGER]
        )
        api_push = self._create_api_push(bridge, additional, types[TYPE_API_PUSH])
        webhook_provider = self._create_webhook_provider(
            bridge, types[TYPE_GENERIC_WEBHOOKS]
        )

        self._create_route(
            bridge,
            provider=inreach,
            destination=earth_ranger,
            configuration=self._provider_key_configuration(
                inreach, earth_ranger, additional["er_source_provider"]
            ),
        )
        self._create_route(bridge, provider=api_push, destination=inreach)
        self._create_route(
            bridge, provider=webhook_provider, destination=earth_ranger
        )

        return self._build_report(bridge, show_secrets=options["show_secrets"])

    # --- Integration builders --------------------------------------------

    def _create_inreach(self, bridge, additional, integration_type):
        integration = self._new_integration(
            bridge,
            integration_type=integration_type,
            name=bridge.name,
            base_url=additional["inreach_url"],
        )
        self._set_action_config(
            integration,
            "auth",
            {
                "api_url": additional["inreach_url"],
                "username": additional["inreach_username"],
                "password": additional["inreach_password"],
            },
        )
        # append_recipients_to_message has no field in the v2 PushMessageConfig
        # schema; it is carried here as the nearest home so the setting is not
        # lost, but nothing reads it today.
        self._set_action_config(
            integration,
            "push_messages",
            {
                "append_recipients_to_message": additional[
                    "append_recipients_to_message"
                ]
            },
        )
        self._create_webhook_config(
            integration,
            WEBHOOK_INREACH,
            {"include_messages": True, "include_observations": True},
        )
        return integration

    def _create_earth_ranger(self, bridge, additional, integration_type):
        integration = self._new_integration(
            bridge,
            integration_type=integration_type,
            name=additional["er_site"],
            base_url=er_base_url(additional["er_site"]),
        )
        self._set_action_config(
            integration,
            "auth",
            {"authentication_type": "token", "token": additional["er_token"]},
        )
        return integration

    # --- EarthRanger reuse ------------------------------------------------

    def _find_reusable_earth_ranger(self, bridge, additional, options):
        """Return an existing ER destination to reuse, or None to create one.

        Read-only: raises rather than reusing anything it cannot vouch for.
        """
        if options["no_reuse_er"]:
            return None

        if options["er_integration"]:
            existing = self._load_named_er_integration(options["er_integration"])
            self._check_reusable(existing, bridge)
            self.stderr.write(
                f"Reusing EarthRanger integration {existing.id} as instructed; "
                "credential verification skipped."
            )
            self.reused_integrations.append(existing)
            return existing

        candidates = list(
            Integration.objects.filter(
                type__value=TYPE_EARTH_RANGER,
                base_url__iexact=er_base_url(additional["er_site"]),
            )
        )
        if not candidates:
            return None
        if len(candidates) > 1:
            described = ", ".join(
                f"{i.name} ({i.id}, owner {i.owner.name})" for i in candidates
            )
            raise CommandError(
                f"{len(candidates)} EarthRanger integrations already exist for "
                f"'{additional['er_site']}': {described}. Pass --er-integration "
                "<uuid> to choose one, or --no-reuse-er to create another."
            )

        existing = candidates[0]
        self._check_reusable(existing, bridge)
        self._check_same_er_user(existing, additional)
        self.stderr.write(f"Reusing EarthRanger integration {existing.id}.")
        self.reused_integrations.append(existing)
        return existing

    def _load_named_er_integration(self, integration_id):
        integration = Integration.objects.filter(
            id=integration_id, type__value=TYPE_EARTH_RANGER
        ).first()
        if integration is None:
            raise CommandError(
                f"EarthRanger integration '{integration_id}' not found."
            )
        return integration

    def _check_reusable(self, existing, bridge):
        """Structural checks on a candidate ER destination. No network."""
        if not existing.enabled:
            raise CommandError(
                f"EarthRanger integration {existing.id} is disabled; refusing "
                "to route to it. Enable it, or pass --no-reuse-er."
            )
        if existing.owner_id != bridge.owner_id:
            raise CommandError(
                f"EarthRanger integration {existing.id} is owned by "
                f"'{existing.owner.name}', but the BridgeIntegration is owned by "
                f"'{bridge.owner.name}'. Pass --no-reuse-er to create a separate "
                "destination."
            )
        auth = existing.configurations.filter(action__value="auth").first()
        if auth is None or not auth.data:
            raise CommandError(
                f"EarthRanger integration {existing.id} has no auth "
                "configuration; refusing to route to it."
            )
        configured = set(
            existing.configurations.values_list("action__value", flat=True)
        )
        missing = {"push_observations", "push_events"} - configured
        if missing:
            raise CommandError(
                f"EarthRanger integration {existing.id} is missing "
                f"configuration for: {', '.join(sorted(missing))}. Run "
                "repair_integration_configurations, or pass --no-reuse-er."
            )

    def _check_same_er_user(self, existing, additional):
        """Confirm the candidate authenticates as the same ER user as the bridge."""
        auth = existing.configurations.get(action__value="auth").data
        bridge_token = additional["er_token"]
        uses_token = auth.get("authentication_type") == "token"

        if uses_token and auth.get("token") == bridge_token:
            # Same credential, so the permissions are identical by definition.
            return

        er_site = additional["er_site"]
        bridge_user = self._er_username(er_site, bridge_token)
        if uses_token:
            existing_user = self._er_username(er_site, auth.get("token"))
        else:
            existing_user = auth.get("username")

        if bridge_user != existing_user:
            raise CommandError(
                f"EarthRanger integration {existing.id} authenticates as "
                f"'{existing_user}', but the BridgeIntegration's token belongs "
                f"to '{bridge_user}'. Their permissions may differ. Pass "
                f"--er-integration {existing.id} to reuse it anyway, or "
                "--no-reuse-er to create a separate destination."
            )

    def _er_username(self, er_site, token):
        url = f"{er_base_url(er_site)}{ER_USER_PATH}"
        try:
            response = requests.get(
                url,
                headers={"Authorization": f"Bearer {token}"},
                timeout=ER_REQUEST_TIMEOUT,
            )
        except requests.RequestException as exc:
            raise CommandError(
                f"Could not verify ER credentials against {url}: "
                f"{exc.__class__.__name__}."
            )
        if response.status_code != 200:
            raise CommandError(
                f"Could not verify ER credentials against {url}: "
                f"HTTP {response.status_code}."
            )
        try:
            return response.json()["data"]["username"]
        except (ValueError, TypeError, KeyError):
            raise CommandError(
                f"Could not verify ER credentials against {url}: response had "
                "no 'data.username'."
            )

    def _create_api_push(self, bridge, additional, integration_type):
        return self._new_integration(
            bridge,
            integration_type=integration_type,
            name=f"ER Messages from {additional['er_site']}",
        )

    def _create_webhook_provider(self, bridge, integration_type):
        integration = self._new_integration(
            bridge,
            integration_type=integration_type,
            name="Everywhere Hub Alerts",
        )
        self._create_webhook_config(
            integration, WEBHOOK_GENERIC_JSON, EVERYWHERE_HUB_WEBHOOK_CONFIG
        )
        return integration

    # --- Routes -----------------------------------------------------------

    def _create_route(self, bridge, provider, destination, configuration=None):
        route = Route.objects.create(
            name=f"{provider.name} to {destination.name}"[:200],
            owner=bridge.owner,
            configuration=configuration,
        )
        route.data_providers.add(provider)
        route.destinations.add(destination)
        self.created_routes.append(route)
        return route

    def _provider_key_configuration(self, provider, destination, provider_key):
        # Reproduces the v1 bridge's er_source_provider: every observation this
        # provider sends to this destination is stamped with the same
        # provider_key. Shape per api/v2/serializers.py field-mapping schema.
        configuration = RouteConfiguration.objects.create(
            name=f"Provider key for {provider.name}"[:200],
            data={
                "field_mappings": {
                    str(provider.id): {
                        "obv": {
                            str(destination.id): {
                                "destination_field": "provider_key",
                                "default": provider_key,
                            }
                        }
                    }
                }
            },
        )
        self.created_route_configurations.append(configuration)
        return configuration

    # --- Report -----------------------------------------------------------

    def _build_report(self, bridge, show_secrets):
        integrations = self.created_integrations
        configurations = IntegrationConfiguration.objects.filter(
            integration__in=integrations
        ).order_by("integration__name", "action__value")
        webhook_configurations = WebhookConfiguration.objects.filter(
            integration__in=integrations
        ).order_by("integration__name")

        return {
            "bridge_integration": {
                "id": str(bridge.id),
                "name": bridge.name,
                "owner": str(bridge.owner_id),
            },
            "created": {
                "integrations": [
                    {
                        "id": str(i.id),
                        "name": i.name,
                        "type": i.type.value,
                        "base_url": i.base_url,
                        "owner": str(i.owner_id),
                    }
                    for i in integrations
                ],
                "integration_configurations": [
                    {
                        "id": str(c.id),
                        "integration": str(c.integration_id),
                        "action": c.action.value,
                        "data": redact(c.data, show_secrets),
                    }
                    for c in configurations
                ],
                "webhook_configurations": [
                    {
                        "id": str(w.id),
                        "integration": str(w.integration_id),
                        "webhook": w.webhook.value,
                        "data": redact(w.data, show_secrets),
                    }
                    for w in webhook_configurations
                ],
                "route_configurations": [
                    {"id": str(rc.id), "name": rc.name, "data": rc.data}
                    for rc in self.created_route_configurations
                ],
                "routes": [
                    {
                        "id": str(r.id),
                        "name": r.name,
                        "data_providers": [str(p.id) for p in r.data_providers.all()],
                        "destinations": [str(d.id) for d in r.destinations.all()],
                        "configuration": (
                            str(r.configuration_id) if r.configuration_id else None
                        ),
                    }
                    for r in self.created_routes
                ],
            },
            "reused": {
                "integrations": [
                    {
                        "id": str(i.id),
                        "name": i.name,
                        "type": i.type.value,
                        "base_url": i.base_url,
                        "owner": str(i.owner_id),
                    }
                    for i in self.reused_integrations
                ],
            },
        }

    # --- Helpers ----------------------------------------------------------

    def _new_integration(self, bridge, integration_type, name, base_url=""):
        integration = Integration.objects.create(
            type=integration_type,
            owner=bridge.owner,
            name=name,
            base_url=base_url,
            # The marker is what the re-run guard looks for, and what tells an
            # operator later where this integration came from.
            additional={MARKER_KEY: str(bridge.id)},
        )
        # Matches what the v2 API does on create (api/v2/serializers.py): every
        # action of the type gets a configuration row, empty until populated.
        integration.create_missing_configurations()
        self.created_integrations.append(integration)
        return integration

    def _set_action_config(self, integration, action_value, data):
        config = integration.configurations.filter(
            action__value=action_value
        ).first()
        if config is None:
            raise CommandError(
                f"IntegrationType '{integration.type.value}' has no "
                f"'{action_value}' action in this database."
            )
        config.data = data
        config.save()
        return config

    def _create_webhook_config(self, integration, webhook_value, data):
        webhook = getattr(integration.type, "webhook", None)
        if webhook is None or webhook.value != webhook_value:
            raise CommandError(
                f"IntegrationType '{integration.type.value}' has no "
                f"'{webhook_value}' webhook in this database."
            )
        return WebhookConfiguration.objects.create(
            integration=integration, webhook=webhook, data=data
        )

    def _check_required_keys(self, additional):
        missing = [key for key in REQUIRED_KEYS if key not in additional]
        if missing:
            raise CommandError(
                "BridgeIntegration.additional is missing required key(s): "
                f"{', '.join(missing)}."
            )

    def _check_not_already_converted(self, bridge):
        existing = Integration.objects.filter(
            **{f"additional__{MARKER_KEY}": str(bridge.id)}
        )
        if existing.exists():
            described = ", ".join(
                f"{i.name} ({i.type.value}, {i.id})" for i in existing
            )
            raise CommandError(
                f"BridgeIntegration '{bridge.id}' has already been converted. "
                f"Existing integrations: {described}. "
                "Pass --force to create a second, independent set."
            )

    def _load_bridge(self, bridge_integration_id):
        try:
            return BridgeIntegration.objects.get(id=bridge_integration_id)
        except (BridgeIntegration.DoesNotExist, ValidationError, ValueError):
            raise CommandError(
                f"BridgeIntegration '{bridge_integration_id}' not found."
            )

    def _load_types(self):
        slugs = [
            TYPE_INREACH,
            TYPE_EARTH_RANGER,
            TYPE_API_PUSH,
            TYPE_GENERIC_WEBHOOKS,
        ]
        types = {
            it.value: it
            for it in IntegrationType.objects.filter(value__in=slugs)
        }
        missing = [slug for slug in slugs if slug not in types]
        if missing:
            raise CommandError(
                "Missing IntegrationType(s) in this database: "
                f"{', '.join(missing)}."
            )
        return types
