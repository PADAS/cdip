import json
from hashlib import md5

import backoff
from google.api_core.exceptions import GoogleAPICallError
from google.cloud import pubsub_v1
from cdip_connector.core import cdip_settings
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.conf import settings
from cdip_connector.core.publisher import NullPublisher, Publisher
from gundi_core.schemas.v2 import StreamPrefixEnum, Location, Attachment, Event, Observation, EventUpdate
from gundi_core.events import EventUpdateReceived, ObservationReceived, EventReceived, AttachmentReceived
from core import tracing, cache
from opentelemetry import trace
from integrations.models import GundiTrace


deduplication_db = cache.get_deduplication_db()


def is_duplicate_data(data: dict, expiration_time):
    jsonified_data = json.dumps(data, default=str)
    # For a short time, check both the legacy, simple hash too.
    hash_v1 = md5(jsonified_data.encode("utf-8")).hexdigest()
    integration_id = str(data['integration'].id)
    source_id = str(data['source'].id)
    hash = f"{integration_id}.{source_id}.{hash_v1}"

    # Discard duplicates
    is_duplicate = deduplication_db.exists(hash, hash_v1) > 0
    deduplication_db.setex(
        hash, expiration_time, 1
    )
    deduplication_db.delete(hash_v1)
    return is_duplicate


def is_duplicate_attachment(data: dict):
    integration_id = str(data["integration"].id)
    source = data.get('source')
    source_id = str(source.id if source else None)
    related_to = str(data["related_to"])
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


class GooglePublisher(Publisher):

    def __init__(self):
        self.pubsub_client = pubsub_v1.PublisherClient()

    @backoff.on_exception(
        backoff.expo, (GoogleAPICallError,), max_tries=5, jitter=backoff.full_jitter
    )
    def publish(self, topic: str, data: dict, extra: dict = None):
        extra = extra or {}
        # Specify the topic path
        topic_path = self.pubsub_client.topic_path(settings.GCP_PROJECT_ID, topic)
        publish_future = self.pubsub_client.publish(
            topic=topic_path,
            data=json.dumps(data, default=str).encode("utf-8"),
            **extra
        )
        result = publish_future.result()
        return result


def get_publisher():
    if cdip_settings.PUBSUB_ENABLED:
        return GooglePublisher()
    else:
        return NullPublisher()


publisher = get_publisher()


def send_events_to_routing(events, gundi_ids):
    for event, gundi_id in zip(events, gundi_ids):
        # Trace observations with Open Telemetry
        with tracing.tracer.start_as_current_span(
                f"gundi_api.process_event", kind=trace.SpanKind.PRODUCER
        ) as current_span:
            tracing.instrumentation.enrich_span_with_environment(
                span=current_span
            )
            integration = event.get("integration")
            source = event.get("source")
            source_id = source.external_id if source else None
            current_span.set_attribute("gundi_id", gundi_id)
            current_span.set_attribute("observation_type", StreamPrefixEnum.event.value)
            current_span.set_attribute("integration_type", integration.type.value)
            current_span.set_attribute("integration_id", str(integration.id))
            current_span.set_attribute("integration_name", integration.name)
            current_span.set_attribute("external_source_id", str(source_id))
            current_span.set_attribute("device_id", str(source_id))  # For backward compatibility

            # Check for duplicates
            is_duplicate = is_duplicate_data(data=event, expiration_time=settings.GEOEVENT_DUPLICATE_CHECK_SECONDS)
            if is_duplicate:
                current_span.set_attribute("is_duplicate", True)
                current_span.add_event(
                    name=f"gundi_api.duplicate.event_discarded"
                )
                gundi_trace = GundiTrace.objects.get(object_id=gundi_id)
                gundi_trace.is_duplicate = True
                gundi_trace.save()
                continue

            with tracing.tracer.start_as_current_span(
                    f"gundi_api.send_event_to_routing", kind=trace.SpanKind.PRODUCER
            ) as current_span:
                # Convert the event to the schema supported by routing
                if event_location := event.get("location"):
                    location = Location(
                        lon=event_location.get("lon"),  # Longitude
                        lat=event_location.get("lat"),  # Latitude
                        alt=event_location.get("alt", 0.0),  # Altitude
                        hdop=event_location.get("hdop"),
                        vdop=event_location.get("vdop")
                    )
                else:
                    location = None
                msg_for_routing = EventReceived(
                    payload=Event(
                        gundi_id=str(gundi_id),
                        related_to=event.get("related_to"),
                        data_provider_id=str(integration.id),
                        source_id=str(source.id),
                        external_source_id=str(source.external_id),
                        owner=str(integration.owner.id),  # Warning this can lead to the n+1 queries problem
                        recorded_at=event.get("recorded_at"),  #ToDo: Convet to "2021-03-21 12:01:02-0700"
                        location=location,
                        annotations=event.get("annotations", {}),
                        title=event.get("title"),
                        event_type=event.get("event_type"),
                        event_details=event.get("event_details", {}),
                        geometry=event.get("geometry", {}),
                        observation_type=StreamPrefixEnum.event.value
                    )
                )
                tracing.instrumentation.enrich_span_from_event(
                    span=current_span, event=msg_for_routing.payload, gundi_version="v2",
                    gundi_id=str(gundi_id), related_to=str(event.get("related_to"))
                )
                tracing_context = json.dumps(
                    tracing.instrumentation.build_context_headers(),
                    default=str,
                )
                # Send message to routing services
                publisher.publish(
                    topic=settings.RAW_OBSERVATIONS_TOPIC,
                    data=json.loads(msg_for_routing.json()),  # This is suboptimal but it's fixed in pydantic 2
                    extra={
                        "observation_type": StreamPrefixEnum.event.value,
                        "gundi_version": "v2",  # Add the version so routing knows how to handle it
                        "gundi_id": str(gundi_id),
                        "tracing_context": tracing_context  # Propagate OTel context in message attributes
                    },
                )


def send_event_update_to_routing(event_trace, event_changes):
    # Trace observations with Open Telemetry
    with tracing.tracer.start_as_current_span(
            f"gundi_api.process_event_update", kind=trace.SpanKind.PRODUCER
    ) as current_span:
        tracing.instrumentation.enrich_span_with_environment(
            span=current_span
        )
        gundi_id = str(event_trace.object_id)
        integration = event_trace.data_provider
        current_span.set_attribute("gundi_id", gundi_id)
        current_span.set_attribute("observation_type", StreamPrefixEnum.event_update.value)
        current_span.set_attribute("integration_type", integration.type.value)
        current_span.set_attribute("integration_id", str(integration.id))
        current_span.set_attribute("integration_name", integration.name)
        if "integration" in event_changes:
            event_changes.pop("integration")
        with tracing.tracer.start_as_current_span(
                f"gundi_api.send_event_update_to_routing", kind=trace.SpanKind.PRODUCER
        ) as current_span:
            msg_for_routing = EventUpdateReceived(
                payload=EventUpdate(
                    gundi_id=gundi_id,
                    related_to=str(event_trace.related_to),
                    data_provider_id=str(integration.id),
                    owner=str(integration.owner.id),
                    changes=event_changes,
                )
            )
            tracing_context = json.dumps(
                tracing.instrumentation.build_context_headers(),
                default=str,
            )
            # Send message to routing services
            publisher.publish(
                topic=settings.RAW_OBSERVATIONS_TOPIC,
                data=json.loads(msg_for_routing.json()),  # This is suboptimal but it's fixed in pydantic 2
                extra={
                    "observation_type": StreamPrefixEnum.event_update.value,
                    "gundi_version": "v2",  # Add the version so routing knows how to handle it
                    "gundi_id": str(gundi_id),
                    "tracing_context": tracing_context  # Propagate OTel context in message attributes
                },
            )


def send_attachments_to_routing(attachments_data, gundi_ids):
    for attachment, gundi_id in zip(attachments_data, gundi_ids):
        # Trace observations with Open Telemetry
        with tracing.tracer.start_as_current_span(
                f"gundi_api.process_attachment", kind=trace.SpanKind.PRODUCER
        ) as current_span:
            tracing.instrumentation.enrich_span_with_environment(
                span=current_span
            )
            observation_type = StreamPrefixEnum.attachment.value
            integration = attachment.get("integration")
            source = attachment.get("source")
            source_id = source.external_id if source else None
            current_span.set_attribute("gundi_id", gundi_id)
            current_span.set_attribute("observation_type", observation_type)
            current_span.set_attribute("integration_type", integration.type.value)
            current_span.set_attribute("integration_id", str(integration.id))
            current_span.set_attribute("integration_name", integration.name)
            current_span.set_attribute("external_source_id", str(source_id)),
            current_span.set_attribute("device_id", str(source_id))  # For backward compatibility

            # Check for duplicates
            is_duplicate = is_duplicate_attachment(data=attachment)
            if is_duplicate:
                current_span.set_attribute("is_duplicate", True)
                current_span.add_event(
                    name=f"gundi_api.duplicate.attachment_discarded"
                )
                gundi_trace = GundiTrace.objects.get(object_id=gundi_id)
                gundi_trace.is_duplicate = True
                gundi_trace.save()
                continue
            # Upload file to the cloud
            with tracing.tracer.start_as_current_span(
                    f"gundi_api.upload_file_to_gcp", kind=trace.SpanKind.PRODUCER
            ) as gcp_upload_span:
                file = attachment["file"]
                gcp_upload_span.set_attribute("file_name", file.name)
                file_path = default_storage.save(f"attachments/{gundi_id}_{file.name}", ContentFile(file.read()))
            with tracing.tracer.start_as_current_span(
                    f"gundi_api.send_attachment_to_routing", kind=trace.SpanKind.PRODUCER
            ):
                msg_for_routing = AttachmentReceived(
                    payload=Attachment(
                        gundi_id=str(gundi_id),
                        data_provider_id=str(integration.id),
                        source_id=str(source.id if source else None),  # ToDo: Can be null?
                        external_source_id=str(source.external_id if source else None),
                        related_to=attachment.get("related_to"),
                        file_path=file_path,
                        observation_type=observation_type
                    )
                )
                tracing.instrumentation.enrich_span_from_attachment(
                    span=current_span, attachment=msg_for_routing.payload, file_path=file_path,
                    gundi_version="v2", gundi_id=str(gundi_id), related_to=str(attachment.get("related_to"))
                )
                tracing_context = json.dumps(
                    tracing.instrumentation.build_context_headers(),
                    default=str,
                )
                # Send message to routing services
                publisher.publish(
                    topic=settings.RAW_OBSERVATIONS_TOPIC,
                    data=json.loads(msg_for_routing.json()),  # This is suboptimal but it's fixed in pydantic 2
                    extra={
                        "observation_type": StreamPrefixEnum.attachment.value,
                        "gundi_version": "v2",  # Add the version so routing knows how to handle it
                        "gundi_id": str(gundi_id),
                        "tracing_context": tracing_context  # Propagate OTel context in message attributes
                    },
                )


def send_observations_to_routing(observations, gundi_ids):
    for observation, gundi_id in zip(observations, gundi_ids):
        # Trace observations with Open Telemetry
        with tracing.tracer.start_as_current_span(
                f"gundi_api.process_observation", kind=trace.SpanKind.PRODUCER
        ) as current_span:
            tracing.instrumentation.enrich_span_with_environment(
                span=current_span
            )
            observation_type = StreamPrefixEnum.observation.value
            integration = observation.get("integration")
            source = observation.get("source")
            source_id = source.external_id if source else None
            location = observation.get("location", {})
            current_span.set_attribute("gundi_id", gundi_id)
            current_span.set_attribute("observation_type", observation_type)
            current_span.set_attribute("integration_type", integration.type.value)
            current_span.set_attribute("integration_id", str(integration.id))
            current_span.set_attribute("integration_name", integration.name)
            current_span.set_attribute("external_source_id", str(source_id)),
            current_span.set_attribute("device_id", str(source_id))  # For backward compatibility
            current_span.set_attribute("location", str(location))

            # Check for duplicates
            is_duplicate = is_duplicate_data(
                data=observation,
                expiration_time=settings.OBSERVATION_DUPLICATE_CHECK_SECONDS
            )
            if is_duplicate:
                current_span.set_attribute("is_duplicate", True)
                current_span.add_event(
                    name=f"gundi_api.duplicate.observation_discarded"
                )
                gundi_trace = GundiTrace.objects.get(object_id=gundi_id)
                gundi_trace.is_duplicate = True
                gundi_trace.save()
                continue

            with tracing.tracer.start_as_current_span(
                    f"gundi_api.send_observations_to_routing", kind=trace.SpanKind.PRODUCER
            ) as current_span:
                # Convert the event to the schema supported by routing
                msg_for_routing = ObservationReceived(
                    payload=Observation(
                        gundi_id=str(gundi_id),
                        related_to=observation.get("related_to"),
                        owner=str(integration.owner.id),  # Warning this can lead to the n+1 queries problem
                        data_provider_id=str(integration.id),
                        annotations=observation.get("annotations", {}),
                        source_id=str(source.id),
                        external_source_id=str(source.external_id),
                        source_name=observation.get("source_name") or str(source.name),
                        type=observation.get("type"),
                        subject_type=observation.get("subject_type"),
                        recorded_at=observation.get("recorded_at"),
                        location=Location(
                            lon=location.get("lon"),  # Longitude
                            lat=location.get("lat"),  # Latitude
                            alt=location.get("alt", 0.0),  # Altitude
                            hdop=location.get("hdop"),
                            vdop=location.get("vdop")
                        ),
                        additional=observation.get("additional", {}),
                        observation_type=StreamPrefixEnum.observation.value
                    )
                )
                tracing.instrumentation.enrich_span_from_observation(
                    span=current_span, observation=msg_for_routing.payload, gundi_version="v2"
                )
                tracing_context = json.dumps(
                    tracing.instrumentation.build_context_headers(),
                    default=str,
                )
                # Send message to routing services
                publisher.publish(
                    topic=settings.RAW_OBSERVATIONS_TOPIC,
                    data=json.loads(msg_for_routing.json()),  # This is suboptimal. It's fixed in pydantic v2
                    extra={
                        "observation_type": StreamPrefixEnum.observation.value,
                        "gundi_version": "v2",  # Add the version so routing knows how to handle it
                        "gundi_id": str(gundi_id),
                        "tracing_context": tracing_context  # Propagate OTel context in message attributes
                    },
                )
