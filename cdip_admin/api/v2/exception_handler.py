import logging

from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger(__name__)

# Path prefix for the v2 ingestion/API surface. A 4xx here means a data provider
# (connector) sent something we rejected; we log the detail so the cause is
# diagnosable. Django's default `django.request` "Bad Request" line carries none.
_V2_PREFIX = "/v2/"
_MAX_DETAIL_CHARS = 2000
_MAX_DETAIL_ITEMS = 20


def _summarize_detail(value):
    """Render the error detail compactly.

    Bulk endpoints (``SingleOrBulkCreateModelMixin``) return a per-item list that
    is mostly empty ``{}`` for the valid items; a big batch would make
    ``str(value)`` huge and pointless. Pull out just the error-bearing entries
    (keyed by their index), capped, so we never stringify the whole batch, then
    bound the final string length as a backstop.
    """
    if isinstance(value, list):
        errors = {}
        for index, item in enumerate(value):
            if not item:  # valid items serialize to an empty {} — skip them
                continue
            errors[index] = item
            if len(errors) >= _MAX_DETAIL_ITEMS:
                break
        text = str({"item_count": len(value), "errors": errors})
    else:
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
                # field names + messages, not the raw payload; summarized+truncated.
                "detail": _summarize_detail(getattr(response, "data", None)),
            },
        )
    return response
