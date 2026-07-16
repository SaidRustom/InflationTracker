import json

import pytest
from pydantic import ValidationError

from pipeline.build_web import build_web, series_points
from pipeline.metrics import run_metrics
from pipeline.models import AppConfig, RevisionsConfig, SeriesConfig, Thresholds
from pipeline.quality import report_to_dict, run_quality
from pipeline.transform import build_curated_con

ROWS = [
    {"series_id": "V39079", "obs_date": "2026-07-13", "value": "2.25"},
    {"series_id": "BD.CDN.2YR.DQ.YLD", "obs_date": "2026-07-13", "value": "3.0"},
    {"series_id": "BD.CDN.5YR.DQ.YLD", "obs_date": "2026-07-13", "value": "3.2"},
    {"series_id": "BD.CDN.10YR.DQ.YLD", "obs_date": "2026-07-13", "value": "3.5"},
    {"series_id": "V122667780", "obs_date": "2026-07-31", "value": "5.3"},
    {"series_id": "CPI_TRIM", "obs_date": "2026-06-30", "value": "2.4"},
    {"series_id": "STATIC_TOTALCPICHANGE", "obs_date": "2026-06-30", "value": "3.2"},
]


def _cfg() -> AppConfig:
    def y(i, k):
        return SeriesConfig(id=i, label_en=i, label_fr=i, frequency="daily", role="yield", metric_key=k)

    return AppConfig(
        start_date="2000-01-01",
        series=[
            SeriesConfig(id="V39079", label_en="Policy", label_fr="Politique", frequency="daily", role="policy"),
            y("BD.CDN.2YR.DQ.YLD", "yield_2y"),
            y("BD.CDN.5YR.DQ.YLD", "yield_5y"),
            y("BD.CDN.10YR.DQ.YLD", "yield_10y"),
            SeriesConfig(id="V122667780", label_en="Mtg", label_fr="Hyp", frequency="monthly",
                         role="lending", metric_key="mortgage_5y_fixed"),
            SeriesConfig(id="CPI_TRIM", label_en="Trim", label_fr="Tronq", frequency="monthly", role="inflation"),
            SeriesConfig(id="STATIC_TOTALCPICHANGE", label_en="Total CPI", label_fr="IPC global",
                         frequency="monthly", role="headline", metric_key="cpi_headline"),
        ],
        thresholds=Thresholds(
            staleness_days={"daily": 7, "monthly": 400},
            max_null_ratio=0.5,
            value_ranges={},
        ),
    )


def test_series_points_orders_by_date():
    con = build_curated_con(ROWS, _cfg(), ingested_at="2026-07-14T00:00:00")
    assert series_points(con, "V39079") == [["2026-07-13", 2.25]]


def test_build_web_emits_all_panels_and_manifest(tmp_path):
    cfg = _cfg()
    con = build_curated_con(ROWS, cfg, ingested_at="2026-07-14T00:00:00")
    metrics = run_metrics(con, cfg)
    quality = report_to_dict(run_quality(con, cfg, as_of="2026-07-14"))
    paths = build_web(con, cfg, metrics, quality, tmp_path, as_of="2026-07-14")
    names = {p.name for p in paths}
    assert {"panel_policy.json", "panel_markets.json", "panel_households.json",
            "panel_target.json", "data_quality.json", "manifest.json"} <= names
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["as_of"] == "2026-07-14"
    markets = json.loads((tmp_path / "panel_markets.json").read_text(encoding="utf-8"))
    assert markets["yield_slope"][0]["inverted"] is False


def test_panel_target_separates_headline_from_core(tmp_path):
    cfg = _cfg()
    con = build_curated_con(ROWS, cfg, ingested_at="2026-07-14T00:00:00")
    metrics = run_metrics(con, cfg)
    quality = report_to_dict(run_quality(con, cfg, as_of="2026-07-14"))
    build_web(con, cfg, metrics, quality, tmp_path, as_of="2026-07-14")
    target = json.loads((tmp_path / "panel_target.json").read_text(encoding="utf-8"))

    assert [s["id"] for s in target["headline"]] == ["STATIC_TOTALCPICHANGE"]
    assert target["headline"][0]["points"] == [["2026-06-30", 3.2]]
    # headline must not leak into core
    assert [s["id"] for s in target["core"]] == ["CPI_TRIM"]
    assert target["band"] == {"low": 1.0, "high": 3.0}
    assert target["band_months"]["latest_value"] == 3.2
    assert target["band_months"]["latest_inside"] is False
    assert target["band_months"]["months_inside"] == 0


def _rev_cfg(limit=100) -> AppConfig:
    return AppConfig(
        start_date="2000-01-01",
        series=[SeriesConfig(id="S", label_en="Series S", label_fr="Serie S", frequency="monthly", role="inflation")],
        thresholds=Thresholds(staleness_days={"monthly": 95}, max_null_ratio=0.2, value_ranges={"inflation": (-5.0, 25.0)}),
        revisions=RevisionsConfig(publish_limit=limit),
    )


def _ledger(n: int) -> dict:
    return {
        "watching_since": "2026-07-14",
        "last_checked": "2026-07-16",
        "events": [
            {"series_id": "S", "date": f"2026-{m:02d}-01", "kind": "revised",
             "old": 2.9, "new": 3.1, "detected_at": "2026-07-16"}
            for m in range(1, n + 1)
        ],
    }


def test_revisions_payload_is_enriched_with_labels():
    from pipeline.build_web import revisions_payload
    out = revisions_payload(_rev_cfg(), _ledger(1))
    assert out["events"][0]["label_en"] == "Series S"
    assert out["events"][0]["label_fr"] == "Serie S"
    assert out["watching_since"] == "2026-07-14"
    assert out["last_checked"] == "2026-07-16"


def test_publish_limit_caps_but_reports_the_total():
    from pipeline.build_web import revisions_payload
    out = revisions_payload(_rev_cfg(limit=2), _ledger(5))
    assert len(out["events"]) == 2
    assert out["total_events"] == 5  # no silent truncation


def test_published_events_are_newest_first():
    from pipeline.build_web import revisions_payload
    out = revisions_payload(_rev_cfg(limit=2), _ledger(5))
    assert [e["date"] for e in out["events"]] == ["2026-05-01", "2026-04-01"]


def test_no_ledger_yet_publishes_an_honest_empty_payload():
    from pipeline.build_web import revisions_payload
    out = revisions_payload(_rev_cfg(), None)
    assert out == {"watching_since": None, "last_checked": None, "events": [], "total_events": 0}


def test_shipped_config_carries_a_publish_limit():
    from pathlib import Path

    from pipeline.models import load_config
    cfg_dir = Path(__file__).resolve().parents[1] / "config"
    cfg = load_config(cfg_dir / "series.yml", cfg_dir / "settings.yml")
    assert cfg.revisions.publish_limit > 0


@pytest.mark.parametrize("limit", [0, -1])
def test_publish_limit_below_one_is_rejected(limit):
    # events[-limit:] with limit=0 is events[0:] - the ENTIRE ledger, not none of it.
    # publish_limit must be >= 1 so that footgun can never reach the slice.
    with pytest.raises(ValidationError):
        RevisionsConfig(publish_limit=limit)


def test_revisions_payload_falls_back_to_raw_id_for_series_removed_from_config():
    from pipeline.build_web import revisions_payload
    # The ledger is permanent; a series can be dropped from config after events
    # about it were recorded. label lookup must degrade to the raw id, not raise.
    ledger = {
        "watching_since": "2026-07-14",
        "last_checked": "2026-07-16",
        "events": [{"series_id": "GONE", "date": "2026-01-01", "kind": "revised",
                    "old": 2.9, "new": 3.1, "detected_at": "2026-07-16"}],
    }
    out = revisions_payload(_rev_cfg(), ledger)
    assert out["events"][0]["label_en"] == "GONE"
    assert out["events"][0]["label_fr"] == "GONE"
