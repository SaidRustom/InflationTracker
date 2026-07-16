import json
from dataclasses import asdict, dataclass, replace
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
    except json.JSONDecodeError as exc:
        raise RevisionLedgerError(f"revisions ledger at {path} is corrupt: {exc}") from exc

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
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(ledger_to_dict(ledger), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
