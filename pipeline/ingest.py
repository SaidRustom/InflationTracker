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
    return written
