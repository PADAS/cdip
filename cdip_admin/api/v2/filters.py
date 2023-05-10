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
