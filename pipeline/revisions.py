import json
import os
import re
import shutil
import sys
import tempfile
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from pipeline.parse import flatten_observations

_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_META_FILENAME = "_meta.json"


def observations_from_vintage(vintage_dir: Path) -> dict[tuple[str, str], float | None]:
    """Map every observation in a raw vintage to {(series_id, obs_date): float | None}.

    Both sides of a diff go through this function with *today's* parser, which is
    what makes our own parse changes cancel out instead of masquerading as Bank
    revisions. The float cast lives here because parse.py returns strings - without
    it, "1.50" -> "1.5" would report as a revision when nothing changed.
    """
    out: dict[tuple[str, str], float | None] = {}
    for path in sorted(Path(vintage_dir).glob("*.json")):
        if path.name == _META_FILENAME:
            # _meta.json records the vintage's fetch params (start_date, recent), not
            # a series. flatten_observations would harmlessly return [] for it today
            # (no "observations" key), but skip it explicitly rather than lean on
            # that - a future field named "observations" in the meta shape would
            # silently masquerade as real data.
            continue
        raw = json.loads(path.read_text(encoding="utf-8"))
        for row in flatten_observations(raw):
            value = row["value"]
            out[(row["series_id"], row["obs_date"])] = None if value is None else float(value)
    return out


def _read_meta(vintage_dir: Path) -> dict | None:
    """The fetch params recorded for a vintage, or None if it predates this feature."""
    path = Path(vintage_dir) / _META_FILENAME
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


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
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        raise RevisionLedgerError(f"revisions ledger at {path} is unreadable: {exc}") from exc

    if not isinstance(raw, dict):
        raise RevisionLedgerError(f"revisions ledger at {path} is not a JSON object")

    for key in ("watching_since", "last_checked", "events"):
        if key not in raw:
            raise RevisionLedgerError(f"revisions ledger at {path} is missing {key!r}")

    if not isinstance(raw["events"], list):
        raise RevisionLedgerError(f"revisions ledger at {path} has a non-list 'events'")

    try:
        events = [RevisionEvent(**e) for e in raw["events"]]
    except (TypeError, KeyError) as exc:
        raise RevisionLedgerError(f"revisions ledger at {path} has a malformed event: {exc}") from exc

    return Ledger(
        watching_since=raw["watching_since"],
        last_checked=raw["last_checked"],
        events=events,
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
    """Write the ledger atomically: a crash or disk-full mid-write must never leave a
    truncated file at `path`. Write to a temp file in the same directory (so the
    final os.replace is a same-filesystem rename, atomic on both POSIX and Windows),
    then swap it in. The temp file is the only thing that can end up half-written."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(ledger_to_dict(ledger), ensure_ascii=False, indent=2)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(payload)
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def _vintage_dirs(raw_root: Path) -> list[Path]:
    root = Path(raw_root)
    if not root.exists():
        return []
    # Names must be ISO dates: both callers rely on lexicographic order being
    # chronological, and prune_vintages rmtree's what it deems oldest. A stray
    # directory would sort into that ordering and cost a real vintage.
    return sorted(
        (p for p in root.iterdir() if p.is_dir() and _ISO_DATE.fullmatch(p.name)),
        key=lambda p: p.name,
    )


def find_baseline_dir(raw_root: Path, run_date: str) -> Path | None:
    """Newest vintage older than run_date. Names are ISO dates, so they sort chronologically."""
    older = [p for p in _vintage_dirs(raw_root) if p.name < run_date]
    return older[-1] if older else None


def detect_and_record(raw_root: Path, run_date: str, ledger_path: Path) -> Ledger:
    """Diff the retained baseline against this run's vintage and append to the ledger.

    Callers MUST only invoke this on a run that actually reached the source. An
    offline run or a cache-fallback run never contacted Valet, so advancing
    last_checked would make the page claim it checked during an outage.

    Which observations were fetched is a property of the *request* (start_date,
    ?recent=), not something the parser can recover from bytes. Moving start_date
    forward makes every pre-window observation vanish on the new side, and the
    shared_series guard in diff_vintages waves that straight through to `withdrawn`
    - a config edit publishing fake withdrawals over the Bank's name. So detection
    only runs when both vintages' recorded fetch params match exactly; unknown
    (missing _meta.json, e.g. a vintage from before this feature existed) is treated
    as a mismatch, not as equal, since unverifiable is not the same as unchanged.
    """
    baseline = find_baseline_dir(raw_root, run_date)
    events: list[RevisionEvent] = []
    if baseline is not None:
        baseline_meta = _read_meta(baseline)
        current_meta = _read_meta(Path(raw_root) / run_date)
        if baseline_meta is None or current_meta is None or baseline_meta != current_meta:
            print(
                f"revisions: skipping detection between {baseline.name} and {run_date} - "
                f"fetch params differ or are unknown (baseline={baseline_meta!r}, "
                f"current={current_meta!r}); we cannot tell a real withdrawal from a "
                "start_date/recent change, so we are not comparing across this boundary",
                file=sys.stderr,
            )
        else:
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


def prune_vintages(raw_root: Path, keep: int = 2) -> list[Path]:
    """Keep the newest `keep` vintages. Two, because a run needs baseline AND fetch alive at once.

    Callers must only prune on a run that actually reached the source - a run that
    fetched nothing has no new vintage to make room for, and pruning would discard a
    baseline in exchange for nothing.
    """
    dirs = _vintage_dirs(raw_root)
    removed = dirs[: len(dirs) - keep] if len(dirs) > keep else []
    for path in removed:
        shutil.rmtree(path)
    return removed
