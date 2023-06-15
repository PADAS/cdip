import json
from hashlib import md5
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.conf import settings
from cdip_connector.core.publisher import get_publisher
from cdip_connector.core.routing import TopicEnum
from gundi_core.schemas.v2 import StreamPrefixEnum, Location, Attachment, Event
from core import tracing, cache
from opentelemetry import trace


deduplication_db = cache.get_deduplication_db()


# ToDo: Retry on failure?
def is_duplicate_event(data: dict):

    jsonified_data = json.dumps(data, default=str)

    # For a short time, check both the legacy, simple hash too.
    hash_v1 = md5(jsonified_data.encode("utf-8")).hexdigest()
    integration_id = str(data['integration'].id)
    source_id = str(data['source'].id)
    hash = f"{integration_id}.{source_id}.{hash_v1}"

    # Discard duplicates
    is_duplicate = deduplication_db.exists(hash, hash_v1) > 0
    deduplication_db.setex(
        hash, settings.GEOEVENT_DUPLICATE_CHECK_SECONDS, 1
    )
    deduplication_db.delete(hash_v1)
    return is_duplicate


def is_duplicate_attachment(data: dict):
    integration_id = str(data["integration"].id)
    source_id = str(data['source'].id)
    related_to = data["related_to"]
    jsonified_data = json.dumps({
        "filename": data["file"].name,
        "related_to": related_to,
        "integration_id": integration_id,
    })

    # For a short time, check both the legacy, simple hash too.
    hash_v1 = md5(jsonified_data.encode("utf-8")).hexdigest()
    hash = f"{integration_id}.{source_id}.{related_to}.{hash_v1}"

    # Discard duplicates
    is_duplicate = deduplication_db.exists(hash, hash_v1) > 0
    deduplication_db.setex(
        hash, settings.GEOEVENT_DUPLICATE_CHECK_SECONDS, 1
    )
    deduplication_db.delete(hash_v1)
    return is_duplicate


def send_events_to_routing(events, gundi_ids):
    publisher = get_publisher()

    for event, gundi_id in zip(events, gundi_ids):
        # Trace observations with Open Telemetry
        with tracing.tracer.start_as_current_span(
                f"gundi_api.process_event", kind=trace.SpanKind.PRODUCER
        ) as current_span:
            tracing.instrumentation.enrich_span_with_environment(
                span=current_span
            )

            # Check for duplicates
            is_duplicate = is_duplicate_event(data=event)
            if is_duplicate:
                current_span.set_attribute("is_duplicate", True)
                current_span.add_event(
                    name=f"gundi_api.duplicate.event_discarded"
                )
                continue

            with tracing.tracer.start_as_current_span(
                    f"gundi_api.send_event_to_routing", kind=trace.SpanKind.PRODUCER
            ) as current_span:
                # Convert the event to the schema supported by routing
                integration = event.get("integration")
                source = event.get("source")
                msg_for_routing = Event(
                    gundi_id=str(gundi_id),
                    data_provider_id=str(integration.id),
                    source_id=str(source.id),
                    external_source_id=str(source.external_id),
                    owner=str(integration.owner.id),  # Warning this can lead to the n+1 queries problem
                    recorded_at=event.get("recorded_at"),  #ToDo: Convet to "2021-03-21 12:01:02-0700"
                    location=Location(
                        lon=event.get("location", {}).get("lon"),  # Longitude
                        lat=event.get("location", {}).get("lat"),  # Latitude
                        alt=event.get("location", {}).get("alt"),  # Altitude
                        hdop=event.get("location", {}).get("hdop"),
                        vdop=event.get("location", {}).get("vdop")
                    ),
                    annotations=event.get("annotations", {}),
                    title=event.get("title"),
                    event_type=event.get("event_type"),
                    event_details=event.get("event_details", {}),
                    geometry=event.get("geometry", {}),
                    observation_type=StreamPrefixEnum.event.value
                )
                tracing.instrumentation.enrich_span_from_event(
                    span=current_span, event=msg_for_routing, gundi_version="v2",
                    gundi_id=str(gundi_id), related_to=str(event.get("related_to"))
                )
                # Send message to routing services
                # ToDo: Revisit this once we move transformers from kafka to gcp pubsub
                publisher.publish(
                    topic=TopicEnum.observations_unprocessed.value,
                    data=json.loads(msg_for_routing.json()),  # This is suboptimal but it's fixed in pydantic 2
                    extra={
                        "observation_type": StreamPrefixEnum.event.value,
                        "gundi_version": "v2",  # Add the version so routing knows how to handle it
                        "gundi_id": str(gundi_id)
                    },
                )


def send_attachments_to_routing(attachments_data, gundi_ids):

    publisher = get_publisher()

    for attachment, gundi_id in zip(attachments_data, gundi_ids):
        # ToDo: Manage tracing and deduplication
        # Trace observations with Open Telemetry
        with tracing.tracer.start_as_current_span(
                f"gundi_api.process_attachment", kind=trace.SpanKind.PRODUCER
        ) as current_span:
            tracing.instrumentation.enrich_span_with_environment(
                span=current_span
            )
            # Check for duplicates
            is_duplicate = is_duplicate_attachment(data=attachment)
            if is_duplicate:
                current_span.set_attribute("is_duplicate", True)
                current_span.add_event(
                    name=f"gundi_api.duplicate.attachment_discarded"
                )
                continue
            # Upload file to the cloud
            with tracing.tracer.start_as_current_span(
                    f"gundi_api.upload_file_to_gcp", kind=trace.SpanKind.PRODUCER
            ):
                tracing.instrumentation.enrich_span_with_environment(
                    span=current_span
                )
                file = attachment["file"]
                file_path = default_storage.save(f"attachments/{gundi_id}_{file.name}", ContentFile(file.read()))
            with tracing.tracer.start_as_current_span(
                    f"gundi_api.send_attachment_to_routing", kind=trace.SpanKind.PRODUCER
            ):
                observation_type = StreamPrefixEnum.attachment.value
                # Convert the event to the schema supported by routing
                integration = attachment.get("integration")
                source = attachment.get("source")
                msg_for_routing = Attachment(
                    gundi_id=str(gundi_id),
                    data_provider_id=str(integration.id),
                    source_id=str(source.id),
                    external_source_id=str(source.external_id),
                    related_to=str(attachment.get("related_to")),
                    file_path=file_path,
                    observation_type=observation_type
                )
                tracing.instrumentation.enrich_span_from_attachment(
                    span=current_span, attachment=msg_for_routing, file_path=file_path,
                    gundi_version="v2", gundi_id=str(gundi_id), related_to=str(attachment.get("related_to"))
                )
                # Send message to routing services
                # ToDo: Revisit this once we move transformers from kafka to gcp pubsub
                publisher.publish(
                    topic=TopicEnum.observations_unprocessed.value,
                    data=json.loads(msg_for_routing.json()),  # This is suboptimal but it's fixed in pydantic 2
                    extra={
                        "observation_type": StreamPrefixEnum.attachment.value,
                        "gundi_version": "v2",  # Add the version so routing knows how to handle it
                        "gundi_id": str(gundi_id)
                    },
                )
