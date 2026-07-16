from pathlib import Path

import pytest

from pipeline.revisions import diff_vintages, observations_from_vintage

RAW = Path(__file__).resolve().parents[1] / "data" / "raw"
BEFORE, AFTER = RAW / "2026-07-14", RAW / "2026-07-15"

pytestmark = pytest.mark.skipif(
    not (BEFORE.exists() and AFTER.exists()),
    reason="the two seed vintages are not present in this checkout",
)


def test_real_vintages_report_no_revisions():
    # One day apart. Daily series appended; nothing was restated. If this ever fails,
    # either Valet really revised something or the differ has a false positive.
    events = diff_vintages(
        observations_from_vintage(BEFORE),
        observations_from_vintage(AFTER),
        detected_at="2026-07-15",
    )
    assert events == []


def test_series_added_by_plan_2_is_not_reported_as_anything():
    # STATIC_TOTALCPICHANGE exists only in the 07-15 vintage. Config churn is not a
    # BoC revision - and the inverse (removing a series) must not fire ~6384 fake
    # withdrawals.
    before = observations_from_vintage(BEFORE)
    after = observations_from_vintage(AFTER)
    assert not any(sid == "STATIC_TOTALCPICHANGE" for sid, _ in before)
    assert any(sid == "STATIC_TOTALCPICHANGE" for sid, _ in after)
    events = diff_vintages(before, after, detected_at="2026-07-15")
    assert [e for e in events if e.series_id == "STATIC_TOTALCPICHANGE"] == []


def test_new_daily_observations_are_not_revisions():
    before = observations_from_vintage(BEFORE)
    after = observations_from_vintage(AFTER)
    added = set(after) - set(before)
    assert {sid for sid, _ in added} == {
        "AVG.INTWO",
        "BD.CDN.2YR.DQ.YLD",
        "BD.CDN.5YR.DQ.YLD",
        "BD.CDN.10YR.DQ.YLD",
        "V39079",
        "STATIC_TOTALCPICHANGE",
    }
    assert diff_vintages(before, after, detected_at="2026-07-15") == []


def test_a_vintage_diffed_against_itself_is_silent():
    snapshot = observations_from_vintage(AFTER)
    assert diff_vintages(snapshot, snapshot, detected_at="2026-07-15") == []
