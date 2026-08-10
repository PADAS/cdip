import logging
from datetime import datetime, timedelta

from django import forms
from django.contrib.admin.filters import DateFieldListFilter, RelatedFieldListFilter
from django.contrib.admin.widgets import AutocompleteSelect
from django.core.paginator import Paginator
from django.db import connection
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _


logger = logging.getLogger(__name__)


class AutocompleteFieldListFilter(RelatedFieldListFilter):
    """A foreign-key sidebar filter that never enumerates the related table.

    ``RelatedFieldListFilter`` renders one ``<option>`` per row of the related
    model, so the changelist HTML grows without bound as rows are added --
    roughly 168 bytes per Integration, measured. Loading those options in a
    single ``select_related`` query fixes the query count but not the payload,
    and rendering every Integration into a ``<select>`` is what previously
    timed out the Route change page (see
    ``test_route_change_page_does_not_scale_with_integration_count``).

    ``AutocompleteSelect`` renders only the *currently selected* option --
    ``AutocompleteMixin.optgroups`` filters the queryset to the selected keys,
    so an unfiltered changelist emits zero options and issues zero queries --
    and fetches the rest over AJAX, 20 at a time, as the user types.

    This reuses Django's own ``/admin/autocomplete/`` endpoint and bundled
    select2 assets, so it needs no extra dependency. The endpoint validates the
    *source* field and requires the related model's admin to define
    ``search_fields``; it does not require the field to appear in any
    ``ModelAdmin.autocomplete_fields``, which is what makes it usable from a
    filter that has no form field at all.

    The admin using this filter must contribute the widget's media, which
    Django does not collect from filters -- see ``ActivityLogAdmin.media``.
    """

    template = "admin/autocomplete_filter.html"

    def field_choices(self, field, request, model_admin):
        # Never enumerate the related table; that is the entire point.
        return []

    def has_output(self):
        # The base class hides a filter offering fewer than two choices, and
        # this one deliberately offers none up front.
        return True

    def choices(self, changelist):
        widget = AutocompleteSelect(self.field, changelist.model_admin.admin_site)
        # AutocompleteSelect reads ``choices.field`` and ``choices.queryset`` to
        # render the selected option, so it needs a bound form field. Applying
        # ``limit_choices_to`` keeps that label consistent with what
        # /admin/autocomplete/ will actually offer -- the endpoint applies the
        # same filter in ``AutocompleteJsonView.get_queryset``.
        widget.choices = forms.ModelChoiceField(
            queryset=self.field.remote_field.model._default_manager.complex_filter(
                self.field.get_limit_choices_to()
            ),
            required=False,
        ).choices

        # "All" and "(None)" mirror RelatedFieldListFilter. The empty choice
        # matters here: ``ActivityLog.integration`` is nullable with
        # ``on_delete=SET_NULL``, so orphaned rows accumulate and this is the
        # only way to find them. The autocomplete widget cannot express
        # "is null", so it stays a plain link.
        links = [
            {
                "selected": self.lookup_val is None and not self.lookup_val_isnull,
                "query_string": changelist.get_query_string(
                    remove=[self.lookup_kwarg, self.lookup_kwarg_isnull]
                ),
                "display": _("All"),
            }
        ]
        if self.include_empty_choice:
            links.append(
                {
                    "selected": bool(self.lookup_val_isnull),
                    "query_string": changelist.get_query_string(
                        {self.lookup_kwarg_isnull: "True"}, [self.lookup_kwarg]
                    ),
                    "display": self.empty_value_display,
                }
            )

        yield {
            "widget": widget.render(
                self.lookup_kwarg,
                self.lookup_val,
                attrs={"onchange": "this.form.submit();"},
            ),
            # Every other active parameter has to ride along as a hidden input
            # or submitting this filter would silently drop the search term,
            # the date filter and the ordering.
            "carried_params": [
                (key, value)
                for key, value in changelist.params.items()
                if key not in (self.lookup_kwarg, self.lookup_kwarg_isnull)
            ],
            "links": links,
        }


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
      ``reltuples`` row estimate. We use ``pg_partition_tree`` so the
      estimate works for both regular tables (one row → its own
      ``reltuples``) and partitioned tables (sum across leaf partitions).
      The reltuples value comes from the catalog and costs microseconds.
      We require the estimate to be at least ``ESTIMATE_THRESHOLD`` rows
      before we trust it; for small/new tables we fall through to the
      exact count.
    - **Filtered queryset, or any non-Postgres backend, or an error
      reading the catalog**: fall back to the standard exact count.

    A filtered changelist (e.g. one log_level / one integration) can still
    issue an expensive count, but admin users hit those intentionally and
    the WHERE clause usually narrows the scan dramatically — the incident
    being fixed is the unfiltered index page.

    Subclasses can set ``estimate_through_baseline_filter = True`` to keep
    using the table-wide estimate even when the queryset already has a
    WHERE clause. This is intended for ModelAdmins whose default manager
    injects a baseline filter that doesn't actually narrow the data the
    user sees (e.g. ``ActivityLogManager.get_queryset()`` filters
    ``created_at <= now`` to skip empty future partitions). The trade-off
    is that user-applied filters then also pass through to the estimate,
    so filtered counts may overcount — acceptable for the changelist
    incident this PR exists to fix; the page loads instead of stalling
    on COUNT(*).
    """

    # Below this estimate, prefer the exact count: small tables count
    # cheaply and the catalog estimate can be wildly wrong before the
    # first ANALYZE (Postgres seeds it at -1 / row width-based guesses).
    ESTIMATE_THRESHOLD = 1000

    # Opt-in escape hatch for ModelAdmins whose manager injects a baseline
    # WHERE clause. See class docstring for the trade-off.
    estimate_through_baseline_filter = False

    @cached_property
    def count(self):
        query = self.object_list.query
        where_ok = self.estimate_through_baseline_filter or not query.where
        if (
            connection.vendor == "postgresql"
            and where_ok
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
        if the catalog read fails or returns no row.

        Uses ``pg_partition_tree`` so this works for both regular and
        partitioned tables in a single query: for a partitioned table the
        function returns one row per partition (parent + children) and we
        sum ``reltuples`` across the leaves; for a non-partitioned table
        the function returns a single row whose ``relid`` is the table
        itself, so the same SUM yields the table's own ``reltuples``.
        ``pg_partition_tree`` requires Postgres 10+; the project runs 12+.

        Pulled out as a seam so tests can mock the estimate without
        colliding with the cursor used by the exact-count fallback.
        """
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT COALESCE(SUM(c.reltuples), 0)::bigint
                    FROM pg_partition_tree(%s::regclass) p
                    JOIN pg_class c ON c.oid = p.relid
                    WHERE p.isleaf
                    """,
                    [table_name],
                )
                row = cursor.fetchone()
        except Exception:
            logger.warning(
                "EstimatedCountPaginator: pg_partition_tree/pg_class lookup "
                "failed for %s; falling back to exact COUNT(*).",
                table_name,
                exc_info=True,
            )
            return None
        if row is None or row[0] is None:
            return None
        return int(row[0])
