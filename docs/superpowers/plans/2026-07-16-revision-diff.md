# Revision-Diff Implementation Plan (Plan 3a of 3a/3b/3c)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detect when the Valet API changes an observation it already published, record every change in a permanent append-only ledger, and publish it to `site/data/revisions.json`.

**Architecture:** A new `pipeline/revisions.py` runs from `run.py` **after ingest, before transform**. It compares the retained previous raw vintage against the fresh one, **re-parsing both sides with today's parser** so our own code changes cancel out and only what Valet actually said differently survives. Events append to `data/curated/revisions.json` (permanent); `build_web` publishes a capped, label-enriched view.

**Tech Stack:** Python 3.12 (`.venv`), pydantic (config), pytest, ruff. **No new dependencies.**

**Spec:** `docs/superpowers/specs/2026-07-16-revision-diff-design.md` (approved 2026-07-16, commit `be17200`)

**Scope:** Pipeline through published JSON. **No frontend.** The Data-Trust tab that renders `revisions.json` is Plan 3b, after the accessibility and `fr-CA` number-formatting work — building the tab first would add fresh `toFixed`/no-`aria` debt to the pile 3b exists to clear.

## Global Constraints

Every task's requirements implicitly include these. Copied verbatim from the spec.

- **Revisions never fail the pipeline.** `run.py` exit status is unaffected by any revision event.
- **`detected_at`, never `revised_on`.** A vintage diff reveals when *we noticed*, never when the Bank *acted*.
- **`last_checked` updates only on a run that actually reached the source.** `--offline` and the `ValetError` cache-fallback both skip detection and leave it untouched.
- **`watching_since` is written once at ledger creation and never mutated.**
- **Series present in only one vintage are skipped entirely, not diffed.** Config churn is not a BoC revision.
- **The ledger is append-only.** Corrupt or unreadable → raise and fail the run. **Never silently recreate** — that erases history.
- **Values must be cast to float before comparison.** `flatten_observations` returns strings; without the cast, `"1.50"` → `"1.5"` reports as a revision.
- **Config, not code.** The publish cap lives in `config/settings.yml`.
- **No silent truncation.** The published payload always carries `total_events` alongside the capped list.
- Test command: `.venv\Scripts\python.exe -m pytest -q` · Lint: `.venv\Scripts\python.exe -m ruff check .`
- Baseline before this plan: **30 tests passing, ruff clean.**

---

### Task 1: Read a vintage into a comparable map

The float cast lives here. This is the task that defuses the `"1.50"` vs `"1.5"` trap.

**Files:**
- Create: `pipeline/revisions.py`
- Create: `tests/test_revisions.py`

**Interfaces:**
- Consumes: `pipeline.parse.flatten_observations(raw: dict) -> list[dict]` — returns rows shaped `{"series_id": str, "obs_date": str, "value": str | None}`. **Note `value` is a string**; `parse.py` contains zero `float()` calls, the cast happens only in DuckDB today.
- Produces: `observations_from_vintage(vintage_dir: Path) -> dict[tuple[str, str], float | None]`, keyed `(series_id, obs_date)`.

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_revisions.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.revisions'`

- [ ] **Step 3: Write minimal implementation**

```python
import json
from pathlib import Path

from pipeline.parse import flatten_observations


def observations_from_vintage(vintage_dir: Path) -> dict[tuple[str, str], float | None]:
    """Map every observation in a raw vintage to {(series_id, obs_date): float | None}.

    Both sides of a diff go through this function with *today's* parser, which is
    what makes our own parse changes cancel out instead of masquerading as Bank
    revisions. The float cast lives here because parse.py returns strings - without
    it, "1.50" -> "1.5" would report as a revision when nothing changed.
    """
    out: dict[tuple[str, str], float | None] = {}
    for path in sorted(Path(vintage_dir).glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        for row in flatten_observations(raw):
            value = row["value"]
            out[(row["series_id"], row["obs_date"])] = None if value is None else float(value)
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_revisions.py -q`
Expected: PASS — 4 passed

- [ ] **Step 5: Commit**

```bash
git add pipeline/revisions.py tests/test_revisions.py
git commit -m "feat: read a raw vintage into a float-normalised observation map"
```

---

### Task 2: Classify the diff

**Files:**
- Modify: `pipeline/revisions.py`
- Modify: `tests/test_revisions.py`

**Interfaces:**
- Consumes: `observations_from_vintage` (Task 1) — the two maps being compared.
- Produces:
  - `RevisionEvent` dataclass: fields `series_id: str`, `date: str`, `kind: str`, `old: float | None`, `new: float | None`, `detected_at: str`.
  - `diff_vintages(before: dict, after: dict, detected_at: str) -> list[RevisionEvent]`.
  - `kind` is a closed set: `"revised"` | `"late_publication"` | `"withdrawn"`.

- [ ] **Step 1: Write the failing test**

```python
from pipeline.revisions import RevisionEvent, diff_vintages


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_revisions.py -q`
Expected: FAIL — `ImportError: cannot import name 'RevisionEvent' from 'pipeline.revisions'`

- [ ] **Step 3: Write minimal implementation**

Add to `pipeline/revisions.py` (keep the existing imports; add `from dataclasses import dataclass`):

```python
_MISSING = object()


@dataclass(frozen=True)
class RevisionEvent:
    series_id: str
    date: str
    kind: str  # "revised" | "late_publication" | "withdrawn"
    old: float | None
    new: float | None
    detected_at: str


def diff_vintages(
    before: dict[tuple[str, str], float | None],
    after: dict[tuple[str, str], float | None],
    detected_at: str,
) -> list[RevisionEvent]:
    """Classify what changed between two vintages of the same source.

    detected_at is the run date - when we NOTICED. A vintage diff cannot know when
    the Bank actually revised, only when we looked, so the field is never revised_on.
    """
    shared_series = {sid for sid, _ in before} & {sid for sid, _ in after}
    events: list[RevisionEvent] = []

    for key in sorted(before):
        series_id, date = key
        if series_id not in shared_series:
            continue  # config churn: series added/removed on our side, not revised on theirs

        old = before[key]
        new = after[key] if key in after else _MISSING

        if new is _MISSING:
            if old is None:
                continue  # nothing was ever published for that date, so nothing was withdrawn
            events.append(RevisionEvent(series_id, date, "withdrawn", old, None, detected_at))
            continue

        if old == new:
            continue  # covers equal floats and None == None

        if old is None:
            kind = "late_publication"
        elif new is None:
            kind = "withdrawn"
        else:
            kind = "revised"
        events.append(RevisionEvent(series_id, date, kind, old, new, detected_at))

    return events
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_revisions.py -q`
Expected: PASS — 13 passed

- [ ] **Step 5: Commit**

```bash
git add pipeline/revisions.py tests/test_revisions.py
git commit -m "feat: classify revised/late_publication/withdrawn between vintages"
```

---

### Task 3: The append-only ledger

**Files:**
- Modify: `pipeline/revisions.py`
- Modify: `tests/test_revisions.py`

**Interfaces:**
- Consumes: `RevisionEvent` (Task 2).
- Produces:
  - `Ledger` dataclass: `watching_since: str`, `last_checked: str`, `events: list[RevisionEvent]`.
  - `RevisionLedgerError(Exception)`.
  - `load_ledger(path: Path, default_watching_since: str) -> Ledger`
  - `append_events(ledger: Ledger, events: list[RevisionEvent], last_checked: str) -> Ledger`
  - `ledger_to_dict(ledger: Ledger) -> dict`
  - `write_ledger(ledger: Ledger, path: Path) -> None`

- [ ] **Step 1: Write the failing test**

```python
import pytest

from pipeline.revisions import (
    Ledger,
    RevisionEvent,
    RevisionLedgerError,
    append_events,
    ledger_to_dict,
    load_ledger,
    write_ledger,
)


def _event(detected_at="2026-06-20", old=2.9, new=3.1) -> RevisionEvent:
    return RevisionEvent("S", "2026-03-01", "revised", old, new, detected_at)


def test_first_run_creates_ledger_with_watching_since(tmp_path):
    ledger = load_ledger(tmp_path / "revisions.json", default_watching_since="2026-07-14")
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_revisions.py -q`
Expected: FAIL — `ImportError: cannot import name 'Ledger' from 'pipeline.revisions'`

- [ ] **Step 3: Write minimal implementation**

Add to `pipeline/revisions.py` (add `from dataclasses import asdict, dataclass, replace` to imports):

```python
class RevisionLedgerError(Exception):
    """The ledger is unreadable. Never recover by resetting - that erases history."""


@dataclass(frozen=True)
class Ledger:
    watching_since: str
    last_checked: str
    events: list[RevisionEvent]


def _dedupe_key(e: RevisionEvent) -> tuple:
    return (e.series_id, e.date, e.kind, e.old, e.new, e.detected_at)


def load_ledger(path: Path, default_watching_since: str) -> Ledger:
    path = Path(path)
    if not path.exists():
        return Ledger(
            watching_since=default_watching_since,
            last_checked=default_watching_since,
            events=[],
        )
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RevisionLedgerError(f"revisions ledger at {path} is corrupt: {exc}") from exc

    for key in ("watching_since", "last_checked", "events"):
        if key not in raw:
            raise RevisionLedgerError(f"revisions ledger at {path} is missing {key!r}")

    return Ledger(
        watching_since=raw["watching_since"],
        last_checked=raw["last_checked"],
        events=[RevisionEvent(**e) for e in raw["events"]],
    )


def append_events(ledger: Ledger, events: list[RevisionEvent], last_checked: str) -> Ledger:
    """Append unseen events. watching_since is never touched - it is written once."""
    seen = {_dedupe_key(e) for e in ledger.events}
    fresh = [e for e in events if _dedupe_key(e) not in seen]
    return replace(ledger, last_checked=last_checked, events=[*ledger.events, *fresh])


def ledger_to_dict(ledger: Ledger) -> dict:
    return {
        "watching_since": ledger.watching_since,
        "last_checked": ledger.last_checked,
        "events": [asdict(e) for e in ledger.events],
    }


def write_ledger(ledger: Ledger, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(ledger_to_dict(ledger), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_revisions.py -q`
Expected: PASS — 21 passed

- [ ] **Step 5: Commit**

```bash
git add pipeline/revisions.py tests/test_revisions.py
git commit -m "feat: append-only revisions ledger with immutable watching_since"
```

---

### Task 4: Find the baseline vintage and prune the rest

**Files:**
- Modify: `pipeline/revisions.py`
- Modify: `tests/test_revisions.py`

**Interfaces:**
- Produces:
  - `find_baseline_dir(raw_root: Path, run_date: str) -> Path | None` — newest vintage dir whose name sorts strictly before `run_date`, else `None`.
  - `prune_vintages(raw_root: Path, keep: int = 2) -> list[Path]` — returns the removed dirs.
- Note: vintage dir names are ISO dates, which sort lexicographically = chronologically.

- [ ] **Step 1: Write the failing test**

```python
from pipeline.revisions import find_baseline_dir, prune_vintages


def _dirs(root, *names):
    for n in names:
        (root / n).mkdir(parents=True)


def test_baseline_is_the_newest_older_vintage(tmp_path):
    _dirs(tmp_path, "2026-07-13", "2026-07-14", "2026-07-15")
    assert find_baseline_dir(tmp_path, "2026-07-15").name == "2026-07-14"


def test_no_baseline_on_first_run(tmp_path):
    _dirs(tmp_path, "2026-07-15")
    assert find_baseline_dir(tmp_path, "2026-07-15") is None


def test_no_baseline_when_raw_root_absent(tmp_path):
    assert find_baseline_dir(tmp_path / "nope", "2026-07-15") is None


def test_prune_keeps_the_two_newest(tmp_path):
    _dirs(tmp_path, "2026-07-12", "2026-07-13", "2026-07-14", "2026-07-15")
    removed = prune_vintages(tmp_path, keep=2)
    assert sorted(p.name for p in removed) == ["2026-07-12", "2026-07-13"]
    assert sorted(p.name for p in tmp_path.iterdir()) == ["2026-07-14", "2026-07-15"]


def test_prune_is_a_noop_below_the_limit(tmp_path):
    _dirs(tmp_path, "2026-07-14", "2026-07-15")
    assert prune_vintages(tmp_path, keep=2) == []
    assert len(list(tmp_path.iterdir())) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_revisions.py -q`
Expected: FAIL — `ImportError: cannot import name 'find_baseline_dir' from 'pipeline.revisions'`

- [ ] **Step 3: Write minimal implementation**

Add to `pipeline/revisions.py` (add `import shutil` to imports):

```python
def _vintage_dirs(raw_root: Path) -> list[Path]:
    root = Path(raw_root)
    if not root.exists():
        return []
    return sorted((p for p in root.iterdir() if p.is_dir()), key=lambda p: p.name)


def find_baseline_dir(raw_root: Path, run_date: str) -> Path | None:
    """Newest vintage older than run_date. Names are ISO dates, so they sort chronologically."""
    older = [p for p in _vintage_dirs(raw_root) if p.name < run_date]
    return older[-1] if older else None


def prune_vintages(raw_root: Path, keep: int = 2) -> list[Path]:
    """Keep the newest `keep` vintages. Two, because a run needs baseline AND fetch alive at once.

    Callers must only prune on a run that actually reached the source - a run that
    fetched nothing has no new vintage to make room for, and pruning would discard a
    baseline in exchange for nothing.
    """
    dirs = _vintage_dirs(raw_root)
    removed = dirs[:-keep] if len(dirs) > keep else []
    for path in removed:
        shutil.rmtree(path)
    return removed
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_revisions.py -q`
Expected: PASS — 26 passed

- [ ] **Step 5: Commit**

```bash
git add pipeline/revisions.py tests/test_revisions.py
git commit -m "feat: baseline vintage discovery and bounded retention"
```

---

### Task 5: Wire detection into run.py, gated on reaching the source

The honesty gate. This is the task where the page learns not to claim it checked when it didn't.

**Files:**
- Modify: `pipeline/run.py:38-49`
- Create: `tests/test_run_revisions.py`

**Interfaces:**
- Consumes: `find_baseline_dir`, `observations_from_vintage`, `diff_vintages`, `load_ledger`, `append_events`, `write_ledger`, `prune_vintages`.
- Produces: `detect_and_record(raw_root: Path, run_date: str, ledger_path: Path) -> Ledger` — the whole detection step as one callable, so `run.py` stays thin and the step is testable without a Valet client.
- `run.py` gains a local `reached_source: bool`, true only when `run_ingest` returned without raising.

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_run_revisions.py -q`
Expected: FAIL — `ImportError: cannot import name 'detect_and_record' from 'pipeline.revisions'`

- [ ] **Step 3: Write minimal implementation**

Add to `pipeline/revisions.py`:

```python
def detect_and_record(raw_root: Path, run_date: str, ledger_path: Path) -> Ledger:
    """Diff the retained baseline against this run's vintage and append to the ledger.

    Callers MUST only invoke this on a run that actually reached the source. An
    offline run or a cache-fallback run never contacted Valet, so advancing
    last_checked would make the page claim it checked during an outage.
    """
    baseline = find_baseline_dir(raw_root, run_date)
    events: list[RevisionEvent] = []
    if baseline is not None:
        events = diff_vintages(
            observations_from_vintage(baseline),
            observations_from_vintage(Path(raw_root) / run_date),
            detected_at=run_date,
        )
    ledger = load_ledger(ledger_path, default_watching_since=run_date)
    ledger = append_events(ledger, events, last_checked=run_date)
    write_ledger(ledger, ledger_path)
    prune_vintages(raw_root, keep=2)
    return ledger
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_run_revisions.py -q`
Expected: PASS — 4 passed

- [ ] **Step 5: Wire it into run.py**

Replace the ingest block at `pipeline/run.py:38-45` with:

```python
    reached_source = False
    if not args.offline:
        try:
            run_ingest(config, ValetClient(), raw_root, args.run_date)
            reached_source = True
        except ValetError as exc:
            if not (raw_root / args.run_date).exists():
                print(f"ingest failed and no cached raw for {args.run_date}: {exc}", file=sys.stderr)
                return 2
            print(f"ingest failed; reusing cached raw for {args.run_date}: {exc}", file=sys.stderr)

    # Revision detection compares source bytes, so it runs before anything derived
    # exists - and only when we actually reached the source. An offline run or a
    # cache-fallback never contacted Valet; advancing last_checked would let the page
    # claim "checked today" during an outage.
    ledger_path = Path(args.curated_dir) / "revisions.json"
    if reached_source:
        detect_and_record(raw_root, args.run_date, ledger_path)
```

And add the import at the top of `pipeline/run.py`:

```python
from pipeline.revisions import detect_and_record
```

Leave the `build_web(...)` call alone for now — it does not accept a `revisions` argument until Task 6, and passing one here would raise `TypeError`. Task 6 adds the parameter and the call-site change together.

- [ ] **Step 6: Run the full suite and lint**

Run: `.venv\Scripts\python.exe -m pytest -q && .venv\Scripts\python.exe -m ruff check .`
Expected: PASS — 60 passed, `All checks passed!`

- [ ] **Step 7: Commit**

```bash
git add pipeline/revisions.py pipeline/run.py tests/test_run_revisions.py
git commit -m "feat: run revision detection only on runs that reached the source"
```

---

### Task 6: Publish `site/data/revisions.json`

**Files:**
- Modify: `config/settings.yml`
- Modify: `pipeline/models.py:18-50`
- Modify: `pipeline/build_web.py:33-74`
- Modify: `pipeline/run.py` (the ledger load + the `build_web` call site)
- Modify: `tests/test_build_web.py`

**Interfaces:**
- Consumes: `ledger_to_dict(...)` output (Task 3) — `{"watching_since", "last_checked", "events": [ {series_id, date, kind, old, new, detected_at} ]}`, or `None` when no ledger exists yet.
- Produces:
  - `RevisionsConfig` pydantic model with `publish_limit: int = 100`; `AppConfig.revisions: RevisionsConfig`.
  - `build_web(..., revisions: dict | None = None)` — keyword-defaulted so existing callers and tests keep working.
  - `site/data/revisions.json`: `{"watching_since", "last_checked", "events": [...enriched, newest first...], "total_events": int}`.

- [ ] **Step 1: Write the failing test**

```python
from pipeline.models import AppConfig, RevisionsConfig, SeriesConfig, Thresholds


def _rev_cfg(limit=100) -> AppConfig:
    return AppConfig(
        start_date="2000-01-01",
        series=[SeriesConfig(id="S", label_en="Series S", label_fr="Serie S", frequency="monthly", role="inflation")],
        thresholds=Thresholds(staleness_days={"monthly": 95}, max_null_ratio=0.2, value_ranges={"inflation": (-5.0, 25.0)}),
        revisions=RevisionsConfig(publish_limit=limit),
    )


def _ledger(n: int) -> dict:
    return {
        "watching_since": "2026-07-14",
        "last_checked": "2026-07-16",
        "events": [
            {"series_id": "S", "date": f"2026-{m:02d}-01", "kind": "revised",
             "old": 2.9, "new": 3.1, "detected_at": "2026-07-16"}
            for m in range(1, n + 1)
        ],
    }


def test_revisions_payload_is_enriched_with_labels(tmp_path):
    from pipeline.build_web import revisions_payload
    out = revisions_payload(_rev_cfg(), _ledger(1))
    assert out["events"][0]["label_en"] == "Series S"
    assert out["events"][0]["label_fr"] == "Serie S"
    assert out["watching_since"] == "2026-07-14"
    assert out["last_checked"] == "2026-07-16"


def test_publish_limit_caps_but_reports_the_total(tmp_path):
    from pipeline.build_web import revisions_payload
    out = revisions_payload(_rev_cfg(limit=2), _ledger(5))
    assert len(out["events"]) == 2
    assert out["total_events"] == 5  # no silent truncation


def test_published_events_are_newest_first(tmp_path):
    from pipeline.build_web import revisions_payload
    out = revisions_payload(_rev_cfg(limit=2), _ledger(5))
    assert [e["date"] for e in out["events"]] == ["2026-05-01", "2026-04-01"]


def test_no_ledger_yet_publishes_an_honest_empty_payload(tmp_path):
    from pipeline.build_web import revisions_payload
    out = revisions_payload(_rev_cfg(), None)
    assert out == {"watching_since": None, "last_checked": None, "events": [], "total_events": 0}


def test_shipped_config_carries_a_publish_limit():
    from pathlib import Path

    from pipeline.models import load_config
    cfg_dir = Path(__file__).resolve().parents[1] / "config"
    cfg = load_config(cfg_dir / "series.yml", cfg_dir / "settings.yml")
    assert cfg.revisions.publish_limit > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_build_web.py -q`
Expected: FAIL — `ImportError: cannot import name 'RevisionsConfig' from 'pipeline.models'`

- [ ] **Step 3: Add the config knob**

Append to `config/settings.yml`:

```yaml
revisions:
  # How many of the most recent ledger events site/data/revisions.json carries. The
  # ledger keeps every event forever; the page states "showing N of TOTAL" so the cap
  # is never a silent truncation.
  publish_limit: 100
```

In `pipeline/models.py`, add the model and field, and read it in `load_config`:

```python
class RevisionsConfig(BaseModel):
    publish_limit: int = 100


class AppConfig(BaseModel):
    start_date: str
    series: list[SeriesConfig]
    thresholds: Thresholds
    inflation_band: InflationBand = InflationBand(low=1.0, high=3.0)
    revisions: RevisionsConfig = RevisionsConfig()

    def by_metric_key(self, key: str) -> SeriesConfig:
        for s in self.series:
            if s.metric_key == key:
                return s
        raise KeyError(f"no series with metric_key={key!r}")


def load_config(series_path: Path, settings_path: Path) -> AppConfig:
    series = yaml.safe_load(series_path.read_text(encoding="utf-8"))["series"]
    settings = yaml.safe_load(settings_path.read_text(encoding="utf-8"))
    return AppConfig(
        start_date=settings["start_date"],
        series=[SeriesConfig(**s) for s in series],
        thresholds=Thresholds(**settings["thresholds"]),
        inflation_band=InflationBand(**settings["inflation_band"]),
        revisions=RevisionsConfig(**settings.get("revisions", {})),
    )
```

- [ ] **Step 4: Implement the payload in build_web.py**

Add to `pipeline/build_web.py`:

```python
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
```

Change the `build_web` signature and add the write (keyword-defaulted so existing callers keep working):

```python
def build_web(
    con: duckdb.DuckDBPyConnection,
    config: AppConfig,
    metrics: dict,
    quality: dict,
    out_dir: Path,
    as_of: str,
    revisions: dict | None = None,
) -> list[Path]:
```

Immediately before the `manifest.json` write, add:

```python
    paths.append(_write(out_dir, "revisions.json", revisions_payload(config, revisions)))
```

And add `"revisions"` to the manifest so the site can discover it:

```python
    paths.append(_write(out_dir, "manifest.json", {
        "as_of": as_of,
        "last_refreshed": quality.get("generated_at", f"{as_of}T00:00:00"),
        "overall_quality": quality.get("overall", "OK"),
        "panels": ["policy", "markets", "households", "target"],
        "revisions": "revisions.json",
    }))
```

- [ ] **Step 5: Hand the ledger to build_web from run.py**

In `pipeline/run.py`, extend the import added in Task 5:

```python
from pipeline.revisions import detect_and_record, ledger_to_dict, load_ledger
```

Directly below the `if reached_source: detect_and_record(...)` block, read the ledger back for
publication — it exists whether or not *this* run detected anything, and publishing it on an offline
run is correct: we republish what we last knew, with `last_checked` unchanged.

```python
    revisions = (
        ledger_to_dict(load_ledger(ledger_path, default_watching_since=args.run_date))
        if ledger_path.exists()
        else None
    )
```

Then pass it at the `build_web(...)` call:

```python
    build_web(
        con, config, metrics, report_to_dict(report), Path(args.web_dir),
        as_of=args.run_date, revisions=revisions,
    )
```

- [ ] **Step 6: Run the full suite and lint**

Run: `.venv\Scripts\python.exe -m pytest -q && .venv\Scripts\python.exe -m ruff check .`
Expected: PASS — 65 passed, `All checks passed!`

- [ ] **Step 7: Commit**

```bash
git add config/settings.yml pipeline/models.py pipeline/build_web.py pipeline/run.py tests/test_build_web.py
git commit -m "feat: publish site/data/revisions.json, capped with total stated"
```

---

### Task 7: Regression-test against the two real committed vintages

The false-positive suite. Every class of lie this design exists to prevent, tested against data already in the repo.

**Files:**
- Create: `tests/test_revisions_real_vintages.py`

**Interfaces:**
- Consumes: `observations_from_vintage`, `diff_vintages` (Tasks 1-2), and the committed `data/raw/2026-07-14` / `data/raw/2026-07-15` fixtures.

**Ground truth**, measured from the repo: the 4 daily series (`AVG.INTWO`, `BD.CDN.{2,5,10}YR.DQ.YLD`, `V39079`) each gained exactly 1 observation; the 4 monthly series were unchanged; `STATIC_TOTALCPICHANGE` exists **only** in the 07-15 vintage because Plan 2 added it; **zero** revisions.

- [ ] **Step 1: Write the test**

```python
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
```

- [ ] **Step 2: Run the test**

Run: `.venv\Scripts\python.exe -m pytest tests/test_revisions_real_vintages.py -q`
Expected: PASS — 4 passed
If `test_new_daily_observations_are_not_revisions` fails on the series set, print `{sid for sid, _ in added}` and reconcile against the real vintages before changing the differ — the fixture is ground truth, the assertion is a transcription of it.

- [ ] **Step 3: Run the full suite and lint**

Run: `.venv\Scripts\python.exe -m pytest -q && .venv\Scripts\python.exe -m ruff check .`
Expected: PASS — 69 passed, `All checks passed!`

- [ ] **Step 4: Verify the pipeline end-to-end offline**

Run: `.venv\Scripts\python.exe -m pipeline.run --run-date 2026-07-15 --ingested-at 2026-07-15T00:00:00 --offline`
Expected: `pipeline OK - overall quality: OK`, and **`site/data/revisions.json` must NOT have been rewritten with a fresh `last_checked`** — the run was offline, so it never reached the source. Confirm with `git status site/data/revisions.json`.

- [ ] **Step 5: Commit**

```bash
git add tests/test_revisions_real_vintages.py
git commit -m "test: pin the differ against the two real committed vintages"
```

---

## Done when

- `.venv\Scripts\python.exe -m pytest -q` → **69 passed** (up from 30), ruff clean.
- `data/curated/revisions.json` exists after an online run, append-only, `watching_since` immutable.
- `site/data/revisions.json` published, capped at `publish_limit`, `total_events` always stated.
- An `--offline` run leaves `last_checked` untouched.
- The differ reports **zero** events against the two real seed vintages.

## Follow-on (not this plan)

- **Plan 3b** — accessibility (WCAG 2.1 AA: zero `aria`/`role`/`<table>` today), `fr-CA` number formatting (`toFixed` everywhere, no `Intl`), the Data-Trust tab rendering `revisions.json` + `data_quality.json`, methodology page.
- **Plan 3c** — `ci.yml`, `refresh.yml` (the cron that makes this feature accumulate), README.
- **Deferred by the spec (§3):** surfacing `withdrawn` as a WARN in `data_quality.json`.
