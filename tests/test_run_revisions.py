import json
from pathlib import Path

from pipeline.revisions import detect_and_record, load_ledger


def _vintage(root: Path, name: str, series_id: str, observations: list[tuple[str, str | None]]) -> Path:
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    body = {
        "seriesDetail": {series_id: {"label": series_id}},
        "observations": [
            {"d": date, series_id: ({} if value is None else {"v": value})}
            for date, value in observations
        ],
    }
    (d / f"{series_id}.json").write_text(json.dumps(body), encoding="utf-8")
    return d


def test_records_a_revision_between_two_vintages(tmp_path):
    raw = tmp_path / "raw"
    _vintage(raw, "2026-07-14", "S", [("2026-03-01", "2.9")])
    _vintage(raw, "2026-07-15", "S", [("2026-03-01", "3.1")])
    ledger = detect_and_record(raw, "2026-07-15", tmp_path / "revisions.json")
    assert [(e.kind, e.old, e.new, e.detected_at) for e in ledger.events] == [
        ("revised", 2.9, 3.1, "2026-07-15")
    ]
    assert ledger.watching_since == "2026-07-15"
    assert ledger.last_checked == "2026-07-15"


def test_first_run_has_no_baseline_and_records_nothing(tmp_path):
    raw = tmp_path / "raw"
    _vintage(raw, "2026-07-14", "S", [("2026-03-01", "2.9")])
    ledger = detect_and_record(raw, "2026-07-14", tmp_path / "revisions.json")
    assert ledger.events == []
    assert ledger.watching_since == "2026-07-14"


def test_detection_persists_and_prunes(tmp_path):
    raw = tmp_path / "raw"
    for name in ("2026-07-12", "2026-07-13", "2026-07-14"):
        _vintage(raw, name, "S", [("2026-03-01", "2.9")])
    _vintage(raw, "2026-07-15", "S", [("2026-03-01", "3.1")])
    path = tmp_path / "revisions.json"
    detect_and_record(raw, "2026-07-15", path)
    assert sorted(p.name for p in raw.iterdir()) == ["2026-07-14", "2026-07-15"]
    assert load_ledger(path, default_watching_since="x").events[0].kind == "revised"


def test_rerunning_the_same_run_date_does_not_duplicate(tmp_path):
    raw = tmp_path / "raw"
    _vintage(raw, "2026-07-14", "S", [("2026-03-01", "2.9")])
    _vintage(raw, "2026-07-15", "S", [("2026-03-01", "3.1")])
    path = tmp_path / "revisions.json"
    detect_and_record(raw, "2026-07-15", path)
    ledger = detect_and_record(raw, "2026-07-15", path)
    assert len(ledger.events) == 1
