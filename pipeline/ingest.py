import json
from pathlib import Path

from pipeline.models import AppConfig


def run_ingest(config: AppConfig, client, out_root: Path, run_date: str) -> list[Path]:
    out_dir = Path(out_root) / run_date
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for series in config.series:
        body = client.get_observations(series.id, kind=series.kind, start=config.start_date)
        path = out_dir / f"{series.id}.json"
        path.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
        written.append(path)

    # Record the fetch parameters alongside the vintage. Which observations we
    # fetched is not something the parser can recover - it is a property of the
    # request, not the bytes. detect_and_record compares this file across vintages
    # and skips detection when it differs (or is missing), because a start_date or
    # ?recent= change makes every pre-window observation look like a withdrawal to
    # a byte-for-byte diff, even though nothing was actually revised.
    (out_dir / "_meta.json").write_text(
        json.dumps({"start_date": config.start_date, "recent": None}, ensure_ascii=False),
        encoding="utf-8",
    )
    return written
