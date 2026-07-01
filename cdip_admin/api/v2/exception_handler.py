import logging

from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger(__name__)

# Path prefix for the v2 ingestion/API surface. A 4xx here means a data provider
# (connector) sent something we rejected; we log the detail so the cause is
# diagnosable. Django's default `django.request` "Bad Request" line carries none.
_V2_PREFIX = "/v2/"
_MAX_DETAIL_CHARS = 2000


def _truncate(value):
    text = str(value)
    if len(text) > _MAX_DETAIL_CHARS:
        return text[:_MAX_DETAIL_CHARS] + "…(truncated)"
    return text


def logging_exception_handler(exc, context):
    """DRF exception handler that additionally logs the *reason* for v2 4xx
    responses (validation/parse errors), which the default handler swallows into
    an opaque "Bad Request". Response behavior is unchanged."""
    response = drf_exception_handler(exc, context)
    if response is None:
        return response

    request = context.get("request")
    path = getattr(request, "path", "") or ""
    if 400 <= response.status_code < 500 and path.startswith(_V2_PREFIX):
        logger.warning(
            "gundi_api.v2.request_rejected:%s %s -> %s",
            getattr(request, "method", "?"),
            path,
            response.status_code,
            extra={
                "status_code": response.status_code,
                "path": path,
                "integration_id": getattr(request, "integration_id", None),
                # response.data holds the serializer/parse error detail. It is
                # field names + messages, not the raw payload; truncated for safety.
                "detail": _truncate(getattr(response, "data", None)),
            },
        )
    return response
