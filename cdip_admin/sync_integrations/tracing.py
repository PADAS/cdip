"""er-smart-sync TracingProvider over the portal's OpenTelemetry tracer."""
from contextlib import contextmanager

from opentelemetry import trace

from core import tracing

_SPAN_KINDS = {
    "producer": trace.SpanKind.PRODUCER,
    "consumer": trace.SpanKind.CONSUMER,
    "client": trace.SpanKind.CLIENT,
    "server": trace.SpanKind.SERVER,
    "internal": trace.SpanKind.INTERNAL,
}


class PortalTracing:
    @contextmanager
    def start_span(self, name: str, kind: str = "producer"):
        span_kind = _SPAN_KINDS.get(kind, trace.SpanKind.INTERNAL)
        with tracing.tracer.start_as_current_span(name, kind=span_kind) as span:
            yield span

    def build_context_headers(self) -> dict:
        return tracing.instrumentation.build_context_headers()
