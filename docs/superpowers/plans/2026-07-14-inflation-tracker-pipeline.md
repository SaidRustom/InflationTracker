# Inflation Tracker — Pipeline Implementation Plan (Plan 1 of 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Python + SQL data pipeline that ingests BoC Valet series, transforms them with DuckDB, computes derived metrics, runs data-quality checks, and emits the slim per-panel JSON the dashboard consumes.

**Architecture:** Four file-based, idempotent stages — `ingest` (Valet → dated raw JSON) → `transform` (DuckDB SQL → `dim_series` + `fact_observation` parquet) → `metrics` + `quality` (ASOF-join derived series + a data-quality report) → `build_web` (per-panel JSON + manifest). A thin `run.py` CLI chains them. Plan 2 covers the static dashboard, CI workflows, and GitHub Pages deploy that consume this plan's `site/data/*.json`.

**Tech Stack:** Python 3.12, httpx (HTTP), DuckDB (SQL transforms + ASOF joins), pydantic (config/validation), PyYAML (config), pytest + ruff (dev). No pandas.

## Global Constraints

- Python `>=3.12`. Runtime deps limited to: `httpx`, `duckdb`, `pydantic`, `pyyaml`. Dev: `pytest`, `ruff`. **No pandas.**
- **BoC Valet is the only external data source.** All series IDs live in `config/series.yml`, never hard-coded in Python.
- **Descriptive only** — no advice, no prediction, no forecasting logic anywhere.
- Pipeline is **file-based and idempotent**; a failed run must never overwrite good data with empty output.
- **Bilingual:** every series carries `label_en` and `label_fr`; no English-only leakage into emitted data.
- Package name is `pipeline`; tests import `from pipeline.<module> import ...`.
- TDD: write the failing test first. Commit after every green task. DRY, YAGNI.
- Verified series IDs (checked live 2026-07-14): policy `V39079`; funding `AVG.INTWO`; yields `BD.CDN.2YR.DQ.YLD`, `BD.CDN.5YR.DQ.YLD`, `BD.CDN.10YR.DQ.YLD`; mortgage `V122667780`; core CPI `CPI_TRIM`, `CPI_MEDIAN`, `CPI_COMMON`.

## File Structure

- `pyproject.toml` — deps, pytest pythonpath, ruff, hatchling build.
- `pipeline/__init__.py` — package marker.
- `pipeline/models.py` — pydantic config models + `load_config`.
- `pipeline/valet_client.py` — `ValetClient` HTTP wrapper with retry/backoff.
- `pipeline/ingest.py` — `run_ingest` → dated raw JSON.
- `pipeline/parse.py` — `flatten_observations` (Valet JSON → long rows).
- `pipeline/transform.py` + `pipeline/transform.sql` — DuckDB `dim_series` + `fact_observation`.
- `pipeline/metrics.py` — ASOF-join yield slope + household spread.
- `pipeline/quality.py` — data-quality checks + report.
- `pipeline/build_web.py` — per-panel JSON + manifest.
- `pipeline/run.py` — CLI chaining all stages.
- `config/series.yml`, `config/settings.yml` — series catalog + thresholds.
- `tests/…` — one test module per pipeline module + `tests/fixtures/`.

---

### Task 1: Project scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `pipeline/__init__.py`
- Create: `tests/test_smoke.py`

**Interfaces:**
- Consumes: nothing.
- Produces: an importable `pipeline` package; `pytest` and `ruff` runnable.

- [ ] **Step 1: Write the failing test**

`tests/test_smoke.py`:
```python
import pipeline


def test_package_importable():
    assert pipeline.__name__ == "pipeline"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_smoke.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline'`.

- [ ] **Step 3: Create the package and project config**

`pipeline/__init__.py`:
```python
"""Inflation Tracker data pipeline."""
```

`pyproject.toml`:
```toml
[project]
name = "inflation-tracker"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = ["httpx>=0.27", "duckdb>=1.0", "pydantic>=2.7", "pyyaml>=6.0"]

[project.optional-dependencies]
dev = ["pytest>=8", "ruff>=0.5"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["pipeline"]

[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py312"
```

- [ ] **Step 4: Install dev deps and run test to verify it passes**

Run: `uv sync --extra dev` (or `pip install -e ".[dev]"`), then `python -m pytest tests/test_smoke.py -v`
Expected: PASS.

- [ ] **Step 5: Verify lint is clean**

Run: `ruff check .`
Expected: `All checks passed!`

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml pipeline/__init__.py tests/test_smoke.py
git commit -m "chore: scaffold pipeline package with pytest + ruff"
```

---

### Task 2: Config models + loader

**Files:**
- Create: `pipeline/models.py`
- Create: `config/series.yml`
- Create: `config/settings.yml`
- Test: `tests/test_models.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `SeriesConfig` fields: `id: str`, `kind: str = "series"`, `label_en: str`, `label_fr: str`, `frequency: str` (`daily|weekly|monthly`), `role: str` (`policy|funding|yield|lending|inflation`), `metric_key: str | None = None`, `source_url: str | None = None`.
  - `Thresholds` fields: `staleness_days: dict[str, int]` (keyed by frequency), `max_null_ratio: float`, `value_ranges: dict[str, tuple[float, float]]` (keyed by role).
  - `AppConfig` fields: `start_date: str`, `series: list[SeriesConfig]`, `thresholds: Thresholds`; method `by_metric_key(self, key: str) -> SeriesConfig` (raises `KeyError` if absent).
  - `load_config(series_path: Path, settings_path: Path) -> AppConfig`.

- [ ] **Step 1: Write the failing test**

`tests/test_models.py`:
```python
from pathlib import Path

from pipeline.models import AppConfig, load_config

CONFIG = Path("config")


def test_load_config_reads_series_and_thresholds():
    cfg = load_config(CONFIG / "series.yml", CONFIG / "settings.yml")
    assert isinstance(cfg, AppConfig)
    ids = {s.id for s in cfg.series}
    assert {"V39079", "BD.CDN.5YR.DQ.YLD", "V122667780", "CPI_TRIM"} <= ids
    assert cfg.thresholds.staleness_days["daily"] >= 1


def test_by_metric_key_resolves_yield_ids():
    cfg = load_config(CONFIG / "series.yml", CONFIG / "settings.yml")
    assert cfg.by_metric_key("yield_5y").id == "BD.CDN.5YR.DQ.YLD"
    assert cfg.by_metric_key("mortgage_5y_fixed").id == "V122667780"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.models'`.

- [ ] **Step 3: Write the config files**

`config/series.yml`:
```yaml
series:
  - {id: V39079,             kind: series, frequency: daily,   role: policy,    label_en: "Target for the overnight rate", label_fr: "Cible du taux du financement à un jour"}
  - {id: AVG.INTWO,          kind: series, frequency: daily,   role: funding,   label_en: "CORRA (overnight funding)",     label_fr: "CORRA (financement à un jour)"}
  - {id: BD.CDN.2YR.DQ.YLD,  kind: series, frequency: daily,   role: yield,     metric_key: yield_2y,  label_en: "GoC benchmark yield: 2 year",  label_fr: "Rendement de référence GdC : 2 ans"}
  - {id: BD.CDN.5YR.DQ.YLD,  kind: series, frequency: daily,   role: yield,     metric_key: yield_5y,  label_en: "GoC benchmark yield: 5 year",  label_fr: "Rendement de référence GdC : 5 ans"}
  - {id: BD.CDN.10YR.DQ.YLD, kind: series, frequency: daily,   role: yield,     metric_key: yield_10y, label_en: "GoC benchmark yield: 10 year", label_fr: "Rendement de référence GdC : 10 ans"}
  - {id: V122667780,         kind: series, frequency: monthly, role: lending,   metric_key: mortgage_5y_fixed, label_en: "Insured 5yr+ fixed mortgage rate", label_fr: "Taux hypothécaire fixe assuré 5 ans et +"}
  - {id: CPI_TRIM,           kind: series, frequency: monthly, role: inflation, label_en: "Core inflation: CPI-trim",   label_fr: "Inflation fondamentale : IPC-tronq"}
  - {id: CPI_MEDIAN,         kind: series, frequency: monthly, role: inflation, label_en: "Core inflation: CPI-median", label_fr: "Inflation fondamentale : IPC-méd"}
  - {id: CPI_COMMON,         kind: series, frequency: monthly, role: inflation, label_en: "Core inflation: CPI-common", label_fr: "Inflation fondamentale : IPC-comm"}
```

`config/settings.yml`:
```yaml
start_date: "2000-01-01"
thresholds:
  staleness_days: {daily: 7, weekly: 14, monthly: 75}
  max_null_ratio: 0.20
  value_ranges:
    policy:    [-1.0, 25.0]
    funding:   [-1.0, 25.0]
    yield:     [-2.0, 25.0]
    lending:   [0.0, 30.0]
    inflation: [-5.0, 25.0]
```

- [ ] **Step 4: Write the models**

`pipeline/models.py`:
```python
from pathlib import Path

import yaml
from pydantic import BaseModel


class SeriesConfig(BaseModel):
    id: str
    kind: str = "series"
    label_en: str
    label_fr: str
    frequency: str
    role: str
    metric_key: str | None = None
    source_url: str | None = None


class Thresholds(BaseModel):
    staleness_days: dict[str, int]
    max_null_ratio: float
    value_ranges: dict[str, tuple[float, float]]


class AppConfig(BaseModel):
    start_date: str
    series: list[SeriesConfig]
    thresholds: Thresholds

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
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_models.py -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```bash
git add pipeline/models.py config/series.yml config/settings.yml tests/test_models.py
git commit -m "feat: config models + verified series catalog"
```

---

### Task 3: Valet HTTP client

**Files:**
- Create: `pipeline/valet_client.py`
- Test: `tests/test_valet_client.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `ValetError(Exception)`.
  - `ValetClient(base_url="https://www.bankofcanada.ca/valet", http: httpx.Client | None = None, max_retries: int = 3, backoff: float = 0.5)`.
  - `ValetClient.get_observations(name: str, kind: str = "series", start: str | None = None, recent: int | None = None) -> dict` — returns the parsed JSON body; retries transport errors and 5xx up to `max_retries`; raises `ValetError` on exhaustion or 4xx.

- [ ] **Step 1: Write the failing test**

`tests/test_valet_client.py`:
```python
import httpx
import pytest

from pipeline.valet_client import ValetClient, ValetError

BODY = {"observations": [{"d": "2026-07-13", "V39079": {"v": "2.25"}}]}


def _client(handler) -> ValetClient:
    return ValetClient(http=httpx.Client(transport=httpx.MockTransport(handler)))


def test_series_url_and_params():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json=BODY)

    body = _client(handler).get_observations("V39079", start="2020-01-01")
    assert body == BODY
    assert "/observations/V39079/json" in seen["url"]
    assert "start_date=2020-01-01" in seen["url"]


def test_group_url():
    def handler(request: httpx.Request) -> httpx.Response:
        assert "/observations/group/bond_yields_benchmark/json" in str(request.url)
        return httpx.Response(200, json=BODY)

    _client(handler).get_observations("bond_yields_benchmark", kind="group", recent=1)


def test_retries_then_raises_on_persistent_5xx():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503)

    with pytest.raises(ValetError):
        ValetClient(
            http=httpx.Client(transport=httpx.MockTransport(handler)),
            max_retries=2,
            backoff=0.0,
        ).get_observations("V39079")
    assert calls["n"] == 3  # initial + 2 retries
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_valet_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.valet_client'`.

- [ ] **Step 3: Write the client**

`pipeline/valet_client.py`:
```python
import time

import httpx


class ValetError(Exception):
    pass


class ValetClient:
    def __init__(
        self,
        base_url: str = "https://www.bankofcanada.ca/valet",
        http: httpx.Client | None = None,
        max_retries: int = 3,
        backoff: float = 0.5,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._http = http or httpx.Client(timeout=30.0)
        self._max_retries = max_retries
        self._backoff = backoff

    def get_observations(
        self,
        name: str,
        kind: str = "series",
        start: str | None = None,
        recent: int | None = None,
    ) -> dict:
        path = f"/observations/group/{name}/json" if kind == "group" else f"/observations/{name}/json"
        params: dict[str, str] = {}
        if start is not None:
            params["start_date"] = start
        if recent is not None:
            params["recent"] = str(recent)

        last_err: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                resp = self._http.get(self._base + path, params=params)
            except httpx.TransportError as exc:
                last_err = exc
            else:
                if resp.status_code < 400:
                    return resp.json()
                if resp.status_code < 500:
                    raise ValetError(f"{resp.status_code} for {name}: {resp.text[:200]}")
                last_err = ValetError(f"{resp.status_code} for {name}")
            if attempt < self._max_retries:
                time.sleep(self._backoff * (attempt + 1))
        raise ValetError(f"exhausted retries for {name}: {last_err}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_valet_client.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add pipeline/valet_client.py tests/test_valet_client.py
git commit -m "feat: Valet client with retry/backoff"
```

---

### Task 4: Ingest → dated raw JSON

**Files:**
- Create: `pipeline/ingest.py`
- Test: `tests/test_ingest.py`

**Interfaces:**
- Consumes: `AppConfig` (Task 2), `ValetClient` (Task 3).
- Produces: `run_ingest(config: AppConfig, client: ValetClient, out_root: Path, run_date: str) -> list[Path]` — writes `out_root/<run_date>/<series.id>.json` for every series and returns the written paths. Idempotent (overwrites the same run_date file). On a per-series fetch error, re-raises `ValetError` (fail loud; the CLI decides fallback).

- [ ] **Step 1: Write the failing test**

`tests/test_ingest.py`:
```python
import json
from pathlib import Path

from pipeline.ingest import run_ingest
from pipeline.models import AppConfig, SeriesConfig, Thresholds


class FakeClient:
    def get_observations(self, name, kind="series", start=None, recent=None):
        return {"seriesDetail": {name: {}}, "observations": [{"d": "2026-07-13", name: {"v": "1.0"}}]}


def _cfg() -> AppConfig:
    return AppConfig(
        start_date="2000-01-01",
        series=[
            SeriesConfig(id="V39079", label_en="a", label_fr="a", frequency="daily", role="policy"),
            SeriesConfig(id="CPI_TRIM", label_en="b", label_fr="b", frequency="monthly", role="inflation"),
        ],
        thresholds=Thresholds(staleness_days={"daily": 7}, max_null_ratio=0.2, value_ranges={}),
    )


def test_run_ingest_writes_one_file_per_series(tmp_path: Path):
    paths = run_ingest(_cfg(), FakeClient(), tmp_path, "2026-07-13")
    assert {p.name for p in paths} == {"V39079.json", "CPI_TRIM.json"}
    body = json.loads((tmp_path / "2026-07-13" / "V39079.json").read_text(encoding="utf-8"))
    assert body["observations"][0]["d"] == "2026-07-13"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ingest.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.ingest'`.

- [ ] **Step 3: Write ingest**

`pipeline/ingest.py`:
```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_ingest.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pipeline/ingest.py tests/test_ingest.py
git commit -m "feat: ingest stage writes dated raw JSON"
```

---

### Task 5: Parse — flatten Valet JSON to long rows

**Files:**
- Create: `pipeline/parse.py`
- Test: `tests/test_parse.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `flatten_observations(raw: dict) -> list[dict]` — each row is `{"series_id": str, "obs_date": str, "value": str | None}`. Handles single-series bodies and group bodies (multiple series keys per observation). A missing/empty `{"v": ...}` yields `value=None`. The `"d"` key is the date, never a series.

- [ ] **Step 1: Write the failing test**

`tests/test_parse.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_parse.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.parse'`.

- [ ] **Step 3: Write parse**

`pipeline/parse.py`:
```python
def flatten_observations(raw: dict) -> list[dict]:
    rows: list[dict] = []
    for obs in raw.get("observations", []):
        date = obs.get("d")
        if date is None:
            continue
        for key, cell in obs.items():
            if key == "d":
                continue
            value = cell.get("v") if isinstance(cell, dict) else None
            if value == "":
                value = None
            rows.append({"series_id": key, "obs_date": date, "value": value})
    return rows
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_parse.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add pipeline/parse.py tests/test_parse.py
git commit -m "feat: flatten Valet JSON to long rows"
```

---

### Task 6: Transform — DuckDB dim_series + fact_observation

**Files:**
- Create: `pipeline/transform.sql`
- Create: `pipeline/transform.py`
- Test: `tests/test_transform.py`

**Interfaces:**
- Consumes: `AppConfig` (Task 2), `flatten_observations` output rows (Task 5).
- Produces:
  - `build_curated_con(rows: list[dict], config: AppConfig, ingested_at: str, sql_path: Path = SQL_PATH) -> duckdb.DuckDBPyConnection` — an in-memory connection holding `dim_series` and `fact_observation`.
  - `fact_observation` columns: `series_id VARCHAR`, `date DATE`, `value DOUBLE` (null when unparseable), `is_null BOOLEAN`, `ingested_at TIMESTAMP`. Deduped on `(series_id, date)`.
  - `dim_series` columns: `series_id`, `label_en`, `label_fr`, `frequency`, `role`, `metric_key`, `source_url`.
  - `write_curated(con, out_dir: Path) -> None` — COPY both tables to `out_dir/{dim_series,fact_observation}.parquet`.
  - `SQL_PATH: Path` — module-level path to `transform.sql`.

- [ ] **Step 1: Write the failing test**

`tests/test_transform.py`:
```python
from pipeline.models import AppConfig, SeriesConfig, Thresholds
from pipeline.transform import build_curated_con, write_curated


def _cfg() -> AppConfig:
    return AppConfig(
        start_date="2000-01-01",
        series=[SeriesConfig(id="V39079", label_en="Policy", label_fr="Politique",
                             frequency="daily", role="policy")],
        thresholds=Thresholds(staleness_days={"daily": 7}, max_null_ratio=0.2, value_ranges={}),
    )


ROWS = [
    {"series_id": "V39079", "obs_date": "2026-07-10", "value": "2.25"},
    {"series_id": "V39079", "obs_date": "2026-07-13", "value": None},
    {"series_id": "V39079", "obs_date": "2026-07-13", "value": None},  # duplicate date
]


def test_fact_types_dedup_and_null_flag():
    con = build_curated_con(ROWS, _cfg(), ingested_at="2026-07-14T00:00:00")
    facts = con.execute(
        "SELECT date::VARCHAR, value, is_null FROM fact_observation ORDER BY date"
    ).fetchall()
    assert facts == [("2026-07-10", 2.25, False), ("2026-07-13", None, True)]


def test_dim_series_carries_bilingual_labels():
    con = build_curated_con(ROWS, _cfg(), ingested_at="2026-07-14T00:00:00")
    row = con.execute(
        "SELECT label_en, label_fr, role FROM dim_series WHERE series_id = 'V39079'"
    ).fetchone()
    assert row == ("Policy", "Politique", "policy")


def test_write_curated_emits_parquet(tmp_path):
    con = build_curated_con(ROWS, _cfg(), ingested_at="2026-07-14T00:00:00")
    write_curated(con, tmp_path)
    assert (tmp_path / "fact_observation.parquet").exists()
    assert (tmp_path / "dim_series.parquet").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_transform.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.transform'`.

- [ ] **Step 3: Write the SQL**

`pipeline/transform.sql`:
```sql
-- Requires temp tables: stg_observation(series_id, obs_date, value) and
-- a session variable 'ingested_at'. Produces fact_observation.
CREATE OR REPLACE TABLE fact_observation AS
SELECT
    series_id,
    CAST(obs_date AS DATE)                          AS date,
    TRY_CAST(value AS DOUBLE)                       AS value,
    (TRY_CAST(value AS DOUBLE) IS NULL)             AS is_null,
    CAST(getvariable('ingested_at') AS TIMESTAMP)   AS ingested_at
FROM stg_observation
WHERE obs_date IS NOT NULL
QUALIFY row_number() OVER (
    PARTITION BY series_id, obs_date
    ORDER BY TRY_CAST(value AS DOUBLE) DESC NULLS LAST
) = 1
ORDER BY series_id, date;
```

- [ ] **Step 4: Write the transform module**

`pipeline/transform.py`:
```python
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_transform.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add pipeline/transform.py pipeline/transform.sql tests/test_transform.py
git commit -m "feat: DuckDB transform to dim_series + fact_observation"
```

---

### Task 7: Metrics — yield slope + household spread (ASOF joins)

**Files:**
- Create: `pipeline/metrics.py`
- Test: `tests/test_metrics.py`

**Interfaces:**
- Consumes: a DuckDB connection holding `fact_observation` (Task 6); `AppConfig.by_metric_key` (Task 2).
- Produces:
  - `compute_yield_slope(con, id_2y: str, id_10y: str) -> list[dict]` — rows `{"date": str, "slope": float, "inverted": bool}` where `slope = yield_10y - yield_2y` (as-of prior 2y).
  - `compute_household_spread(con, id_mortgage: str, id_5y: str) -> list[dict]` — rows `{"date": str, "spread": float}` where `spread = mortgage - yield_5y` (as-of nearest prior yield).
  - `run_metrics(con, config: AppConfig) -> dict` — `{"yield_slope": [...], "household_spread": [...]}` using `metric_key` lookups (`yield_2y`, `yield_10y`, `yield_5y`, `mortgage_5y_fixed`).

- [ ] **Step 1: Write the failing test**

`tests/test_metrics.py`:
```python
from pipeline.metrics import compute_household_spread, compute_yield_slope
from pipeline.models import AppConfig, SeriesConfig, Thresholds
from pipeline.transform import build_curated_con

ROWS = [
    {"series_id": "Y2", "obs_date": "2026-07-13", "value": "3.00"},
    {"series_id": "Y10", "obs_date": "2026-07-13", "value": "2.50"},   # inverted (10y < 2y)
    {"series_id": "Y5", "obs_date": "2026-07-10", "value": "2.80"},
    {"series_id": "MTG", "obs_date": "2026-07-31", "value": "5.30"},   # monthly, as-of 5y on 07-10
]


def _cfg() -> AppConfig:
    def mk(i, k):
        return SeriesConfig(id=i, label_en=i, label_fr=i, frequency="daily", role="yield", metric_key=k)

    return AppConfig(
        start_date="2000-01-01",
        series=[mk("Y2", "yield_2y"), mk("Y10", "yield_10y"), mk("Y5", "yield_5y"),
                SeriesConfig(id="MTG", label_en="m", label_fr="m", frequency="monthly",
                             role="lending", metric_key="mortgage_5y_fixed")],
        thresholds=Thresholds(staleness_days={"daily": 7}, max_null_ratio=0.2, value_ranges={}),
    )


def test_yield_slope_and_inversion():
    con = build_curated_con(ROWS, _cfg(), ingested_at="2026-07-14T00:00:00")
    slope = compute_yield_slope(con, "Y2", "Y10")
    assert slope == [{"date": "2026-07-13", "slope": -0.5, "inverted": True}]


def test_household_spread_asof_prior_yield():
    con = build_curated_con(ROWS, _cfg(), ingested_at="2026-07-14T00:00:00")
    spread = compute_household_spread(con, "MTG", "Y5")
    assert spread == [{"date": "2026-07-31", "spread": 2.5}]  # 5.30 - 2.80
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_metrics.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.metrics'`.

- [ ] **Step 3: Write metrics**

`pipeline/metrics.py`:
```python
import duckdb

from pipeline.models import AppConfig

_SLOPE_SQL = """
SELECT a.date::VARCHAR AS date,
       round(a.value - b.value, 10) AS slope,
       (a.value - b.value) < 0 AS inverted
FROM (SELECT date, value FROM fact_observation WHERE series_id = ? AND value IS NOT NULL) a
ASOF JOIN (SELECT date, value FROM fact_observation WHERE series_id = ? AND value IS NOT NULL) b
  ON a.date >= b.date
ORDER BY a.date
"""

_SPREAD_SQL = """
SELECT a.date::VARCHAR AS date,
       round(a.value - b.value, 10) AS spread
FROM (SELECT date, value FROM fact_observation WHERE series_id = ? AND value IS NOT NULL) a
ASOF JOIN (SELECT date, value FROM fact_observation WHERE series_id = ? AND value IS NOT NULL) b
  ON a.date >= b.date
ORDER BY a.date
"""


def compute_yield_slope(con: duckdb.DuckDBPyConnection, id_2y: str, id_10y: str) -> list[dict]:
    rows = con.execute(_SLOPE_SQL, [id_10y, id_2y]).fetchall()
    return [{"date": d, "slope": s, "inverted": bool(inv)} for d, s, inv in rows]


def compute_household_spread(con: duckdb.DuckDBPyConnection, id_mortgage: str, id_5y: str) -> list[dict]:
    rows = con.execute(_SPREAD_SQL, [id_mortgage, id_5y]).fetchall()
    return [{"date": d, "spread": s} for d, s in rows]


def run_metrics(con: duckdb.DuckDBPyConnection, config: AppConfig) -> dict:
    return {
        "yield_slope": compute_yield_slope(
            con, config.by_metric_key("yield_2y").id, config.by_metric_key("yield_10y").id
        ),
        "household_spread": compute_household_spread(
            con, config.by_metric_key("mortgage_5y_fixed").id, config.by_metric_key("yield_5y").id
        ),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_metrics.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add pipeline/metrics.py tests/test_metrics.py
git commit -m "feat: yield slope + household spread via ASOF joins"
```

---

### Task 8: Quality — checks + report

**Files:**
- Create: `pipeline/quality.py`
- Test: `tests/test_quality.py`

**Interfaces:**
- Consumes: a DuckDB connection with `fact_observation` (Task 6); `AppConfig` (Task 2).
- Produces:
  - `@dataclass SeriesQuality(series_id: str, status: str, checks: dict[str, str])`.
  - `@dataclass QualityReport(generated_at: str, overall: str, series: list[SeriesQuality])`.
  - `run_quality(con, config: AppConfig, as_of: str) -> QualityReport` — per series runs freshness, null-ratio, value-range, monotonicity; `status` is worst of the four (`FAIL` > `WARN` > `OK`); `overall` is worst across series.
  - `report_to_dict(report: QualityReport) -> dict` and `write_report(report: QualityReport, path: Path) -> None`.
  - Status rules: value out of `value_ranges[role]` → **FAIL**; latest non-null older than `staleness_days[frequency]` → **FAIL**; duplicate dates → **FAIL**; null-ratio > `max_null_ratio` → **WARN**.

- [ ] **Step 1: Write the failing test**

`tests/test_quality.py`:
```python
import json

from pipeline.models import AppConfig, SeriesConfig, Thresholds
from pipeline.quality import report_to_dict, run_quality, write_report
from pipeline.transform import build_curated_con


def _cfg(role="policy", freq="daily") -> AppConfig:
    return AppConfig(
        start_date="2000-01-01",
        series=[SeriesConfig(id="S", label_en="s", label_fr="s", frequency=freq, role=role)],
        thresholds=Thresholds(
            staleness_days={"daily": 7, "monthly": 75},
            max_null_ratio=0.20,
            value_ranges={"policy": (-1.0, 25.0)},
        ),
    )


def _con(rows):
    return build_curated_con(rows, _cfg(), ingested_at="2026-07-14T00:00:00")


def test_fresh_in_range_is_ok():
    con = _con([{"series_id": "S", "obs_date": "2026-07-13", "value": "2.25"}])
    report = run_quality(con, _cfg(), as_of="2026-07-14")
    assert report.overall == "OK"


def test_stale_series_fails():
    con = _con([{"series_id": "S", "obs_date": "2026-01-01", "value": "2.25"}])
    report = run_quality(con, _cfg(), as_of="2026-07-14")
    assert report.series[0].status == "FAIL"
    assert "fresh" in report.series[0].checks["freshness"].lower()


def test_out_of_range_fails():
    con = _con([{"series_id": "S", "obs_date": "2026-07-13", "value": "999"}])
    report = run_quality(con, _cfg(), as_of="2026-07-14")
    assert report.series[0].status == "FAIL"


def test_high_null_ratio_warns():
    rows = [{"series_id": "S", "obs_date": f"2026-07-{d:02d}", "value": None} for d in (10, 11, 12)]
    rows.append({"series_id": "S", "obs_date": "2026-07-13", "value": "2.25"})
    con = _con(rows)
    report = run_quality(con, _cfg(), as_of="2026-07-14")
    assert report.series[0].status == "WARN"


def test_write_report_roundtrips(tmp_path):
    con = _con([{"series_id": "S", "obs_date": "2026-07-13", "value": "2.25"}])
    report = run_quality(con, _cfg(), as_of="2026-07-14")
    write_report(report, tmp_path / "dq.json")
    loaded = json.loads((tmp_path / "dq.json").read_text(encoding="utf-8"))
    assert loaded["overall"] == "OK"
    assert loaded["series"][0]["series_id"] == "S"
    assert report_to_dict(report)["overall"] == "OK"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_quality.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.quality'`.

- [ ] **Step 3: Write quality**

`pipeline/quality.py`:
```python
import json
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

import duckdb

from pipeline.models import AppConfig

_ORDER = {"OK": 0, "WARN": 1, "FAIL": 2}


def _worst(statuses: list[str]) -> str:
    return max(statuses, key=lambda s: _ORDER[s]) if statuses else "OK"


@dataclass
class SeriesQuality:
    series_id: str
    status: str
    checks: dict[str, str]


@dataclass
class QualityReport:
    generated_at: str
    overall: str
    series: list[SeriesQuality]


def run_quality(con: duckdb.DuckDBPyConnection, config: AppConfig, as_of: str) -> QualityReport:
    as_of_date = date.fromisoformat(as_of)
    results: list[SeriesQuality] = []
    for s in config.series:
        stats = con.execute(
            "SELECT count(*), count(*) FILTER (WHERE is_null), "
            "max(date) FILTER (WHERE NOT is_null), "
            "min(value), max(value), count(DISTINCT date) "
            "FROM fact_observation WHERE series_id = ?",
            [s.id],
        ).fetchone()
        total, nulls, latest, vmin, vmax, distinct_dates = stats
        checks: dict[str, str] = {}
        statuses: list[str] = []

        # Freshness
        limit = config.thresholds.staleness_days.get(s.frequency, 9999)
        if latest is None:
            checks["freshness"] = "no non-null observations"
            statuses.append("FAIL")
        else:
            age = (as_of_date - latest).days
            if age > limit:
                checks["freshness"] = f"not fresh: {age}d old (> {limit}d)"
                statuses.append("FAIL")
            else:
                checks["freshness"] = f"fresh: {age}d old"
                statuses.append("OK")

        # Value range
        lo, hi = config.thresholds.value_ranges.get(s.role, (float("-inf"), float("inf")))
        if vmin is not None and (vmin < lo or vmax > hi):
            checks["value_range"] = f"out of [{lo}, {hi}]: min={vmin}, max={vmax}"
            statuses.append("FAIL")
        else:
            checks["value_range"] = "within range"
            statuses.append("OK")

        # Monotonic / no duplicate dates
        if total != distinct_dates:
            checks["monotonic"] = f"duplicate dates: {total - distinct_dates}"
            statuses.append("FAIL")
        else:
            checks["monotonic"] = "no duplicate dates"
            statuses.append("OK")

        # Null ratio
        ratio = (nulls / total) if total else 0.0
        if ratio > config.thresholds.max_null_ratio:
            checks["null_ratio"] = f"high nulls: {ratio:.0%}"
            statuses.append("WARN")
        else:
            checks["null_ratio"] = f"nulls: {ratio:.0%}"
            statuses.append("OK")

        results.append(SeriesQuality(series_id=s.id, status=_worst(statuses), checks=checks))

    return QualityReport(
        generated_at=f"{as_of}T00:00:00",
        overall=_worst([r.status for r in results]),
        series=results,
    )


def report_to_dict(report: QualityReport) -> dict:
    return asdict(report)


def write_report(report: QualityReport, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report_to_dict(report), ensure_ascii=False, indent=2), encoding="utf-8")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_quality.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add pipeline/quality.py tests/test_quality.py
git commit -m "feat: data-quality checks + report"
```

---

### Task 9: build_web + run CLI (end-to-end)

**Files:**
- Create: `pipeline/build_web.py`
- Create: `pipeline/run.py`
- Test: `tests/test_build_web.py`

**Interfaces:**
- Consumes: a DuckDB connection with `fact_observation` + `dim_series` (Task 6); `run_metrics` (Task 7); `QualityReport`/`report_to_dict` (Task 8); `AppConfig` (Task 2).
- Produces:
  - `series_points(con, series_id: str) -> list[list]` — `[[date_str, value_or_None], ...]` ordered by date.
  - `build_web(con, config, metrics: dict, quality: dict, out_dir: Path, as_of: str) -> list[Path]` — writes `panel_policy.json`, `panel_markets.json`, `panel_households.json`, `panel_target.json`, `data_quality.json`, `manifest.json` under `out_dir` and returns the paths. `manifest.json` includes `{"as_of": as_of, "last_refreshed": ..., "overall_quality": quality["overall"], "panels": [...]}`.
  - `pipeline/run.py` `main(argv=None) -> int` — CLI: `--config-dir`, `--raw-root`, `--curated-dir`, `--web-dir`, `--run-date`, `--ingested-at`, `--offline` (skip ingest, reuse raw). Chains ingest → flatten → transform → metrics → quality → build_web. On ingest failure with existing raw for `run_date`, logs and continues (never publishes empty).

- [ ] **Step 1: Write the failing test**

`tests/test_build_web.py`:
```python
import json

from pipeline.build_web import build_web, series_points
from pipeline.metrics import run_metrics
from pipeline.models import AppConfig, SeriesConfig, Thresholds
from pipeline.quality import report_to_dict, run_quality
from pipeline.transform import build_curated_con

ROWS = [
    {"series_id": "V39079", "obs_date": "2026-07-13", "value": "2.25"},
    {"series_id": "BD.CDN.2YR.DQ.YLD", "obs_date": "2026-07-13", "value": "3.0"},
    {"series_id": "BD.CDN.5YR.DQ.YLD", "obs_date": "2026-07-13", "value": "3.2"},
    {"series_id": "BD.CDN.10YR.DQ.YLD", "obs_date": "2026-07-13", "value": "3.5"},
    {"series_id": "V122667780", "obs_date": "2026-07-31", "value": "5.3"},
    {"series_id": "CPI_TRIM", "obs_date": "2026-06-30", "value": "2.4"},
]


def _cfg() -> AppConfig:
    def y(i, k):
        return SeriesConfig(id=i, label_en=i, label_fr=i, frequency="daily", role="yield", metric_key=k)

    return AppConfig(
        start_date="2000-01-01",
        series=[
            SeriesConfig(id="V39079", label_en="Policy", label_fr="Politique", frequency="daily", role="policy"),
            y("BD.CDN.2YR.DQ.YLD", "yield_2y"),
            y("BD.CDN.5YR.DQ.YLD", "yield_5y"),
            y("BD.CDN.10YR.DQ.YLD", "yield_10y"),
            SeriesConfig(id="V122667780", label_en="Mtg", label_fr="Hyp", frequency="monthly",
                         role="lending", metric_key="mortgage_5y_fixed"),
            SeriesConfig(id="CPI_TRIM", label_en="Trim", label_fr="Tronq", frequency="monthly", role="inflation"),
        ],
        thresholds=Thresholds(
            staleness_days={"daily": 7, "monthly": 400},
            max_null_ratio=0.5,
            value_ranges={},
        ),
    )


def test_series_points_orders_by_date():
    con = build_curated_con(ROWS, _cfg(), ingested_at="2026-07-14T00:00:00")
    assert series_points(con, "V39079") == [["2026-07-13", 2.25]]


def test_build_web_emits_all_panels_and_manifest(tmp_path):
    cfg = _cfg()
    con = build_curated_con(ROWS, cfg, ingested_at="2026-07-14T00:00:00")
    metrics = run_metrics(con, cfg)
    quality = report_to_dict(run_quality(con, cfg, as_of="2026-07-14"))
    paths = build_web(con, cfg, metrics, quality, tmp_path, as_of="2026-07-14")
    names = {p.name for p in paths}
    assert {"panel_policy.json", "panel_markets.json", "panel_households.json",
            "panel_target.json", "data_quality.json", "manifest.json"} <= names
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["as_of"] == "2026-07-14"
    markets = json.loads((tmp_path / "panel_markets.json").read_text(encoding="utf-8"))
    assert markets["yield_slope"][0]["inverted"] is False  # 10y(3.5) - 2y(3.0) = +0.5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_build_web.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.build_web'`.

- [ ] **Step 3: Write build_web**

`pipeline/build_web.py`:
```python
import json
from pathlib import Path

import duckdb

from pipeline.models import AppConfig


def series_points(con: duckdb.DuckDBPyConnection, series_id: str) -> list[list]:
    rows = con.execute(
        "SELECT date::VARCHAR, value FROM fact_observation WHERE series_id = ? ORDER BY date",
        [series_id],
    ).fetchall()
    return [[d, v] for d, v in rows]


def _series_block(con: duckdb.DuckDBPyConnection, s) -> dict:
    return {
        "id": s.id,
        "label_en": s.label_en,
        "label_fr": s.label_fr,
        "role": s.role,
        "points": series_points(con, s.id),
    }


def _write(out_dir: Path, name: str, payload: dict) -> Path:
    path = out_dir / name
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def build_web(
    con: duckdb.DuckDBPyConnection,
    config: AppConfig,
    metrics: dict,
    quality: dict,
    out_dir: Path,
    as_of: str,
) -> list[Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    by_role: dict[str, list] = {}
    for s in config.series:
        by_role.setdefault(s.role, []).append(s)

    paths: list[Path] = []
    paths.append(_write(out_dir, "panel_policy.json", {
        "series": [_series_block(con, s) for s in by_role.get("policy", []) + by_role.get("funding", [])],
    }))
    paths.append(_write(out_dir, "panel_markets.json", {
        "yields": [_series_block(con, s) for s in by_role.get("yield", [])],
        "policy": [_series_block(con, s) for s in by_role.get("policy", [])],
        "yield_slope": metrics["yield_slope"],
    }))
    paths.append(_write(out_dir, "panel_households.json", {
        "lending": [_series_block(con, s) for s in by_role.get("lending", [])],
        "yield5": [_series_block(con, s) for s in config.series if s.metric_key == "yield_5y"],
        "spread": metrics["household_spread"],
    }))
    paths.append(_write(out_dir, "panel_target.json", {
        "core": [_series_block(con, s) for s in by_role.get("inflation", [])],
        "band": {"low": 1.0, "high": 3.0},
    }))
    paths.append(_write(out_dir, "data_quality.json", quality))
    paths.append(_write(out_dir, "manifest.json", {
        "as_of": as_of,
        "last_refreshed": quality.get("generated_at", f"{as_of}T00:00:00"),
        "overall_quality": quality.get("overall", "OK"),
        "panels": ["policy", "markets", "households", "target"],
    }))
    return paths
```

- [ ] **Step 4: Write the CLI**

`pipeline/run.py`:
```python
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

    if not args.offline:
        try:
            run_ingest(config, ValetClient(), raw_root, args.run_date)
        except ValetError as exc:
            if not (raw_root / args.run_date).exists():
                print(f"ingest failed and no cached raw for {args.run_date}: {exc}", file=sys.stderr)
                return 2
            print(f"ingest failed; reusing cached raw for {args.run_date}: {exc}", file=sys.stderr)

    rows = _read_raw(raw_root, args.run_date)
    con = build_curated_con(rows, config, ingested_at=args.ingested_at)
    write_curated(con, Path(args.curated_dir))

    metrics = run_metrics(con, config)
    report = run_quality(con, config, as_of=args.run_date)
    write_report(report, Path(args.curated_dir) / "data_quality.json")
    build_web(con, config, metrics, report_to_dict(report), Path(args.web_dir), as_of=args.run_date)

    print(f"pipeline OK — overall quality: {report.overall}")
    return 1 if report.overall == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_build_web.py -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Run the full pipeline live (integration smoke)**

Run: `python -m pipeline.run --run-date 2026-07-14 --ingested-at 2026-07-14T12:00:00`
Expected: prints `pipeline OK — overall quality: OK` (or `WARN`); `site/data/manifest.json` and the four `panel_*.json` exist and contain real observations. Exit code 0 (or 1 only if a series legitimately FAILs).

- [ ] **Step 7: Run the whole test suite + lint**

Run: `python -m pytest -q && ruff check .`
Expected: all tests pass; lint clean.

- [ ] **Step 8: Commit**

```bash
git add pipeline/build_web.py pipeline/run.py tests/test_build_web.py
git commit -m "feat: build_web panels + end-to-end run CLI"
```

- [ ] **Step 9: Commit the first real data snapshot**

```bash
git add data/ site/data/
git commit -m "data: first BoC Valet snapshot + published panels"
```

---

## Self-Review

**Spec coverage (against `2026-07-14-inflation-tracker-design.md`):**
- §3 architecture (ingest → transform → quality → build_web) — Tasks 4, 6, 8, 9. ✅
- §5 components / interfaces — Tasks 3–9 match the spec's signatures. ✅
- §6 data model (`dim_series`, `fact_observation`) — Task 6. ✅
- §7 verified series — Task 2 config (IDs re-verified live 2026-07-14). ✅
- §8 panels — Task 9 emits the four panel JSONs; §8 *rendering* is Plan 2. ✅ (data side)
- §9 data-quality checks (freshness/null/range/monotonic) — Task 8. Revision-diff is deferred to Plan 2 (needs a persisted prior snapshot); noted here so it is not silently dropped.
- §10 error handling (retry/backoff, keep-last-good, as-of joins) — Tasks 3, 7, 9. ✅
- §11 testing — every task is TDD; CI wiring is Plan 2. ✅
- §8 methodology page, §12 hosting/i18n site, §13 M3–M4, Data-Trust tab **rendering**, CI/deploy — **Plan 2** (dashboard + deploy). Explicitly out of scope here.

**Placeholder scan:** No TBD/TODO; every code step is complete and runnable. ✅

**Type consistency:** `build_curated_con` returns a connection reused by `run_metrics`, `run_quality`, `build_web`. `AppConfig.by_metric_key` used consistently (`yield_2y/5y/10y`, `mortgage_5y_fixed`). `report_to_dict` feeds `build_web(quality=...)`. `run_quality(as_of=run_date)` matches the CLI. ✅

**Deferred-to-Plan-2 (tracked, not dropped):** static site render, Data-Trust + methodology pages, revision-diff check, `ci.yml` + `refresh.yml`, README + Pages deploy.

## Execution Handoff

Two execution options:
1. **Subagent-Driven (recommended)** — a fresh subagent per task, review between tasks, two-stage review.
2. **Inline Execution** — execute tasks in this session with checkpoints.
