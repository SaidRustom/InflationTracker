from pathlib import Path

import duckdb

from pipeline.models import AppConfig

SQL_PATH = Path(__file__).with_name("transform.sql")


def _load_dim_series(con: duckdb.DuckDBPyConnection, config: AppConfig) -> None:
    con.execute(
        "CREATE TABLE dim_series ("
        "series_id VARCHAR, label_en VARCHAR, label_fr VARCHAR, "
        "frequency VARCHAR, role VARCHAR, metric_key VARCHAR, source_url VARCHAR)"
    )
    con.executemany(
        "INSERT INTO dim_series VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            (s.id, s.label_en, s.label_fr, s.frequency, s.role, s.metric_key, s.source_url)
            for s in config.series
        ],
    )


def _load_staging(con: duckdb.DuckDBPyConnection, rows: list[dict]) -> None:
    con.execute("CREATE TABLE stg_observation (series_id VARCHAR, obs_date VARCHAR, value VARCHAR)")
    if rows:
        con.executemany(
            "INSERT INTO stg_observation VALUES (?, ?, ?)",
            [(r["series_id"], r["obs_date"], r["value"]) for r in rows],
        )


def build_curated_con(
    rows: list[dict], config: AppConfig, ingested_at: str, sql_path: Path = SQL_PATH
) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute(f"SET VARIABLE ingested_at = '{ingested_at}'")
    _load_dim_series(con, config)
    _load_staging(con, rows)
    con.execute(sql_path.read_text(encoding="utf-8"))
    return con


def write_curated(con: duckdb.DuckDBPyConnection, out_dir: Path) -> None:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    con.execute(f"COPY dim_series TO '{(out_dir / 'dim_series.parquet').as_posix()}' (FORMAT PARQUET)")
    con.execute(
        f"COPY fact_observation TO '{(out_dir / 'fact_observation.parquet').as_posix()}' (FORMAT PARQUET)"
    )
