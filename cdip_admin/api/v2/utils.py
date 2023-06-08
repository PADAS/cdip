import json
from copy import deepcopy

from cdip_connector.core.publisher import get_publisher
from cdip_connector.core.routing import TopicEnum
from cdip_connector.core.schemas import StreamPrefixEnum, GeoEvent, Location


# ToDo: Retry on failure?
def send_events_to_routing(events, gundi_ids):
    publisher = get_publisher()

    for event, gundi_id in zip(events, gundi_ids):
        # # Use Consumer.cusumer_custom_id as integration ID.
        # if not message.integration_id and consumer_info.consumer_side_data:
        #     message.integration_id = (
        #         consumer_info.consumer_side_data.default_integration_id
        #     )

        # jsonified_data = json.dumps(message.dict(), default=str)

        # # For a short time, check both the legacy, simple hash too.
        # hash_v1 = md5(jsonified_data.encode("utf-8")).hexdigest()
        # hash = f"{message.integration_id}.{message.device_id}.{hash_v1}"
        #
        # # Trace observations with Open Telemetry
        # with tracing.tracer.start_as_current_span(
        #         f"gundi_api.processing_new_observation", kind=trace.SpanKind.PRODUCER
        # ) as current_span:
        #     tracing.observations_instrumentation.enrich_span_with_environment(
        #         span=current_span
        #     )
        #     tracing.observations_instrumentation.enrich_span_from_consumer_info(
        #         span=current_span,
        #         consumer_info=consumer_info,
        #         endpoint="/events/",
        #     )
        #     tracing.observations_instrumentation.enrich_span_from_event(
        #         span=current_span, message=message
        #     )
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

