from unittest.mock import MagicMock, patch

from opentelemetry import trace

from sync_integrations.tracing import PortalTracing


def test_start_span_yields_a_span_that_accepts_attributes_and_events():
    with patch.object(
        __import__("sync_integrations.tracing", fromlist=["tracing"]).tracing,
        "tracer",
    ) as mock_tracer:
        mock_tracer.start_as_current_span.return_value.__enter__.return_value = MagicMock()
        with PortalTracing().start_span("gundi_er_smart_sync.process_event", kind="producer") as span:
            span.set_attribute("is_patrol_event", True)
            span.add_event("gundi_er_smart_sync.event_sent_to_routing")
        mock_tracer.start_as_current_span.assert_called_once_with(
            "gundi_er_smart_sync.process_event", kind=trace.SpanKind.PRODUCER
        )


def test_unknown_kind_falls_back_to_internal():
    with patch.object(
        __import__("sync_integrations.tracing", fromlist=["tracing"]).tracing,
        "tracer",
    ) as mock_tracer:
        mock_tracer.start_as_current_span.return_value.__enter__.return_value = MagicMock()
        with PortalTracing().start_span("x", kind="not-a-kind"):
            pass
        mock_tracer.start_as_current_span.assert_called_once_with(
            "x", kind=trace.SpanKind.INTERNAL
        )


def test_build_context_headers_returns_a_dict():
    assert isinstance(PortalTracing().build_context_headers(), dict)
