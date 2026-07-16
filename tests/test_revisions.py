import json
from pathlib import Path

from pipeline.revisions import observations_from_vintage


def _vintage(tmp_path: Path, name: str, series_id: str, observations: list[tuple[str, str | None]]) -> Path:
    """Write one raw vintage dir holding a single series file in Valet's shape."""
    d = tmp_path / name
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


def test_observations_are_cast_to_float(tmp_path):
    d = _vintage(tmp_path, "2026-07-15", "CPI_TRIM", [("2026-03-01", "2.9")])
    assert observations_from_vintage(d) == {("CPI_TRIM", "2026-03-01"): 2.9}


def test_trailing_zero_is_not_a_difference(tmp_path):
    # The trap: "1.50" and "1.5" are different strings and the same number.
    a = _vintage(tmp_path, "a", "S", [("2026-01-01", "1.50")])
    b = _vintage(tmp_path, "b", "S", [("2026-01-01", "1.5")])
    assert observations_from_vintage(a) == observations_from_vintage(b)


def test_missing_value_becomes_none(tmp_path):
    d = _vintage(tmp_path, "2026-07-15", "S", [("2026-01-01", None)])
    assert observations_from_vintage(d) == {("S", "2026-01-01"): None}


def test_reads_every_series_file_in_the_vintage(tmp_path):
    d = _vintage(tmp_path, "v", "A", [("2026-01-01", "1.0")])
    _vintage(tmp_path, "v", "B", [("2026-01-01", "2.0")])
    assert observations_from_vintage(d) == {
        ("A", "2026-01-01"): 1.0,
        ("B", "2026-01-01"): 2.0,
    }
