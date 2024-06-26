from opentelemetry.propagators.cloud_trace_propagator import (
    CloudTraceFormatPropagator,
)
from opentelemetry.propagate import set_global_textmap
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from django.conf import settings
from . import config
from . import instrumentation


# Using the X-Cloud-Trace-Context header
set_global_textmap(CloudTraceFormatPropagator())
if settings.TRACING_ENABLED:
    RequestsInstrumentor().instrument()
else:
    RequestsInstrumentor().uninstrument()
tracer = config.configure_tracer(name="cdip-portal", version="2.0.0")
