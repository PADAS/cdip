from django.db import models
from django.utils.translation import gettext_lazy as _
import django_filters

from .models import Organization


class OrganizationFilter(django_filters.FilterSet):
    search = django_filters.CharFilter(
        method="filter_search", label=_("Name / Description")
    )

    class Meta:
        model = Organization
        fields = []

    def filter_search(self, queryset, name, value):
        return queryset.filter(
            models.Q(name__icontains=value)
            | models.Q(description__icontains=value)
        )
