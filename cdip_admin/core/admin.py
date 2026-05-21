import logging
from datetime import datetime, timedelta

from django.contrib import admin
from django.contrib.admin.filters import DateFieldListFilter
from django.core.paginator import Paginator
from django.db import connection
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _


logger = logging.getLogger(__name__)


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


class EstimatedCountPaginator(Paginator):
    """Postgres-aware paginator that returns ``pg_class.reltuples`` for
    unfiltered queries on large tables, avoiding the full-table ``COUNT(*)``
    that Django's default paginator runs on every admin changelist render.

    The standard ``ModelAdmin.show_full_result_count = False`` only suppresses
    the *additional* unfiltered total shown next to a filtered count — the
    paginator still evaluates ``queryset.count()`` for the page itself. On
    tables with hundreds of millions of rows that single COUNT can lock up
    a worker for minutes and trigger the same incident this PR is meant to
    fix. Replacing the paginator's count is the only way to actually skip
    it.

    Behaviour:

    - **Unfiltered queryset on Postgres**: use the planner's
      ``reltuples`` row estimate from ``pg_class``. This is cheap (system
      catalog read) and roughly accurate after ``ANALYZE``. We require
      the estimate to be at least ``ESTIMATE_THRESHOLD`` rows before we
      trust it; for small/new tables we fall through to the exact count.
    - **Filtered queryset, or any non-Postgres backend, or an error
      reading the catalog**: fall back to the standard exact count.

    A filtered changelist (e.g. one log_level / one integration) can still
    issue an expensive count, but admin users hit those intentionally and
    the WHERE clause usually narrows the scan dramatically — the incident
    being fixed is the unfiltered index page.
    """

    # Below this estimate, prefer the exact count: small tables count
    # cheaply and the catalog estimate can be wildly wrong before the
    # first ANALYZE (Postgres seeds it at -1 / row width-based guesses).
    ESTIMATE_THRESHOLD = 1000

    @cached_property
    def count(self):
        query = self.object_list.query
        if (
            connection.vendor == "postgresql"
            and not query.where
            and not query.distinct
            and not query.group_by
        ):
            estimate = self._pg_class_estimate(query.model._meta.db_table)
            if estimate is not None and estimate >= self.ESTIMATE_THRESHOLD:
                return estimate
        return super().count

    @staticmethod
    def _pg_class_estimate(table_name):
        """Return the planner's row estimate for ``table_name``, or ``None``
        if the catalog read fails or returns no row. Pulled out as a seam
        so tests can mock the estimate without colliding with the cursor
        used by the exact-count fallback.
        """
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT reltuples::bigint FROM pg_class WHERE relname = %s",
                    [table_name],
                )
                row = cursor.fetchone()
        except Exception:
            logger.warning(
                "EstimatedCountPaginator: pg_class lookup failed for %s; "
                "falling back to exact COUNT(*).",
                table_name,
                exc_info=True,
            )
            return None
        if row is None or row[0] is None:
            return None
        return int(row[0])
