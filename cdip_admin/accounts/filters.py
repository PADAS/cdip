from django.db import models
from django.utils.translation import gettext_lazy as _
import django_filters
from django.contrib.auth.models import User


class AccountFilter(django_filters.FilterSet):
    search = django_filters.CharFilter(
        method="filter_search", label=_("Name / Email")
    )

    class Meta:
        model = User
        fields = []

    def filter_search(self, queryset, name, value):
        return queryset.filter(
            models.Q(first_name__icontains=value)
            | models.Q(last_name__icontains=value)
            | models.Q(email__icontains=value)
            | models.Q(username__icontains=value)
        )
