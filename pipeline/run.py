import argparse
import json
import sys
from pathlib import Path

from pipeline.build_web import build_web
from pipeline.ingest import run_ingest
from pipeline.metrics import run_metrics
from pipeline.models import load_config
from pipeline.parse import flatten_observations
from pipeline.quality import report_to_dict, run_quality, write_report
from pipeline.revisions import detect_and_record, ledger_to_dict, load_ledger
from pipeline.transform import build_curated_con, write_curated
from pipeline.valet_client import ValetClient, ValetError


def _read_raw(raw_root: Path, run_date: str) -> list[dict]:
    rows: list[dict] = []
    for path in sorted((raw_root / run_date).glob("*.json")):
        rows.extend(flatten_observations(json.loads(path.read_text(encoding="utf-8"))))
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Inflation Tracker pipeline")
    ap.add_argument("--config-dir", default="config")
    ap.add_argument("--raw-root", default="data/raw")
    ap.add_argument("--curated-dir", default="data/curated")
    ap.add_argument("--web-dir", default="site/data")
    ap.add_argument("--run-date", required=True)
    ap.add_argument("--ingested-at", required=True)
    ap.add_argument("--offline", action="store_true", help="skip ingest, reuse existing raw")
    args = ap.parse_args(argv)

    cfg_dir = Path(args.config_dir)
    config = load_config(cfg_dir / "series.yml", cfg_dir / "settings.yml")
    raw_root = Path(args.raw_root)

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

    revisions = (
        ledger_to_dict(load_ledger(ledger_path, default_watching_since=args.run_date))
        if ledger_path.exists()
        else None
    )

    rows = _read_raw(raw_root, args.run_date)
    con = build_curated_con(rows, config, ingested_at=args.ingested_at)
    write_curated(con, Path(args.curated_dir))

    metrics = run_metrics(con, config)
    report = run_quality(con, config, as_of=args.run_date)
    write_report(report, Path(args.curated_dir) / "data_quality.json")
    build_web(
        con, config, metrics, report_to_dict(report), Path(args.web_dir),
        as_of=args.run_date, revisions=revisions,
    )

    print(f"pipeline OK - overall quality: {report.overall}")
    return 1 if report.overall == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
