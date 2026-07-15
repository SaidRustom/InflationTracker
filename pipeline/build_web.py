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


def build_web(
    con: duckdb.DuckDBPyConnection,
    config: AppConfig,
    metrics: dict,
    quality: dict,
    out_dir: Path,
    as_of: str,
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
    paths.append(_write(out_dir, "manifest.json", {
        "as_of": as_of,
        "last_refreshed": quality.get("generated_at", f"{as_of}T00:00:00"),
        "overall_quality": quality.get("overall", "OK"),
        "panels": ["policy", "markets", "households", "target"],
    }))
    return paths
