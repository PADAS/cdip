from django.db.models import Min, Value
from django.db.models.functions import Coalesce
from rest_framework import filters


class CustomizableSearchFilter(filters.SearchFilter):
    """
    This search filter allows specifying the search_fields dynamically with a query parameter
    """
    def get_search_fields(self, view, request):
        if search_fields := request.query_params.get('search_fields'):
            return search_fields.split(",")
        # If the query param is not set, check in the view
        return super().get_search_fields(view, request)


class ConnectionOrderingFilter(filters.OrderingFilter):
    """OrderingFilter for ConnectionsView that adds the aggregate needed to
    sort by `destination_type`.

    Applies the annotation only when DRF has actually resolved
    `destination_type` as part of the ordering, so the extra join +
    GROUP BY is not paid on every list request.

    Wraps the aggregate in `Coalesce` so that connections whose routes
    have no destinations get a concrete high-sorting value instead of
    SQL NULL. This lets CursorPagination — which encodes the cursor
    position as `str(annotation_value)` — round-trip across pages, and
    removes the backend-dependent NULLS FIRST / NULLS LAST behavior.

    Appends `id` as a stable tiebreaker so pages are deterministic even
    for rows that share a destination type name.
    """

    # A codepoint above any character IntegrationType names use, so
    # connections with no destinations sort after every real type name
    # on ASC (and before every real type name on DESC).
    _NO_DESTINATION_SENTINEL = "￿"

    def filter_queryset(self, request, queryset, view):
        ordering = self.get_ordering(request, queryset, view) or ()
        if any(field.removeprefix("-") == "destination_type" for field in ordering):
            queryset = queryset.annotate(
                destination_type=Coalesce(
                    Min("routing_rules_by_provider__destinations__type__name"),
                    Value(self._NO_DESTINATION_SENTINEL),
                )
            )
            return queryset.order_by(*ordering, "id")
        return super().filter_queryset(request, queryset, view)
