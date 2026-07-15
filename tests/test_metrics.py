from pipeline.metrics import compute_band_months, compute_household_spread, compute_yield_slope
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


BAND_ROWS = [
    {"series_id": "CPI", "obs_date": "2026-02-01", "value": "1.8"},
    {"series_id": "CPI", "obs_date": "2026-03-01", "value": "2.4"},
    {"series_id": "CPI", "obs_date": "2026-04-01", "value": "2.8"},
    {"series_id": "CPI", "obs_date": "2026-05-01", "value": "3.2"},
]


def _band_cfg() -> AppConfig:
    return AppConfig(
        start_date="2000-01-01",
        series=[SeriesConfig(id="CPI", label_en="c", label_fr="c", frequency="monthly",
                            role="headline", metric_key="cpi_headline")],
        thresholds=Thresholds(staleness_days={"monthly": 95}, max_null_ratio=0.2, value_ranges={}),
    )


def test_band_months_zero_when_latest_is_outside():
    con = build_curated_con(BAND_ROWS, _band_cfg(), ingested_at="2026-07-14T00:00:00")
    assert compute_band_months(con, "CPI", 1.0, 3.0) == {
        "months_inside": 0,
        "latest_date": "2026-05-01",
        "latest_value": 3.2,
        "latest_inside": False,
    }


def test_band_months_counts_consecutive_recent_months_inside():
    con = build_curated_con(BAND_ROWS[:3], _band_cfg(), ingested_at="2026-07-14T00:00:00")
    result = compute_band_months(con, "CPI", 1.0, 3.0)
    assert result["months_inside"] == 3
    assert result["latest_inside"] is True


def test_band_months_streak_stops_at_first_breach():
    rows = [{"series_id": "CPI", "obs_date": "2026-01-01", "value": "5.0"}] + BAND_ROWS[:3]
    con = build_curated_con(rows, _band_cfg(), ingested_at="2026-07-14T00:00:00")
    # 5.0 in Jan breaches, so the streak counts only Feb-Apr, not back through it.
    assert compute_band_months(con, "CPI", 1.0, 3.0)["months_inside"] == 3


def test_band_months_handles_empty_series():
    con = build_curated_con([], _band_cfg(), ingested_at="2026-07-14T00:00:00")
    assert compute_band_months(con, "CPI", 1.0, 3.0) == {
        "months_inside": 0,
        "latest_date": None,
        "latest_value": None,
        "latest_inside": False,
    }
