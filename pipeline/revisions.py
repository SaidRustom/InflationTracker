import json
from dataclasses import dataclass
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
