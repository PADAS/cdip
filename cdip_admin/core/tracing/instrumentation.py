import logging
from django.conf import settings
from gundi_core.schemas.v2 import Event, Observation
from gundi_core.schemas.v1 import EREvent
from opentelemetry import propagate


logger = logging.getLogger(__name__)


def _enrich_span_from_kwargs(span, **kwargs):
    for key, value in kwargs.items():
        span.set_attribute(str(key), str(value))


def enrich_span_with_environment(span):
    span.set_attribute("environment", settings.TRACE_ENVIRONMENT)


def enrich_span_from_event(span, event: Event, **kwargs):
    """
    This helper function adds attributes to a span extracting relevant data from an event.
    It also supports passing extra key/value pairs as attributes.
    """
    span.set_attribute("gundi_id", str(event.gundi_id))
    span.set_attribute("integration_id", str(event.data_provider_id))
    span.set_attribute("observation_type", event.observation_type)
    span.set_attribute("source_id", str(event.source_id))
    span.set_attribute("external_source_id", str(event.external_source_id))
    span.set_attribute("location", str(event.location.dict()) if event.location else "no-location")
    span.set_attribute("data", str(event.dict()))
    span.set_attribute("event_type", str(event.event_type))
    span.set_attribute("event_title", event.title)
    span.set_attribute("event_geometry", str(event.geometry))
    _enrich_span_from_kwargs(span, **kwargs)


def enrich_span_from_er_event(span, event: EREvent, **kwargs):
    """
    This helper function adds attributes to a span extracting relevant data from an Earth Ranger Event.
    It also supports passing extra key/value pairs as attributes.
    """
    span.set_attribute("er_uuid", str(event.er_uuid))
    span.set_attribute("serial_number", str(event.serial_number))
    span.set_attribute("integration_id", str(event.integration_id))
    span.set_attribute("observation_type", str(event.observation_type))
    span.set_attribute("device_id", str(event.device_id))
    span.set_attribute("location", str(event.location.dict()) if event.location else "no-location")
    span.set_attribute("data", str(event.dict()))
    span.set_attribute("event_type", str(event.event_type))
    span.set_attribute("event_title", str(event.title))
    span.set_attribute("event_details", str(event.event_details))
    span.set_attribute("patrols", str(event.patrols))
    span.set_attribute("files", str(event.files))
    _enrich_span_from_kwargs(span, **kwargs)


def enrich_span_from_observation(span, observation: Observation, **kwargs):
    """
    This helper function adds attributes to a span extracting relevant data from an observation.
    It also supports passing extra key/value pairs as attributes.
    """
    span.set_attribute("gundi_id", str(observation.gundi_id))
    span.set_attribute("related_to", str(observation.related_to))
    span.set_attribute("integration_id", str(observation.data_provider_id))
    span.set_attribute("observation_type", str(observation.observation_type))
    span.set_attribute("source_id", str(observation.source_id))
    span.set_attribute("external_source_id", str(observation.external_source_id))
    span.set_attribute("location", str(observation.location.dict()))
    span.set_attribute("data", str(observation.dict()))
    span.set_attribute("source_name", str(observation.type))
    span.set_attribute("subject_type", str(observation.subject_type))
    _enrich_span_from_kwargs(span, **kwargs)


def enrich_span_from_attachment(span, attachment, **kwargs):
    span.set_attribute("gundi_id", str(attachment.gundi_id))
    span.set_attribute("integration_id", str(attachment.data_provider_id))
    span.set_attribute("observation_type", str(attachment.observation_type))
    _enrich_span_from_kwargs(span, **kwargs)


def build_context_headers():
    headers = {}
    propagate.inject(headers)
    logger.debug(f"[tracing.build_context_headers]> headers: {headers}")
    return headers
