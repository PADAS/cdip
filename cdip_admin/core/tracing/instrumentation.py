from typing import Union
from django.conf import settings
from cdip_connector.core.schemas import (
    Position,
    GeoEvent,
    EREvent,
    CameraTrap,
)


def _enrich_span_from_kwargs(span, **kwargs):
    for key, value in kwargs.items():
        span.set_attribute(str(key), str(value))


def enrich_span_with_environment(span):
    span.set_attribute("environment", settings.TRACE_ENVIRONMENT)


def enrich_span_from_position(span, position: Position, **kwargs):
    """
    This helper function adds attributes to a span extracting relevant data from a position.
    It also supports passing extra key/value pairs as attributes.
    """
    # Add attributes to the spans with relevant data for trace analysis
    span.set_attribute("data", str(position.dict()))
    span.set_attribute("integration_id", str(position.integration_id))
    span.set_attribute("observation_type", position.observation_type)
    span.set_attribute("device_id", str(position.device_id))
    _enrich_span_from_kwargs(span, **kwargs)


def enrich_span_from_event(span, event: Union[GeoEvent, EREvent], **kwargs):
    """
    This helper function adds attributes to a span extracting relevant data from an event.
    It also supports passing extra key/value pairs as attributes.
    """
    span.set_attribute("data", str(event.dict()))
    span.set_attribute("integration_id", str(event.integration_id))
    span.set_attribute("observation_type", event.observation_type)
    span.set_attribute("device_id", str(event.device_id))
    span.set_attribute("event_type", event.event_type)
    span.set_attribute("event_location", str(event.location.dict()))
    span.set_attribute("event_title", event.title)
    if isinstance(event, GeoEvent):
        span.set_attribute("event_geometry", str(event.geometry))
    elif isinstance(event, EREvent):
        span.set_attribute("event_owner", event.owner)
        span.set_attribute("event_state", str(event.state))
        span.set_attribute("event_priority", str(event.priority))
    _enrich_span_from_kwargs(span, **kwargs)


def enrich_span_from_camera_trap(span, camera_trap: CameraTrap, **kwargs):
    """
    This helper function adds attributes to a span extracting relevant data from a camera trap.
    It also supports passing extra key/value pairs as attributes.
    """
    span.set_attribute("data", str(camera_trap.dict()))
    span.set_attribute("integration_id", str(camera_trap.integration_id))
    span.set_attribute("observation_type", camera_trap.observation_type)
    span.set_attribute("device_id", str(camera_trap.device_id))
    span.set_attribute("camera_trap_name", str(camera_trap.name))
    span.set_attribute("camera_trap_type", str(camera_trap.type))
    span.set_attribute("camera_trap_location", str(camera_trap.location.dict()))
    _enrich_span_from_kwargs(span, **kwargs)


def enrich_span_from_observation(span, observation, **kwargs):
    """
    This helper function adds attributes to a span extracting relevant data from an observation.
    It also supports passing extra key/value pairs as attributes.
    """
    span.set_attribute("data", str(observation.dict()))
    # Extract attributes that are common to all the observation types
    span.set_attribute("owner", str(observation.owner))
    span.set_attribute("integration_id", str(observation.integration_id))
    span.set_attribute("observation_type", str(observation.observation_type))
    span.set_attribute("device_id", str(observation.device_id))
    _enrich_span_from_kwargs(span, **kwargs)


def enrich_span_from_attachment(span, attachment, **kwargs):
    span.set_attribute("integration_id", str(attachment.integration_id))
    span.set_attribute("observation_type", str(attachment.observation_type))
    _enrich_span_from_kwargs(span, **kwargs)
