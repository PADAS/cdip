import json
import logging
import django
from event_consumers.settings import logging_settings

logging_settings.init()
django.setup()  # To use the django ORM
from google.cloud import pubsub_v1
from django.conf import settings
from gundi_core import events as system_events
from integrations.models import GundiTrace, Integration
from activity_log.models import ActivityLog


logger = logging.getLogger(__name__)


def _clean_event_title(title: str) -> str:
    title = title.strip()
    return title if len(title) < 200 else f"{title[:197]}..."


def handle_integration_action_started_event(event_dict: dict):
    event = system_events.IntegrationActionStarted.parse_obj(event_dict)
    event_data = event.payload
    action_id = event_data.action_id
    integration_id = event_data.integration_id
    integration = Integration.objects.get(id=integration_id)
    message = f"Action '{action_id}' started for integration {integration.name}."
    logger.info(message, extra={"event": event_dict})
    ActivityLog.objects.create(
        log_level=ActivityLog.LogLevels.INFO,
        log_type=ActivityLog.LogTypes.EVENT,
        origin=ActivityLog.Origin.INTEGRATION,
        integration=integration,
        value="integration_action_started",
        title=_clean_event_title(message),
        details=event_dict["payload"],
        is_reversible=False,
    )


def handle_integration_action_complete_event(event_dict: dict):
    event = system_events.IntegrationActionComplete.parse_obj(event_dict)
    event_data = event.payload
    action_id = event_data.action_id
    integration_id = event_data.integration_id
    integration = Integration.objects.get(id=integration_id)
    message = f"Action '{action_id}' completed."
    logger.info(message, extra={"event": event_dict})
    ActivityLog.objects.create(
        log_level=ActivityLog.LogLevels.INFO,
        log_type=ActivityLog.LogTypes.EVENT,
        origin=ActivityLog.Origin.INTEGRATION,
        integration=integration,
        value="integration_action_complete",
        title=_clean_event_title(message),
        details=event_dict["payload"],
        is_reversible=False,
    )


def handle_integration_action_failed_event(event_dict: dict):
    event = system_events.IntegrationActionFailed.parse_obj(event_dict)
    event_data = event.payload
    action_id = event_data.action_id
    integration_id = event_data.integration_id
    integration = Integration.objects.get(id=integration_id)
    error = event_dict["payload"].get("error", "No details.")
    message = f"Error running action '{action_id}': {error}"
    logger.info(message, extra={"event": event_dict})
    ActivityLog.objects.create(
        log_level=ActivityLog.LogLevels.ERROR,
        log_type=ActivityLog.LogTypes.EVENT,
        origin=ActivityLog.Origin.INTEGRATION,
        integration=integration,
        value="integration_action_failed",
        title=_clean_event_title(message),
        details=event_dict["payload"],
        is_reversible=False,
    )


def handle_integration_action_custom_log_event(event_dict: dict):
    event = system_events.IntegrationActionCustomLog.parse_obj(event_dict)
    custom_log = event.payload
    integration_id = custom_log.integration_id
    integration = Integration.objects.get(id=integration_id)
    message = f"Custom Log: {custom_log.title}."
    logger.info(message, extra={"event": event_dict})
    ActivityLog.objects.create(
        log_level=custom_log.level,
        log_type=ActivityLog.LogTypes.EVENT,
        origin=ActivityLog.Origin.INTEGRATION,
        integration=integration,
        value="integration_custom_log",
        title=_clean_event_title(custom_log.title),
        details=event_dict["payload"],
        is_reversible=False,
    )


def handle_integration_webhook_started_event(event_dict: dict):
    event = system_events.IntegrationWebhookStarted.parse_obj(event_dict)
    event_data = event.payload
    integration_id = event_data.integration_id
    integration = Integration.objects.get(id=integration_id)
    message = f"Webhook request received."
    logger.info(message, extra={"event": event_dict})
    ActivityLog.objects.create(
        log_level=ActivityLog.LogLevels.INFO,
        log_type=ActivityLog.LogTypes.EVENT,
        origin=ActivityLog.Origin.INTEGRATION,
        integration=integration,
        value="integration_webhook_started",
        title=_clean_event_title(message),
        details=event_dict["payload"],
        is_reversible=False,
    )


def handle_integration_webhook_complete_event(event_dict: dict):
    event = system_events.IntegrationWebhookComplete.parse_obj(event_dict)
    event_data = event.payload
    integration_id = event_data.integration_id
    integration = Integration.objects.get(id=integration_id)
    message = f"Webhook request processing complete."
    logger.info(message, extra={"event": event_dict})
    ActivityLog.objects.create(
        log_level=ActivityLog.LogLevels.INFO,
        log_type=ActivityLog.LogTypes.EVENT,
        origin=ActivityLog.Origin.INTEGRATION,
        integration=integration,
        value="integration_webhook_complete",
        title=_clean_event_title(message),
        details=event_dict["payload"],
        is_reversible=False,
    )


def handle_integration_webhook_failed_event(event_dict: dict):
    event = system_events.IntegrationWebhookFailed.parse_obj(event_dict)
    event_data = event.payload
    integration_id = event_data.integration_id
    integration = Integration.objects.get(id=integration_id) if integration_id else None
    error = event_dict["payload"].get("error", "No details.")
    logger.info(error, extra={"event": event_dict})
    ActivityLog.objects.create(
        log_level=ActivityLog.LogLevels.ERROR,
        log_type=ActivityLog.LogTypes.EVENT,
        origin=ActivityLog.Origin.INTEGRATION,
        integration=integration,
        value="integration_webhook_failed",
        title=_clean_event_title(error),
        details=event_dict["payload"],
        is_reversible=False,
    )


def handle_integration_webhook_custom_log_event(event_dict: dict):
    event = system_events.IntegrationWebhookCustomLog.parse_obj(event_dict)
    custom_log = event.payload
    integration_id = custom_log.integration_id
    integration = Integration.objects.get(id=integration_id) if integration_id else None
    message = f"Webhook Custom Log: {custom_log.title}."
    logger.info(message, extra={"event": event_dict})
    ActivityLog.objects.create(
        log_level=custom_log.level,
        log_type=ActivityLog.LogTypes.EVENT,
        origin=ActivityLog.Origin.INTEGRATION,
        integration=integration,
        value="integration_webhook_custom_log",
        title=_clean_event_title(custom_log.title),
        details=event_dict["payload"],
        is_reversible=False,
    )


# IntegrationWebhookStarted {"asctime": "2024-06-24 14:22:01,459", "levelname": "DEBUG", "processName": "MainProcess", "thread": 132979787536128, "name": "__main__", "message": "Event Details", "event": {"event_id": "7782da01-f59b-425c-aea8-d46065b9d149", "timestamp": "2024-06-24 14:21:58.205638+00:00", "schema_version": "v1", "payload": {"integration_id": "ed8ed116-efb4-4fb1-9d68-0ecc4b0996a1", "webhook_id": "onyesha_wh_webhook", "config_data": {"json_schema": {"type": "object", "properties": {"received_at": {"type": "string", "format": "date-time"}, "end_device_ids": {"type": "object", "properties": {"dev_eui": {"type": "string"}, "dev_addr": {"type": "string"}, "device_id": {"type": "string"}, "application_ids": {"type": "object", "properties": {"application_id": {"type": "string"}}, "additionalProperties": false}}, "additionalProperties": false}, "uplink_message": {"type": "object", "properties": {"f_cnt": {"type": "integer"}, "f_port": {"type": "integer"}, "settings": {"type": "object", "properties": {"time": {"type": "string", "format": "date-time"}, "data_rate": {"type": "object", "properties": {"lora": {"type": "object", "properties": {"bandwidth": {"type": "integer"}, "coding_rate": {"type": "string"}, "spreading_factor": {"type": "integer"}}, "additionalProperties": false}}, "additionalProperties": false}, "frequency": {"type": "string"}, "timestamp": {"type": "integer"}}, "additionalProperties": false}, "locations": {"type": "object", "properties": {"frm-payload": {"type": "object", "properties": {"source": {"type": "string"}, "latitude": {"type": "number"}, "longitude": {"type": "number"}}, "additionalProperties": false}}, "additionalProperties": false}, "frm_payload": {"type": "string"}, "network_ids": {"type": "object", "properties": {"ns_id": {"type": "string"}, "net_id": {"type": "string"}, "tenant_id": {"type": "string"}, "cluster_id": {"type": "string"}, "tenant_address": {"type": "string"}, "cluster_address": {"type": "string"}}, "additionalProperties": false}, "received_at": {"type": "string", "format": "date-time"}, "rx_metadata": {"type": "array", "items": {"type": "object", "properties": {"snr": {"type": "number"}, "rssi": {"type": "integer"}, "time": {"type": "string", "format": "date-time"}, "gps_time": {"type": "string", "format": "date-time"}, "timestamp": {"type": "integer"}, "gateway_ids": {"type": "object", "properties": {"eui": {"type": "string"}, "gateway_id": {"type": "string"}}, "additionalProperties": false}, "received_at": {"type": "string", "format": "date-time"}, "channel_rssi": {"type": "integer"}, "uplink_token": {"type": "string"}, "channel_index": {"type": "integer"}}, "additionalProperties": false}}, "decoded_payload": {"type": "object", "properties": {"gps": {"type": "string"}, "latitude": {"type": "number"}, "longitude": {"type": "number"}, "batterypercent": {"type": "integer"}}, "additionalProperties": false}, "consumed_airtime": {"type": "string"}}, "additionalProperties": false}, "correlation_ids": {"type": "array", "items": {"type": "string"}}}, "additionalProperties": false}, "jq_filter": "{     \"source\": .end_device_ids.device_id,     \"source_name\": .end_device_ids.device_id,     \"type\": .uplink_message.locations.\"frm-payload\".source,     \"recorded_at\": .uplink_message.settings.time,     \"location\": {       \"lat\": .uplink_message.locations.\"frm-payload\".latitude,       \"lon\": .uplink_message.locations.\"frm-payload\".longitude     },     \"additional\": {       \"application_id\": .end_device_ids.application_ids.application_id,       \"dev_eui\": .end_device_ids.dev_eui,       \"dev_addr\": .end_device_ids.dev_addr,       \"batterypercent\": .uplink_message.decoded_payload.batterypercent,       \"gps\": .uplink_message.decoded_payload.gps     }   }", "output_type": "obv"}}, "event_type": "IntegrationWebhookStarted"}}
# IntegrationWebhookComplete {"asctime": "2024-06-24 14:34:05,949", "levelname": "DEBUG", "processName": "MainProcess", "thread": 132979292628736, "name": "__main__", "message": "Event Details", "event": {"event_id": "53d3ba77-dd8f-428a-b202-f7609ff71f68", "timestamp": "2024-06-24 14:34:02.890406+00:00", "schema_version": "v1", "payload": {"integration_id": "ed8ed116-efb4-4fb1-9d68-0ecc4b0996a1", "webhook_id": "onyesha_wh_webhook", "config_data": {"json_schema": {"type": "object", "properties": {"received_at": {"type": "string", "format": "date-time"}, "end_device_ids": {"type": "object", "properties": {"dev_eui": {"type": "string"}, "dev_addr": {"type": "string"}, "device_id": {"type": "string"}, "application_ids": {"type": "object", "properties": {"application_id": {"type": "string"}}, "additionalProperties": false}}, "additionalProperties": false}, "uplink_message": {"type": "object", "properties": {"f_cnt": {"type": "integer"}, "f_port": {"type": "integer"}, "settings": {"type": "object", "properties": {"time": {"type": "string", "format": "date-time"}, "data_rate": {"type": "object", "properties": {"lora": {"type": "object", "properties": {"bandwidth": {"type": "integer"}, "coding_rate": {"type": "string"}, "spreading_factor": {"type": "integer"}}, "additionalProperties": false}}, "additionalProperties": false}, "frequency": {"type": "string"}, "timestamp": {"type": "integer"}}, "additionalProperties": false}, "locations": {"type": "object", "properties": {"frm-payload": {"type": "object", "properties": {"source": {"type": "string"}, "latitude": {"type": "number"}, "longitude": {"type": "number"}}, "additionalProperties": false}}, "additionalProperties": false}, "frm_payload": {"type": "string"}, "network_ids": {"type": "object", "properties": {"ns_id": {"type": "string"}, "net_id": {"type": "string"}, "tenant_id": {"type": "string"}, "cluster_id": {"type": "string"}, "tenant_address": {"type": "string"}, "cluster_address": {"type": "string"}}, "additionalProperties": false}, "received_at": {"type": "string", "format": "date-time"}, "rx_metadata": {"type": "array", "items": {"type": "object", "properties": {"snr": {"type": "number"}, "rssi": {"type": "integer"}, "time": {"type": "string", "format": "date-time"}, "gps_time": {"type": "string", "format": "date-time"}, "timestamp": {"type": "integer"}, "gateway_ids": {"type": "object", "properties": {"eui": {"type": "string"}, "gateway_id": {"type": "string"}}, "additionalProperties": false}, "received_at": {"type": "string", "format": "date-time"}, "channel_rssi": {"type": "integer"}, "uplink_token": {"type": "string"}, "channel_index": {"type": "integer"}}, "additionalProperties": false}}, "decoded_payload": {"type": "object", "properties": {"gps": {"type": "string"}, "latitude": {"type": "number"}, "longitude": {"type": "number"}, "batterypercent": {"type": "integer"}}, "additionalProperties": false}, "consumed_airtime": {"type": "string"}}, "additionalProperties": false}, "correlation_ids": {"type": "array", "items": {"type": "string"}}}, "additionalProperties": false}, "jq_filter": "{     \"source\": .end_device_ids.device_id,     \"source_name\": .end_device_ids.device_id,     \"type\": .uplink_message.locations.\"frm-payload\".source,     \"recorded_at\": .uplink_message.settings.time,     \"location\": {       \"lat\": .uplink_message.locations.\"frm-payload\".latitude,       \"lon\": .uplink_message.locations.\"frm-payload\".longitude     },     \"additional\": {       \"application_id\": .end_device_ids.application_ids.application_id,       \"dev_eui\": .end_device_ids.dev_eui,       \"dev_addr\": .end_device_ids.dev_addr,       \"batterypercent\": .uplink_message.decoded_payload.batterypercent,       \"gps\": .uplink_message.decoded_payload.gps     }   }", "output_type": "obv"}, "result": {"data_points_qty": 1}}, "event_type": "IntegrationWebhookComplete"}}
# IntegrationWebhookFailed {"asctime": "2024-06-24 14:22:27,594", "levelname": "DEBUG", "processName": "MainProcess", "thread": 132979787536128, "name": "__main__", "message": "Event Details", "event": {"event_id": "272a44d2-9867-43a0-8950-de31df36fa26", "timestamp": "2024-06-24 14:22:24.399021+00:00", "schema_version": "v1", "payload": {"integration_id": "ed8ed116-efb4-4fb1-9d68-0ecc4b0996a1", "webhook_id": "onyesha_wh_webhook", "config_data": {"json_schema": {"type": "object", "properties": {"received_at": {"type": "string", "format": "date-time"}, "end_device_ids": {"type": "object", "properties": {"dev_eui": {"type": "string"}, "dev_addr": {"type": "string"}, "device_id": {"type": "string"}, "application_ids": {"type": "object", "properties": {"application_id": {"type": "string"}}, "additionalProperties": false}}, "additionalProperties": false}, "uplink_message": {"type": "object", "properties": {"f_cnt": {"type": "integer"}, "f_port": {"type": "integer"}, "settings": {"type": "object", "properties": {"time": {"type": "string", "format": "date-time"}, "data_rate": {"type": "object", "properties": {"lora": {"type": "object", "properties": {"bandwidth": {"type": "integer"}, "coding_rate": {"type": "string"}, "spreading_factor": {"type": "integer"}}, "additionalProperties": false}}, "additionalProperties": false}, "frequency": {"type": "string"}, "timestamp": {"type": "integer"}}, "additionalProperties": false}, "locations": {"type": "object", "properties": {"frm-payload": {"type": "object", "properties": {"source": {"type": "string"}, "latitude": {"type": "number"}, "longitude": {"type": "number"}}, "additionalProperties": false}}, "additionalProperties": false}, "frm_payload": {"type": "string"}, "network_ids": {"type": "object", "properties": {"ns_id": {"type": "string"}, "net_id": {"type": "string"}, "tenant_id": {"type": "string"}, "cluster_id": {"type": "string"}, "tenant_address": {"type": "string"}, "cluster_address": {"type": "string"}}, "additionalProperties": false}, "received_at": {"type": "string", "format": "date-time"}, "rx_metadata": {"type": "array", "items": {"type": "object", "properties": {"snr": {"type": "number"}, "rssi": {"type": "integer"}, "time": {"type": "string", "format": "date-time"}, "gps_time": {"type": "string", "format": "date-time"}, "timestamp": {"type": "integer"}, "gateway_ids": {"type": "object", "properties": {"eui": {"type": "string"}, "gateway_id": {"type": "string"}}, "additionalProperties": false}, "received_at": {"type": "string", "format": "date-time"}, "channel_rssi": {"type": "integer"}, "uplink_token": {"type": "string"}, "channel_index": {"type": "integer"}}, "additionalProperties": false}}, "decoded_payload": {"type": "object", "properties": {"gps": {"type": "string"}, "latitude": {"type": "number"}, "longitude": {"type": "number"}, "batterypercent": {"type": "integer"}}, "additionalProperties": false}, "consumed_airtime": {"type": "string"}}, "additionalProperties": false}, "correlation_ids": {"type": "array", "items": {"type": "string"}}}, "additionalProperties": false}, "jq_filter": "{     \"source\": .end_device_ids.device_id,     \"source_name\": .end_device_ids.device_id,     \"type\": .uplink_message.locations.\"frm-payload\".source,     \"recorded_at\": .uplink_message.settings.time,     \"location\": {       \"lat\": .uplink_message.locations.\"frm-payload\".latitude,       \"lon\": .uplink_message.locations.\"frm-payload\".longitude     },     \"additional\": {       \"application_id\": .end_device_ids.application_ids.application_id,       \"dev_eui\": .end_device_ids.dev_eui,       \"dev_addr\": .end_device_ids.dev_addr,       \"batterypercent\": .uplink_message.decoded_payload.batterypercent,       \"gps\": .uplink_message.decoded_payload.gps     }   }", "output_type": "obv"}, "error": "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: self signed certificate (_ssl.c:1007)"}, "event_type": "IntegrationWebhookFailed"}}
# IntegrationWebhookCustomLog {"asctime": "2024-06-24 15:11:47,772", "levelname": "DEBUG", "processName": "MainProcess", "thread": 132979275843328, "name": "__main__", "message": "Event Details", "event": {"event_id": "a0b73b33-0e2e-457d-b650-49adaa7f593d", "timestamp": "2024-06-24 15:11:46.366931+00:00", "schema_version": "v1", "payload": {"integration_id": "ed8ed116-efb4-4fb1-9d68-0ecc4b0996a1", "webhook_id": "webhook", "config_data": {}, "title": "Webhook data transformed successfully", "level": 10, "data": {"transformed_data": [{"source": "test-webhooks-mm", "source_name": "test-webhooks-mm", "type": "SOURCE_GPS", "recorded_at": "2024-06-07T15:08:19.841Z", "location": {"lat": -2.3828796, "lon": 37.338060999999996}, "additional": {"application_id": "lt10-globalsat", "dev_eui": "70B3D57ED80027EF", "dev_addr": "27027D02", "batterypercent": 100, "gps": "3D fix"}}]}}, "event_type": "IntegrationWebhookCustomLog"}}

event_handlers = {
    "IntegrationActionStarted": handle_integration_action_started_event,
    "IntegrationActionComplete": handle_integration_action_complete_event,
    "IntegrationActionFailed": handle_integration_action_failed_event,
    "IntegrationActionCustomLog": handle_integration_action_custom_log_event,
    "IntegrationWebhookStarted": handle_integration_webhook_started_event,
    "IntegrationWebhookComplete": handle_integration_webhook_complete_event,
    "IntegrationWebhookFailed": handle_integration_webhook_failed_event,
    "IntegrationWebhookCustomLog": handle_integration_webhook_custom_log_event,
}


def process_event(message: pubsub_v1.subscriber.message.Message) -> None:
    try:
        logger.info(f"Received Integration Event {message}.")
        event_dict = json.loads(message.data)
        logger.debug(f"Event Details", extra={"event": event_dict})
        event_type = event_dict.get("event_type")
        schema_version = event_dict.get("schema_version")
        if schema_version != "v1":
            logger.warning(
                f"Schema version '{schema_version}' is not supported. Message discarded."
            )
            message.ack()
            return
        event_handler = event_handlers.get(event_type)
        if not event_handler:
            logger.warning(f"Unknown Event Type {event_type}. Message discarded.")
            message.ack()
            return
        event_handler(event_dict=event_dict)
    except Exception as e:
        logger.exception(
            f"Error Processing Integration Event: {e}",
            extra={"event": json.loads(message.data)},
        )
    else:
        logger.info(f"Integration Event Processed successfully.")
    finally:
        message.ack()


def main():
    while True:  # Keep the consumer running. Reset the connection if it fails.
        try:
            subscriber = pubsub_v1.SubscriberClient()
            subscription_path = subscriber.subscription_path(
                settings.GCP_PROJECT_ID, settings.INTEGRATION_EVENTS_SUB_ID
            )
            streaming_pull_future = subscriber.subscribe(
                subscription_path, callback=process_event
            )
            logger.info(
                f"Integration Events Consumer > Listening for messages on {subscription_path}..\n"
            )

            # Wrap subscriber in a 'with' block to automatically call close() when done.
            with subscriber:
                try:
                    streaming_pull_future.result()
                except Exception as e:
                    logger.exception(f"Internal Error {e}. Shutting down..\n")
                    streaming_pull_future.cancel()  # Trigger the shutdown.
                    streaming_pull_future.result()  # Block until the shutdown is complete.
                    raise e
        except Exception as e:
            logger.exception(f"Internal Error {e}. Restarting..")
            continue


if __name__ == "__main__":
    main()
