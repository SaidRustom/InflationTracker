import json
from pathlib import Path

import duckdb

from pipeline.models import AppConfig


def series_points(con: duckdb.DuckDBPyConnection, series_id: str) -> list[list]:
    rows = con.execute(
        "SELECT date::VARCHAR, value FROM fact_observation WHERE series_id = ? ORDER BY date",
        [series_id],
    ).fetchall()
    return [[d, v] for d, v in rows]


def _series_block(con: duckdb.DuckDBPyConnection, s) -> dict:
    return {
        "id": s.id,
        "label_en": s.label_en,
        "label_fr": s.label_fr,
        "role": s.role,
        "points": series_points(con, s.id),
    }


def _write(out_dir: Path, name: str, payload: dict) -> Path:
    path = out_dir / name
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def revisions_payload(config: AppConfig, revisions: dict | None) -> dict:
    """Cap the published event list, enrich with EN/FR labels, always state the total.

    The ledger stays label-free and complete; this is the view. total_events is what
    lets the page say "showing 100 of 342" instead of silently truncating.
    """
    if revisions is None:
        return {"watching_since": None, "last_checked": None, "events": [], "total_events": 0}

    labels = {s.id: (s.label_en, s.label_fr) for s in config.series}
    events = revisions.get("events", [])
    limit = config.revisions.publish_limit
    recent = list(reversed(events[-limit:]))  # newest first

    enriched = []
    for e in recent:
        label_en, label_fr = labels.get(e["series_id"], (e["series_id"], e["series_id"]))
        enriched.append({**e, "label_en": label_en, "label_fr": label_fr})

    return {
        "watching_since": revisions.get("watching_since"),
        "last_checked": revisions.get("last_checked"),
        "events": enriched,
        "total_events": len(events),
    }


def build_web(
    con: duckdb.DuckDBPyConnection,
    config: AppConfig,
    metrics: dict,
    quality: dict,
    out_dir: Path,
    as_of: str,
    revisions: dict | None = None,
) -> list[Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    by_role: dict[str, list] = {}
    for s in config.series:
        by_role.setdefault(s.role, []).append(s)

    paths: list[Path] = []
    paths.append(_write(out_dir, "panel_policy.json", {
        "series": [_series_block(con, s) for s in by_role.get("policy", []) + by_role.get("funding", [])],
    }))
    paths.append(_write(out_dir, "panel_markets.json", {
        "yields": [_series_block(con, s) for s in by_role.get("yield", [])],
        "policy": [_series_block(con, s) for s in by_role.get("policy", [])],
        "yield_slope": metrics["yield_slope"],
    }))
    paths.append(_write(out_dir, "panel_households.json", {
        "lending": [_series_block(con, s) for s in by_role.get("lending", [])],
        "yield5": [_series_block(con, s) for s in config.series if s.metric_key == "yield_5y"],
        "spread": metrics["household_spread"],
    }))
    paths.append(_write(out_dir, "panel_target.json", {
        "headline": [_series_block(con, s) for s in by_role.get("headline", [])],
        "core": [_series_block(con, s) for s in by_role.get("inflation", [])],
        "band": {"low": config.inflation_band.low, "high": config.inflation_band.high},
        "band_months": metrics["band_months"],
    }))
    paths.append(_write(out_dir, "data_quality.json", quality))
    paths.append(_write(out_dir, "revisions.json", revisions_payload(config, revisions)))
    paths.append(_write(out_dir, "manifest.json", {
        "as_of": as_of,
        "last_refreshed": quality.get("generated_at", f"{as_of}T00:00:00"),
        "overall_quality": quality.get("overall", "OK"),
        "panels": ["policy", "markets", "households", "target"],
        "revisions": "revisions.json",
    }))
    return paths
