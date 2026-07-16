import json
from pathlib import Path

from pipeline.revisions import Ledger, detect_and_record, load_ledger, write_ledger
from pipeline.run import main
from pipeline.valet_client import ValetError

# metric_key -> (series id, role, frequency). run_metrics resolves these five metric_keys
# via config.by_metric_key(...); it only needs them to EXIST, not to carry real history -
# one observation each is enough for main() to complete.
_SERIES = [
    ("Y2", "yield_2y", "yield", "daily"),
    ("Y5", "yield_5y", "yield", "daily"),
    ("Y10", "yield_10y", "yield", "daily"),
    ("MTG", "mortgage_5y_fixed", "lending", "monthly"),
    ("CPI", "cpi_headline", "headline", "monthly"),
]


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


# --- Tests below drive pipeline.run.main() end-to-end, to pin the reached_source gate
# itself (not just detect_and_record in isolation). main() takes its own --config-dir, so
# these tests supply a synthetic one-observation vintage instead of the repo's real
# data/raw - real data has 31,698 rows, and build_curated_con's executemany takes ~80s
# against it, which would make this file alone take minutes. But if the gate is ever
# broken, detect_and_record -> prune_vintages -> shutil.rmtree would still run against
# whatever --raw-root points at - so the safety here is that the fixture is synthetic
# and entirely under tmp_path, never the real data/raw/2026-07-14 / 2026-07-15 vintages
# that are Task 7's regression fixture.


def _seed_pipeline(tmp_path: Path) -> tuple[Path, Path]:
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "series.yml").write_text(
        "series:\n"
        + "".join(
            f'  - {{id: "{i}", label_en: "{i}", label_fr: "{i}", '
            f'frequency: "{f}", role: "{r}", metric_key: "{m}"}}\n'
            for i, m, r, f in _SERIES
        ),
        encoding="utf-8",
    )
    (cfg / "settings.yml").write_text(
        'start_date: "2000-01-01"\n'
        "inflation_band: {low: 1.0, high: 3.0}\n"
        "thresholds:\n"
        "  staleness_days: {daily: 7, weekly: 14, monthly: 95}\n"
        "  max_null_ratio: 0.20\n"
        "  value_ranges:\n"
        "    yield: [-2.0, 25.0]\n"
        "    lending: [0.0, 30.0]\n"
        "    headline: [-5.0, 25.0]\n",
        encoding="utf-8",
    )
    raw = tmp_path / "raw"
    vintage = raw / "2026-07-15"
    vintage.mkdir(parents=True)
    for sid, *_ in _SERIES:
        (vintage / f"{sid}.json").write_text(
            json.dumps(
                {
                    "seriesDetail": {sid: {"label": sid}},
                    "observations": [{"d": "2026-07-14", sid: {"v": "2.0"}}],
                }
            ),
            encoding="utf-8",
        )
    return cfg, raw


def _main_argv(tmp_path: Path, cfg: Path, raw_root: Path, offline: bool = False) -> list[str]:
    argv = [
        "--config-dir", str(cfg),
        "--raw-root", str(raw_root),
        "--curated-dir", str(tmp_path / "curated"),
        "--web-dir", str(tmp_path / "web"),
        "--run-date", "2026-07-15",
        "--ingested-at", "2026-07-15T00:00:00",
    ]
    if offline:
        argv.append("--offline")
    return argv


def test_offline_run_does_not_detect(tmp_path, monkeypatch):
    cfg, raw = _seed_pipeline(tmp_path)
    calls = []
    monkeypatch.setattr("pipeline.run.detect_and_record", lambda *a, **k: calls.append((a, k)))

    rc = main(_main_argv(tmp_path, cfg, raw, offline=True))

    assert rc != 2
    assert calls == []


def test_valet_error_cache_fallback_does_not_detect(tmp_path, monkeypatch):
    cfg, raw = _seed_pipeline(tmp_path)  # cached raw for 2026-07-15 already exists, so main() falls back
    calls = []
    monkeypatch.setattr("pipeline.run.detect_and_record", lambda *a, **k: calls.append((a, k)))

    def _raise(*a, **k):
        raise ValetError("simulated Valet outage")

    monkeypatch.setattr("pipeline.run.run_ingest", _raise)

    rc = main(_main_argv(tmp_path, cfg, raw, offline=False))

    assert rc != 2  # confirms the fallback branch ran, not the no-cache return 2
    assert calls == []


def test_successful_ingest_does_detect(tmp_path, monkeypatch):
    """Positive control: without this, the two tests above would pass vacuously if
    main() crashed before reaching the gate, or if the monkeypatch target were wrong."""
    cfg, raw = _seed_pipeline(tmp_path)
    calls = []
    monkeypatch.setattr("pipeline.run.detect_and_record", lambda *a, **k: calls.append((a, k)))
    monkeypatch.setattr("pipeline.run.run_ingest", lambda *a, **k: None)

    rc = main(_main_argv(tmp_path, cfg, raw, offline=False))

    assert rc != 2
    assert len(calls) == 1


def test_offline_run_leaves_last_checked_unchanged(tmp_path):
    """The user-visible guarantee, asserted directly: with detect_and_record NOT
    patched, an --offline run must not advance last_checked in the published ledger."""
    cfg, raw = _seed_pipeline(tmp_path)
    curated = tmp_path / "curated"
    curated.mkdir(parents=True)
    ledger_path = curated / "revisions.json"
    write_ledger(
        Ledger(watching_since="2026-07-01", last_checked="2026-07-01", events=[]),
        ledger_path,
    )

    rc = main(_main_argv(tmp_path, cfg, raw, offline=True))

    assert rc != 2
    ledger = load_ledger(ledger_path, default_watching_since="unused")
    assert ledger.last_checked == "2026-07-01"
