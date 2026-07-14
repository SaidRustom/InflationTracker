from pipeline.models import AppConfig, SeriesConfig, Thresholds
from pipeline.transform import build_curated_con, write_curated


def _cfg() -> AppConfig:
    return AppConfig(
        start_date="2000-01-01",
        series=[SeriesConfig(id="V39079", label_en="Policy", label_fr="Politique",
                             frequency="daily", role="policy")],
        thresholds=Thresholds(staleness_days={"daily": 7}, max_null_ratio=0.2, value_ranges={}),
    )


ROWS = [
    {"series_id": "V39079", "obs_date": "2026-07-10", "value": "2.25"},
    {"series_id": "V39079", "obs_date": "2026-07-13", "value": None},
    {"series_id": "V39079", "obs_date": "2026-07-13", "value": None},
]


def test_fact_types_dedup_and_null_flag():
    con = build_curated_con(ROWS, _cfg(), ingested_at="2026-07-14T00:00:00")
    facts = con.execute(
        "SELECT date::VARCHAR, value, is_null FROM fact_observation ORDER BY date"
    ).fetchall()
    assert facts == [("2026-07-10", 2.25, False), ("2026-07-13", None, True)]


def test_dim_series_carries_bilingual_labels():
    con = build_curated_con(ROWS, _cfg(), ingested_at="2026-07-14T00:00:00")
    row = con.execute(
        "SELECT label_en, label_fr, role FROM dim_series WHERE series_id = 'V39079'"
    ).fetchone()
    assert row == ("Policy", "Politique", "policy")


def test_write_curated_emits_parquet(tmp_path):
    con = build_curated_con(ROWS, _cfg(), ingested_at="2026-07-14T00:00:00")
    write_curated(con, tmp_path)
    assert (tmp_path / "fact_observation.parquet").exists()
    assert (tmp_path / "dim_series.parquet").exists()
