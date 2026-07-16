import json
from pathlib import Path

from pipeline.revisions import RevisionEvent, diff_vintages, observations_from_vintage


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


def test_changed_value_is_a_revision():
    events = diff_vintages(
        {("S", "2026-03-01"): 2.9},
        {("S", "2026-03-01"): 3.1},
        detected_at="2026-06-20",
    )
    assert events == [
        RevisionEvent("S", "2026-03-01", "revised", 2.9, 3.1, "2026-06-20")
    ]


def test_null_becoming_a_value_is_a_late_publication():
    events = diff_vintages(
        {("S", "2026-03-01"): None},
        {("S", "2026-03-01"): 3.1},
        detected_at="2026-06-20",
    )
    assert [e.kind for e in events] == ["late_publication"]
    assert events[0].old is None and events[0].new == 3.1


def test_value_becoming_null_is_a_withdrawal():
    events = diff_vintages(
        {("S", "2026-03-01"): 3.1},
        {("S", "2026-03-01"): None},
        detected_at="2026-06-20",
    )
    assert [e.kind for e in events] == ["withdrawn"]
    assert events[0].old == 3.1 and events[0].new is None


def test_vanished_date_is_a_withdrawal():
    events = diff_vintages(
        {("S", "2026-03-01"): 3.1, ("S", "2026-04-01"): 3.2},
        {("S", "2026-04-01"): 3.2},
        detected_at="2026-06-20",
    )
    assert [(e.date, e.kind) for e in events] == [("2026-03-01", "withdrawn")]


def test_vanished_null_date_is_not_an_event():
    # Nothing was ever published for that date, so nothing was withdrawn.
    events = diff_vintages(
        {("S", "2026-03-01"): None, ("S", "2026-04-01"): 3.2},
        {("S", "2026-04-01"): 3.2},
        detected_at="2026-06-20",
    )
    assert events == []


def test_new_observation_is_not_an_event():
    events = diff_vintages(
        {("S", "2026-03-01"): 2.9},
        {("S", "2026-03-01"): 2.9, ("S", "2026-04-01"): 3.0},
        detected_at="2026-06-20",
    )
    assert events == []


def test_unchanged_and_null_to_null_are_not_events():
    events = diff_vintages(
        {("S", "2026-03-01"): 2.9, ("S", "2026-04-01"): None},
        {("S", "2026-03-01"): 2.9, ("S", "2026-04-01"): None},
        detected_at="2026-06-20",
    )
    assert events == []


def test_series_present_in_only_one_vintage_is_skipped():
    # STATIC_TOTALCPICHANGE exists only in the 2026-07-15 vintage because Plan 2
    # added it. Config churn is not a BoC revision. Without this rule, REMOVING a
    # series from config would fire one fake withdrawal per observation.
    events = diff_vintages(
        {("OLD", "2026-03-01"): 1.0},
        {("NEW", "2026-03-01"): 2.0},
        detected_at="2026-06-20",
    )
    assert events == []


def test_events_are_ordered_by_series_then_date():
    events = diff_vintages(
        {("B", "2026-02-01"): 1.0, ("A", "2026-03-01"): 1.0, ("A", "2026-01-01"): 1.0},
        {("B", "2026-02-01"): 9.0, ("A", "2026-03-01"): 9.0, ("A", "2026-01-01"): 9.0},
        detected_at="2026-06-20",
    )
    assert [(e.series_id, e.date) for e in events] == [
        ("A", "2026-01-01"), ("A", "2026-03-01"), ("B", "2026-02-01"),
    ]
