import json
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

import duckdb

from pipeline.models import AppConfig

_ORDER = {"OK": 0, "WARN": 1, "FAIL": 2}


def _worst(statuses: list[str]) -> str:
    return max(statuses, key=lambda s: _ORDER[s]) if statuses else "OK"


@dataclass
class SeriesQuality:
    series_id: str
    status: str
    checks: dict[str, str]


@dataclass
class QualityReport:
    generated_at: str
    overall: str
    series: list[SeriesQuality]


def run_quality(con: duckdb.DuckDBPyConnection, config: AppConfig, as_of: str) -> QualityReport:
    as_of_date = date.fromisoformat(as_of)
    results: list[SeriesQuality] = []
    for s in config.series:
        stats = con.execute(
            "SELECT count(*), count(*) FILTER (WHERE is_null), "
            "max(date) FILTER (WHERE NOT is_null), "
            "min(value), max(value), count(DISTINCT date) "
            "FROM fact_observation WHERE series_id = ?",
            [s.id],
        ).fetchone()
        total, nulls, latest, vmin, vmax, distinct_dates = stats
        checks: dict[str, str] = {}
        statuses: list[str] = []

        limit = config.thresholds.staleness_days.get(s.frequency, 9999)
        if latest is None:
            checks["freshness"] = "no non-null observations"
            statuses.append("FAIL")
        else:
            age = (as_of_date - latest).days
            if age > limit:
                checks["freshness"] = f"not fresh: {age}d old (> {limit}d)"
                statuses.append("FAIL")
            else:
                checks["freshness"] = f"fresh: {age}d old"
                statuses.append("OK")

        lo, hi = config.thresholds.value_ranges.get(s.role, (float("-inf"), float("inf")))
        if vmin is not None and (vmin < lo or vmax > hi):
            checks["value_range"] = f"out of [{lo}, {hi}]: min={vmin}, max={vmax}"
            statuses.append("FAIL")
        else:
            checks["value_range"] = "within range"
            statuses.append("OK")

        if total != distinct_dates:
            checks["monotonic"] = f"duplicate dates: {total - distinct_dates}"
            statuses.append("FAIL")
        else:
            checks["monotonic"] = "no duplicate dates"
            statuses.append("OK")

        ratio = (nulls / total) if total else 0.0
        if ratio > config.thresholds.max_null_ratio:
            checks["null_ratio"] = f"high nulls: {ratio:.0%}"
            statuses.append("WARN")
        else:
            checks["null_ratio"] = f"nulls: {ratio:.0%}"
            statuses.append("OK")

        results.append(SeriesQuality(series_id=s.id, status=_worst(statuses), checks=checks))

    return QualityReport(
        generated_at=f"{as_of}T00:00:00",
        overall=_worst([r.status for r in results]),
        series=results,
    )


def report_to_dict(report: QualityReport) -> dict:
    return asdict(report)


def write_report(report: QualityReport, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report_to_dict(report), ensure_ascii=False, indent=2), encoding="utf-8")
