from pipeline.parse import flatten_observations


def test_flatten_single_series():
    raw = {"observations": [{"d": "2026-07-13", "V39079": {"v": "2.25"}}]}
    assert flatten_observations(raw) == [
        {"series_id": "V39079", "obs_date": "2026-07-13", "value": "2.25"}
    ]


def test_flatten_group_multiple_series_per_row():
    raw = {"observations": [{"d": "2026-07-13", "A": {"v": "1"}, "B": {"v": "2"}}]}
    rows = flatten_observations(raw)
    assert {(r["series_id"], r["value"]) for r in rows} == {("A", "1"), ("B", "2")}


def test_flatten_missing_value_is_none():
    raw = {"observations": [{"d": "2026-07-13", "A": {}}, {"d": "2026-07-14", "A": {"v": ""}}]}
    values = {r["obs_date"]: r["value"] for r in flatten_observations(raw)}
    assert values == {"2026-07-13": None, "2026-07-14": None}
