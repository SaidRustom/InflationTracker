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
