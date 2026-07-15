import json
from pathlib import Path

from pipeline.models import AppConfig, SeriesConfig, Thresholds, load_config
from pipeline.quality import report_to_dict, run_quality, write_report
from pipeline.transform import build_curated_con


def _cfg(role="policy", freq="daily") -> AppConfig:
    return AppConfig(
        start_date="2000-01-01",
        series=[SeriesConfig(id="S", label_en="s", label_fr="s", frequency=freq, role=role)],
        thresholds=Thresholds(
            staleness_days={"daily": 7, "monthly": 75},
            max_null_ratio=0.20,
            value_ranges={"policy": (-1.0, 25.0)},
        ),
    )


def _con(rows):
    return build_curated_con(rows, _cfg(), ingested_at="2026-07-14T00:00:00")


def test_fresh_in_range_is_ok():
    con = _con([{"series_id": "S", "obs_date": "2026-07-13", "value": "2.25"}])
    report = run_quality(con, _cfg(), as_of="2026-07-14")
    assert report.overall == "OK"


def test_stale_series_fails():
    con = _con([{"series_id": "S", "obs_date": "2026-01-01", "value": "2.25"}])
    report = run_quality(con, _cfg(), as_of="2026-07-14")
    assert report.series[0].status == "FAIL"
    assert "fresh" in report.series[0].checks["freshness"].lower()


def test_out_of_range_fails():
    con = _con([{"series_id": "S", "obs_date": "2026-07-13", "value": "999"}])
    report = run_quality(con, _cfg(), as_of="2026-07-14")
    assert report.series[0].status == "FAIL"


def test_high_null_ratio_warns():
    rows = [{"series_id": "S", "obs_date": f"2026-07-{d:02d}", "value": None} for d in (10, 11, 12)]
    rows.append({"series_id": "S", "obs_date": "2026-07-13", "value": "2.25"})
    con = _con(rows)
    report = run_quality(con, _cfg(), as_of="2026-07-14")
    assert report.series[0].status == "WARN"


def test_write_report_roundtrips(tmp_path):
    con = _con([{"series_id": "S", "obs_date": "2026-07-13", "value": "2.25"}])
    report = run_quality(con, _cfg(), as_of="2026-07-14")
    write_report(report, tmp_path / "dq.json")
    loaded = json.loads((tmp_path / "dq.json").read_text(encoding="utf-8"))
    assert loaded["overall"] == "OK"
    assert loaded["series"][0]["series_id"] == "S"
    assert report_to_dict(report)["overall"] == "OK"


def _monthly_cfg() -> AppConfig:
    return AppConfig(
        start_date="2000-01-01",
        series=[SeriesConfig(id="S", label_en="s", label_fr="s", frequency="monthly", role="inflation")],
        thresholds=Thresholds(
            staleness_days={"daily": 7, "monthly": 95},
            max_null_ratio=0.20,
            value_ranges={"inflation": (-5.0, 25.0)},
        ),
    )


def test_monthly_series_inside_publication_lag_is_ok():
    # May CPI is dated 2026-05-01 and stays the newest observation until June CPI
    # publishes ~2026-07-17. ~77 days old is a normal cycle, not staleness.
    cfg = _monthly_cfg()
    con = build_curated_con(
        [{"series_id": "S", "obs_date": "2026-05-01", "value": "2.0"}],
        cfg,
        ingested_at="2026-07-16T00:00:00",
    )
    report = run_quality(con, cfg, as_of="2026-07-16")
    assert report.series[0].status == "OK"


def test_monthly_series_missing_two_releases_still_fails():
    # A monthly series that has skipped ~2 releases is genuinely stale and must alarm.
    cfg = _monthly_cfg()
    con = build_curated_con(
        [{"series_id": "S", "obs_date": "2026-03-01", "value": "2.0"}],
        cfg,
        ingested_at="2026-07-16T00:00:00",
    )
    report = run_quality(con, cfg, as_of="2026-07-16")
    assert report.series[0].status == "FAIL"


def test_shipped_config_monthly_threshold_survives_publication_lag():
    # Pins the real config file, which is where the bug lived.
    cfg_dir = Path(__file__).resolve().parents[1] / "config"
    cfg = load_config(cfg_dir / "series.yml", cfg_dir / "settings.yml")
    assert cfg.thresholds.staleness_days["monthly"] >= 80
