from pipeline.metrics import compute_household_spread, compute_yield_slope
from pipeline.models import AppConfig, SeriesConfig, Thresholds
from pipeline.transform import build_curated_con

ROWS = [
    {"series_id": "Y2", "obs_date": "2026-07-13", "value": "3.00"},
    {"series_id": "Y10", "obs_date": "2026-07-13", "value": "2.50"},
    {"series_id": "Y5", "obs_date": "2026-07-10", "value": "2.80"},
    {"series_id": "MTG", "obs_date": "2026-07-31", "value": "5.30"},
]


def _cfg() -> AppConfig:
    def mk(i, k):
        return SeriesConfig(id=i, label_en=i, label_fr=i, frequency="daily", role="yield", metric_key=k)

    return AppConfig(
        start_date="2000-01-01",
        series=[mk("Y2", "yield_2y"), mk("Y10", "yield_10y"), mk("Y5", "yield_5y"),
                SeriesConfig(id="MTG", label_en="m", label_fr="m", frequency="monthly",
                             role="lending", metric_key="mortgage_5y_fixed")],
        thresholds=Thresholds(staleness_days={"daily": 7}, max_null_ratio=0.2, value_ranges={}),
    )


def test_yield_slope_and_inversion():
    con = build_curated_con(ROWS, _cfg(), ingested_at="2026-07-14T00:00:00")
    slope = compute_yield_slope(con, "Y2", "Y10")
    assert slope == [{"date": "2026-07-13", "slope": -0.5, "inverted": True}]


def test_household_spread_asof_prior_yield():
    con = build_curated_con(ROWS, _cfg(), ingested_at="2026-07-14T00:00:00")
    spread = compute_household_spread(con, "MTG", "Y5")
    assert spread == [{"date": "2026-07-31", "spread": 2.5}]
