import json

from pipeline.build_web import build_web, series_points
from pipeline.metrics import run_metrics
from pipeline.models import AppConfig, SeriesConfig, Thresholds
from pipeline.quality import report_to_dict, run_quality
from pipeline.transform import build_curated_con

ROWS = [
    {"series_id": "V39079", "obs_date": "2026-07-13", "value": "2.25"},
    {"series_id": "BD.CDN.2YR.DQ.YLD", "obs_date": "2026-07-13", "value": "3.0"},
    {"series_id": "BD.CDN.5YR.DQ.YLD", "obs_date": "2026-07-13", "value": "3.2"},
    {"series_id": "BD.CDN.10YR.DQ.YLD", "obs_date": "2026-07-13", "value": "3.5"},
    {"series_id": "V122667780", "obs_date": "2026-07-31", "value": "5.3"},
    {"series_id": "CPI_TRIM", "obs_date": "2026-06-30", "value": "2.4"},
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
