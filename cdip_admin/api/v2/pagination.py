from proxy_pagination import ProxyPagination
from rest_framework.pagination import (
    CursorPagination,
    LimitOffsetPagination,
    PageNumberPagination,
)


class _FilterSourcesLimitOffset(LimitOffsetPagination):
    default_limit = 50


class _FilterSourcesPageNumber(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"


class _FilterSourcesCursor(CursorPagination):
    page_size = 50
    # `external_id` is unique per provider, not globally, and one filter may hold sources
    # from several providers. Cursor pagination skips or repeats rows when the ordering is
    # not unique, so `id` breaks the ties.
    ordering = ("external_id", "id")


class FilterSourcesPagination(ProxyPagination):
    """Sources inside a single routing filter.

    A filter may hold up to ``SOURCE_FILTER_MAX_SOURCES`` entries, so these are paged
    rather than returned whole. Defaults to 50 per page instead of the project-wide 20,
    and keeps the house ``?pager=`` mechanism: ``?pager=limit&limit=100``,
    ``?pager=page&page_size=100``.
    """

    default_pager = _FilterSourcesLimitOffset
    pager_mapping = {
        "limit": _FilterSourcesLimitOffset,
        "page": _FilterSourcesPageNumber,
        "cursor": _FilterSourcesCursor,
    }
