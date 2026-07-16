import json
from pathlib import Path

from pipeline.ingest import run_ingest
from pipeline.models import AppConfig, SeriesConfig, Thresholds


class FakeClient:
    def get_observations(self, name, kind="series", start=None, recent=None):
        return {"seriesDetail": {name: {}}, "observations": [{"d": "2026-07-13", name: {"v": "1.0"}}]}


def _cfg() -> AppConfig:
    return AppConfig(
        start_date="2000-01-01",
        series=[
            SeriesConfig(id="V39079", label_en="a", label_fr="a", frequency="daily", role="policy"),
            SeriesConfig(id="CPI_TRIM", label_en="b", label_fr="b", frequency="monthly", role="inflation"),
        ],
        thresholds=Thresholds(staleness_days={"daily": 7}, max_null_ratio=0.2, value_ranges={}),
    )


def test_run_ingest_writes_one_file_per_series(tmp_path: Path):
    paths = run_ingest(_cfg(), FakeClient(), tmp_path, "2026-07-13")
    assert {p.name for p in paths} == {"V39079.json", "CPI_TRIM.json"}
    body = json.loads((tmp_path / "2026-07-13" / "V39079.json").read_text(encoding="utf-8"))
    assert body["observations"][0]["d"] == "2026-07-13"


def test_run_ingest_writes_meta_json_with_the_fetch_params(tmp_path: Path):
    # detect_and_record diffs this file across vintages and skips detection when it
    # differs - a moved start_date must be visible, not silently unrecorded.
    run_ingest(_cfg(), FakeClient(), tmp_path, "2026-07-13")
    meta = json.loads((tmp_path / "2026-07-13" / "_meta.json").read_text(encoding="utf-8"))
    assert meta == {"start_date": "2000-01-01", "recent": None}
