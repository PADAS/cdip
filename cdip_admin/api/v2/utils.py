import json
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from cdip_connector.core.publisher import get_publisher
from cdip_connector.core.routing import TopicEnum
from cdip_connector.core.schemas import StreamPrefixEnum, GeoEvent, Location, Attachment
from core import tracing
from opentelemetry import trace


# ToDo: Retry on failure?
def send_events_to_routing(events, gundi_ids):
    publisher = get_publisher()

    for event, gundi_id in zip(events, gundi_ids):
        # ToDo: Manage tracing and deduplication
        # jsonified_data = json.dumps(message.dict(), default=str)

        # # For a short time, check both the legacy, simple hash too.
        # hash_v1 = md5(jsonified_data.encode("utf-8")).hexdigest()
        # hash = f"{message.integration_id}.{message.device_id}.{hash_v1}"
        #
        # # Trace observations with Open Telemetry
        with tracing.tracer.start_as_current_span(
                f"gundi_api.process_event", kind=trace.SpanKind.PRODUCER
        ) as current_span:
            tracing.instrumentation.enrich_span_with_environment(
                span=current_span
            )
        #
        #     # Discard duplicates
        #     is_duplicate = deduplication_db.exists(hash, hash_v1) > 0
        #     deduplication_db.setex(
        #         hash, app.settings.GEOEVENT_DUPLICATE_CHECK_SECONDS, 1
        #     )
        #     deduplication_db.delete(hash_v1)
        #     if is_duplicate:
        #         current_span.set_attribute("is_duplicate", True)
        #         current_span.add_event(
        #             name=f"gundi_api.duplicate_observation_discarded"
        #         )
        #         continue
        #
        #     # Downstream consumers will want to know the owner by subject.
        #     message.owner = consumer_info.consumer_username
        #
        #     event_stream_key = (
        #         f"{message.observation_type}.{message.integration_id}.{message.device_id}"
        #     )
        #
        #     device_stream = db.Stream(event_stream_key)
        #     logger.debug("Post_item. message: %s", message)
        #
        #     id = device_stream.add(
        #         {"data": jsonified_data},
        #         maxlen=app.settings.GEOEVENT_STREAM_DEFAULT_MAXLEN,
        #         approximate=True,
        #     )
        #     message.id = id
            with tracing.tracer.start_as_current_span(
                    f"gundi_api.send_event_to_routing", kind=trace.SpanKind.PRODUCER
            ) as current_span:
                # Convert the event to the schema supported by routing
                integration = event.get("integration")
                msg_for_routing = GeoEvent(
                    id=str(gundi_id),
                    device_id=event.get("source_id"),
                    integration_id=str(integration.id),
                    owner=str(integration.owner.id),  # Warning this can lead to the n+1 queries problem
                    recorded_at=event.get("recorded_at"),  #ToDo: Convet to "2021-03-21 12:01:02-0700"
                    location=Location(
                        x=event.get("location", {}).get("lon"),  # Longitude
                        y=event.get("location", {}).get("lat"),  # Latitude
                        z=event.get("location", {}).get("alt"),  # Altitude
                        hdop=event.get("location", {}).get("hdop"),
                        vdop=event.get("location", {}).get("vdop")
                    ),
                    additional=event.get("annotations",{}),
                    title=event.get("title"),
                    event_type=event.get("event_type"),
                    event_details=event.get("event_details", {}),
                    geometry=event.get("geometry", {}),
                    observation_type=StreamPrefixEnum.geoevent.value
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
                        "observation_type": StreamPrefixEnum.geoevent.value,
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
            # jsonified_data = json.dumps(message.dict(), default=str)

            # # For a short time, check both the legacy, simple hash too.
            # hash_v1 = md5(jsonified_data.encode("utf-8")).hexdigest()
            # hash = f"{message.integration_id}.{message.device_id}.{hash_v1}"
            #

            #     # Discard duplicates
            #     is_duplicate = deduplication_db.exists(hash, hash_v1) > 0
            #     deduplication_db.setex(
            #         hash, app.settings.GEOEVENT_DUPLICATE_CHECK_SECONDS, 1
            #     )
            #     deduplication_db.delete(hash_v1)
            #     if is_duplicate:
            #         current_span.set_attribute("is_duplicate", True)
            #         current_span.add_event(
            #             name=f"gundi_api.duplicate_observation_discarded"
            #         )
            #         continue
            #
            #     # Downstream consumers will want to know the owner by subject.
            #     message.owner = consumer_info.consumer_username
            #
            #     event_stream_key = (
            #         f"{message.observation_type}.{message.integration_id}.{message.device_id}"
            #     )
            #
            #     device_stream = db.Stream(event_stream_key)
            #     logger.debug("Post_item. message: %s", message)
            #
            #     id = device_stream.add(
            #         {"data": jsonified_data},
            #         maxlen=app.settings.GEOEVENT_STREAM_DEFAULT_MAXLEN,
            #         approximate=True,
            #     )
            #     message.id = id
            # Upload file to the cloud
            with tracing.tracer.start_as_current_span(
                    f"gundi_api.upload_file_to_gcp", kind=trace.SpanKind.PRODUCER
            ) as subspan:
                tracing.instrumentation.enrich_span_with_environment(
                    span=current_span
                )
                file = attachment["file"]
                file_path = default_storage.save(f"attachments/{gundi_id}_{file.name}", ContentFile(file.read()))
            with tracing.tracer.start_as_current_span(
                    f"gundi_api.send_attachment_to_routing", kind=trace.SpanKind.PRODUCER
            ) as subspan:
                observation_type = StreamPrefixEnum.attachment.value
                # Convert the event to the schema supported by routing
                integration = attachment.get("integration")
                msg_for_routing = Attachment(
                    id=str(gundi_id),
                    integration_id=str(integration.id),
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
