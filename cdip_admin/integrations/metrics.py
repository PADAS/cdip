from django.db import connection


def calculate_data_frequency(data_provider_id, exclude_duplicates=True, time_window_hours=24):
    """
    Calculates how often we receive data from an integration.
    """

    # Find the time intervals between traces
    lag_query = f"""
        SELECT 
            data_provider_id,
            created_at,
            LAG(created_at) OVER (PARTITION BY data_provider_id ORDER BY created_at) AS prev_created_at
        FROM integrations_gunditrace
        WHERE created_at >= NOW() - INTERVAL '{time_window_hours} hours' 
          AND data_provider_id = %s
    """
    if exclude_duplicates:
        lag_query += "AND is_duplicate = FALSE"
    # Find traffic spikes and gaps and get the minimum, maximum and typical interval between spikes
    query = f"""
        WITH lagged_data AS (
            {lag_query}
        ),
        spikes AS (
            SELECT 
                data_provider_id,
                created_at AS spike_start,
                SUM(
                    CASE 
                        WHEN prev_created_at IS NULL OR created_at - prev_created_at > INTERVAL '5 minutes' 
                        THEN 1 
                        ELSE 0 
                    END
                ) OVER (PARTITION BY data_provider_id ORDER BY created_at) AS spike_group
            FROM lagged_data
        ),
        grouped_spikes AS (
            SELECT 
                data_provider_id,
                spike_group,
                MIN(spike_start) AS spike_start
            FROM spikes
            GROUP BY data_provider_id, spike_group
        ),
        intervals AS (
            SELECT 
                data_provider_id,
                spike_start,
                LEAD(spike_start) OVER (PARTITION BY data_provider_id ORDER BY spike_start) AS next_spike_start,
                EXTRACT(EPOCH FROM (LEAD(spike_start) OVER (PARTITION BY data_provider_id ORDER BY spike_start) - spike_start)) / 60 AS interval_minutes
            FROM grouped_spikes
        )
        SELECT 
            ROUND(MIN(interval_minutes)) AS min_gap_minutes,  -- Smallest gap between spikes
            ROUND(MAX(interval_minutes)) AS max_gap_minutes,  -- Biggest gap in the last 24 hours
            ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY interval_minutes)) AS typical_interval_p95_minutes
        FROM intervals;
    """

    with connection.cursor() as cursor:
        cursor.execute(query, [str(data_provider_id)])
        result = cursor.fetchone()
    f_min, f_max, f_p95 = result if result else (None, None, None)
    return f_min, f_max, f_p95
