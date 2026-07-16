import json
import pytest
from pathlib import Path

from pipeline.revisions import (
    Ledger,
    RevisionEvent,
    RevisionLedgerError,
    append_events,
    diff_vintages,
    ledger_to_dict,
    load_ledger,
    observations_from_vintage,
    write_ledger,
)


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


def _event(detected_at="2026-06-20", old=2.9, new=3.1) -> RevisionEvent:
    return RevisionEvent("S", "2026-03-01", "revised", old, new, detected_at)


def test_first_run_creates_ledger_with_watching_since(tmp_path):
    ledger: Ledger = load_ledger(tmp_path / "revisions.json", default_watching_since="2026-07-14")
    assert ledger.watching_since == "2026-07-14"
    assert ledger.events == []


def test_watching_since_never_mutates(tmp_path):
    path = tmp_path / "revisions.json"
    write_ledger(load_ledger(path, default_watching_since="2026-07-14"), path)
    # A later run passes a different default; the stored value must win.
    ledger = load_ledger(path, default_watching_since="2026-09-01")
    ledger = append_events(ledger, [_event()], last_checked="2026-09-01")
    assert ledger.watching_since == "2026-07-14"


def test_append_is_idempotent_for_the_same_run(tmp_path):
    ledger = load_ledger(tmp_path / "l.json", default_watching_since="2026-07-14")
    ledger = append_events(ledger, [_event()], last_checked="2026-06-20")
    ledger = append_events(ledger, [_event()], last_checked="2026-06-20")
    assert len(ledger.events) == 1


def test_same_observation_revised_again_later_is_a_new_row(tmp_path):
    ledger = load_ledger(tmp_path / "l.json", default_watching_since="2026-07-14")
    ledger = append_events(ledger, [_event(detected_at="2026-06-20")], last_checked="2026-06-20")
    ledger = append_events(
        ledger,
        [_event(detected_at="2026-07-20", old=3.1, new=3.0)],
        last_checked="2026-07-20",
    )
    assert len(ledger.events) == 2


def test_last_checked_advances(tmp_path):
    ledger = load_ledger(tmp_path / "l.json", default_watching_since="2026-07-14")
    ledger = append_events(ledger, [], last_checked="2026-07-16")
    assert ledger.last_checked == "2026-07-16"


def test_ledger_roundtrips(tmp_path):
    path = tmp_path / "revisions.json"
    ledger = append_events(
        load_ledger(path, default_watching_since="2026-07-14"),
        [_event()],
        last_checked="2026-06-20",
    )
    write_ledger(ledger, path)
    reloaded = load_ledger(path, default_watching_since="ignored")
    assert reloaded == ledger
    assert ledger_to_dict(ledger)["events"][0]["kind"] == "revised"


def test_corrupt_ledger_raises_and_does_not_reset(tmp_path):
    path = tmp_path / "revisions.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(RevisionLedgerError):
        load_ledger(path, default_watching_since="2026-07-14")


def test_ledger_missing_required_key_raises(tmp_path):
    path = tmp_path / "revisions.json"
    path.write_text('{"events": []}', encoding="utf-8")
    with pytest.raises(RevisionLedgerError):
        load_ledger(path, default_watching_since="2026-07-14")


def test_ledger_with_malformed_event_raises(tmp_path):
    path = tmp_path / "revisions.json"
    # Event is missing required 'kind' field
    path.write_text(
        '{"watching_since": "2026-07-14", "last_checked": "2026-07-14", "events": [{"series_id": "S"}]}',
        encoding="utf-8",
    )
    with pytest.raises(RevisionLedgerError):
        load_ledger(path, default_watching_since="2026-07-14")


def test_ledger_with_non_list_events_raises(tmp_path):
    path = tmp_path / "revisions.json"
    # events is a dict, not a list
    path.write_text(
        '{"watching_since": "2026-07-14", "last_checked": "2026-07-14", "events": {}}',
        encoding="utf-8",
    )
    with pytest.raises(RevisionLedgerError):
        load_ledger(path, default_watching_since="2026-07-14")


def test_ledger_that_is_not_an_object_raises(tmp_path):
    path = tmp_path / "revisions.json"
    # Entire file is null instead of an object
    path.write_text("null", encoding="utf-8")
    with pytest.raises(RevisionLedgerError):
        load_ledger(path, default_watching_since="2026-07-14")
