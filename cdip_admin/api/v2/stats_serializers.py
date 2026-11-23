from rest_framework import serializers

from activity_log.models import ActivityLog
from stats import queries as stats_queries


class GroupByField(serializers.CharField):
    """Comma-separated list of dimensions, e.g. `integration_type,data_type`."""

    def __init__(self, dimensions, **kwargs):
        self.dimensions = tuple(dimensions)
        kwargs.setdefault("required", False)
        kwargs.setdefault("allow_blank", True)
        kwargs.setdefault("help_text", f"Comma-separated dimensions: {', '.join(self.dimensions)}.")
        super().__init__(**kwargs)

    def to_internal_value(self, data):
        names = [name.strip() for name in super().to_internal_value(data).split(",") if name.strip()]
        unknown = [name for name in names if name not in self.dimensions]
        if unknown:
            raise serializers.ValidationError(
                f"Unknown dimension(s): {', '.join(unknown)}. Choose from: {', '.join(self.dimensions)}."
            )
        return list(dict.fromkeys(names))  # drop repeats, keep the order


class StatsQuerySerializer(serializers.Serializer):
    from_date = serializers.DateTimeField(
        required=False, help_text="Start of the range (ISO 8601). Defaults to 24 hours before to_date."
    )
    to_date = serializers.DateTimeField(
        required=False, help_text="End of the range, exclusive (ISO 8601). Defaults to now."
    )
    interval = serializers.ChoiceField(
        choices=stats_queries.INTERVALS, default="hour", help_text="Bucket size: hour or day (UTC)."
    )

    filter_fields = ()

    def validate(self, attrs):
        attrs["filters"] = {name: attrs[name] for name in self.filter_fields if attrs.get(name)}
        return attrs


class ThroughputStatsQuerySerializer(StatsQuerySerializer):
    group_by = GroupByField(stats_queries.THROUGHPUT_DIMENSIONS)
    integration_type = serializers.CharField(required=False, help_text="Integration type value of the data provider.")
    organization = serializers.UUIDField(required=False, help_text="Id of the organization owning the data provider.")
    data_provider = serializers.UUIDField(required=False, help_text="Id of the data provider integration.")
    destination = serializers.UUIDField(required=False, help_text="Id of the destination integration.")
    data_type = serializers.CharField(required=False, help_text="obv, ev, att or txt.")

    filter_fields = ("integration_type", "organization", "data_provider", "destination", "data_type")


class ErrorsStatsQuerySerializer(StatsQuerySerializer):
    group_by = GroupByField(stats_queries.ERRORS_DIMENSIONS)
    integration_type = serializers.CharField(required=False, help_text="Integration type value.")
    organization = serializers.UUIDField(required=False, help_text="Id of the organization owning the integration.")
    integration = serializers.UUIDField(required=False, help_text="Id of the integration the failure was logged for.")
    origin = serializers.ChoiceField(
        choices=ActivityLog.Origin.choices, required=False,
        help_text="Where the failure was logged: port, inte, tran or disp."
    )
    kind = serializers.CharField(required=False, help_text="Log value, e.g. observation_delivery_failed.")
    include_retriable = serializers.BooleanField(
        default=False, help_text="Also return failures the dispatcher will retry, as a separate count."
    )

    filter_fields = ("integration_type", "organization", "integration", "origin", "kind")


class UsageStatsQuerySerializer(StatsQuerySerializer):
    limit = serializers.IntegerField(
        default=stats_queries.DEFAULT_RANKING_LIMIT, min_value=1, max_value=stats_queries.MAX_RANKING_LIMIT,
        help_text="Number of entries in each ranking."
    )
