from django.conf import settings
from gundi_core.schemas.v2 import Event


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
    span.set_attribute("gundi_id", str(event.object_id))
    span.set_attribute("data", str(event.dict()))
    span.set_attribute("integration_id", str(event.data_provider_id))
    span.set_attribute("observation_type", event.observation_type)
    span.set_attribute("source_id", str(event.source_id))
    span.set_attribute("event_type", str(event.event_type))
    span.set_attribute("event_location", str(event.location.dict()))
    span.set_attribute("event_title", event.title)
    span.set_attribute("event_geometry", str(event.geometry))
    # ToDo: Check what was this for:
    # span.set_attribute("event_owner", event.owner)
    # span.set_attribute("event_state", str(event.state))
    # span.set_attribute("event_priority", str(event.priority))
    _enrich_span_from_kwargs(span, **kwargs)


def enrich_span_from_attachment(span, attachment, **kwargs):
    span.set_attribute("gundi_id", str(attachment.object_id))
    span.set_attribute("integration_id", str(attachment.data_provider_id))
    span.set_attribute("observation_type", str(attachment.observation_type))
    _enrich_span_from_kwargs(span, **kwargs)
