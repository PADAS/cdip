from datetime import datetime, timedelta
from django.contrib import admin
from django.contrib.admin.filters import DateFieldListFilter
from django.utils.translation import gettext_lazy as _


class CustomDateFilter(DateFieldListFilter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        today = datetime.today()
        yesterday = today - timedelta(days=1)

        self.links += ((
            (_('Yesterday'), {
                self.lookup_kwarg_since: datetime.strftime(yesterday, '%Y-%m-%d'),
                self.lookup_kwarg_until: datetime.strftime(today, '%Y-%m-%d'),
            }),
        ))
