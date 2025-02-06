from django.db import connection


def calculate_data_frequency(data_provider_id, exclude_duplicates=True, time_window_hours=24):
    """
    Calculates how often we receive data from an integration.
    """

    # Get the most typical interval between data points using percentiles (p95)
    data_intervals_query = f"""
            SELECT 
                EXTRACT(EPOCH FROM (created_at - LAG(created_at) OVER (PARTITION BY data_provider_id ORDER BY created_at))) / 60 AS interval_minutes
            FROM integrations_gunditrace
            WHERE created_at >= NOW() - INTERVAL '{time_window_hours} hours' 
              AND data_provider_id = %s
    """
    if exclude_duplicates:
        data_intervals_query += "AND is_duplicate = FALSE"
    query = f"""
        SELECT 
            ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY interval_minutes)) AS typical_interval_p95_minutes
        FROM (
            {data_intervals_query}
        ) AS intervals;
    """

    with connection.cursor() as cursor:
        cursor.execute(query, [str(data_provider_id)])
        result = cursor.fetchone()

    return result[0] if result else None
