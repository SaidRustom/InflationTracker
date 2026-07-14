-- Requires temp tables: stg_observation(series_id, obs_date, value) and
-- a session variable 'ingested_at'. Produces fact_observation.
CREATE OR REPLACE TABLE fact_observation AS
SELECT
    series_id,
    CAST(obs_date AS DATE)                          AS date,
    TRY_CAST(value AS DOUBLE)                       AS value,
    (TRY_CAST(value AS DOUBLE) IS NULL)             AS is_null,
    CAST(getvariable('ingested_at') AS TIMESTAMP)   AS ingested_at
FROM stg_observation
WHERE obs_date IS NOT NULL
QUALIFY row_number() OVER (
    PARTITION BY series_id, obs_date
    ORDER BY TRY_CAST(value AS DOUBLE) DESC NULLS LAST
) = 1
ORDER BY series_id, date;
