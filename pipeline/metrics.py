import duckdb

from pipeline.models import AppConfig

_SLOPE_SQL = """
SELECT a.date::VARCHAR AS date,
       round(a.value - b.value, 10) AS slope,
       (a.value - b.value) < 0 AS inverted
FROM (SELECT date, value FROM fact_observation WHERE series_id = ? AND value IS NOT NULL) a
ASOF JOIN (SELECT date, value FROM fact_observation WHERE series_id = ? AND value IS NOT NULL) b
  ON a.date >= b.date
ORDER BY a.date
"""

_SPREAD_SQL = """
SELECT a.date::VARCHAR AS date,
       round(a.value - b.value, 10) AS spread
FROM (SELECT date, value FROM fact_observation WHERE series_id = ? AND value IS NOT NULL) a
ASOF JOIN (SELECT date, value FROM fact_observation WHERE series_id = ? AND value IS NOT NULL) b
  ON a.date >= b.date
ORDER BY a.date
"""


def compute_yield_slope(con: duckdb.DuckDBPyConnection, id_2y: str, id_10y: str) -> list[dict]:
    rows = con.execute(_SLOPE_SQL, [id_10y, id_2y]).fetchall()
    return [{"date": d, "slope": s, "inverted": bool(inv)} for d, s, inv in rows]


def compute_household_spread(con: duckdb.DuckDBPyConnection, id_mortgage: str, id_5y: str) -> list[dict]:
    rows = con.execute(_SPREAD_SQL, [id_mortgage, id_5y]).fetchall()
    return [{"date": d, "spread": s} for d, s in rows]


def compute_band_months(con: duckdb.DuckDBPyConnection, series_id: str, low: float, high: float) -> dict:
    rows = con.execute(
        "SELECT date::VARCHAR, value FROM fact_observation "
        "WHERE series_id = ? AND value IS NOT NULL ORDER BY date DESC",
        [series_id],
    ).fetchall()
    if not rows:
        return {"months_inside": 0, "latest_date": None, "latest_value": None, "latest_inside": False}
    streak = 0
    for _, value in rows:
        if low <= value <= high:
            streak += 1
        else:
            break
    latest_date, latest_value = rows[0]
    return {
        "months_inside": streak,
        "latest_date": latest_date,
        "latest_value": latest_value,
        "latest_inside": low <= latest_value <= high,
    }


def run_metrics(con: duckdb.DuckDBPyConnection, config: AppConfig) -> dict:
    band = config.inflation_band
    return {
        "yield_slope": compute_yield_slope(
            con, config.by_metric_key("yield_2y").id, config.by_metric_key("yield_10y").id
        ),
        "household_spread": compute_household_spread(
            con, config.by_metric_key("mortgage_5y_fixed").id, config.by_metric_key("yield_5y").id
        ),
        "band_months": compute_band_months(
            con, config.by_metric_key("cpi_headline").id, band.low, band.high
        ),
    }
