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
        intervals AS (  -- Intervals rounded to nearest 10 minutes
            SELECT 
                data_provider_id,
                spike_start,
                LEAD(spike_start) OVER (PARTITION BY data_provider_id ORDER BY spike_start) AS next_spike_start,
                ROUND(EXTRACT(EPOCH FROM (LEAD(spike_start) OVER (PARTITION BY data_provider_id ORDER BY spike_start) - spike_start)) / 60 / 10) * 10 AS rounded_interval_minutes  -- Round to nearest 10 minutes
            FROM grouped_spikes
        )
        SELECT 
            MIN(rounded_interval_minutes) AS min_gap_minutes,  
            MAX(rounded_interval_minutes) AS max_gap_minutes,  
            mode() WITHIN GROUP (ORDER BY rounded_interval_minutes) AS typical_interval_minutes  
        FROM intervals;
    """

    with connection.cursor() as cursor:
        cursor.execute(query, [str(data_provider_id)])
        result = cursor.fetchone()
    f_min, f_max, f_typ = result if result else (None, None, None)
    return f_min, f_max, f_typ
