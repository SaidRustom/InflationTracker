# Inflation Tracker — Dashboard Implementation Plan (Plan 2 of 3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the bilingual static dashboard (spec milestone **M3**) — four ECharts panels telling the transmission story, served from the committed `site/data/*.json`, with a working EN/FR toggle.

**Architecture:** No build step and no framework. `site/index.html` loads vanilla ES modules and a vendored ECharts, then renders panels purely from the JSON that `pipeline/build_web.py` already publishes. The page never calls the Valet API (spec §14: CORS/terms). Three small pipeline changes come first, because the dashboard needs data the pipeline does not yet emit (headline CPI, the band, the months-inside-band indicator) — and because a latent staleness bug takes the pipeline red on 2026-07-16.

**Tech Stack:** Python 3.12 · DuckDB · pydantic · pytest · ruff · vanilla ES modules · Apache ECharts 6.1.0 (vendored, Apache-2.0)

**Scope note:** This is Plan **2 of 3**. Spec milestone **M4** (Data-Trust tab, methodology page, revision-diff check, `ci.yml` + `refresh.yml`, README, Pages deploy) moves to **Plan 3** so that this plan ships something reviewable on its own.

## Global Constraints

Every task's requirements implicitly include this section.

- **Env:** Python 3.12 in `.venv`, created with **stdlib `venv`, not `uv venv`** (uv's launcher stub is blocked by antivirus on this machine).
- **Test:** `.venv\Scripts\python.exe -m pytest -q` · **Lint:** `.venv\Scripts\python.exe -m ruff check .`
- **Both must be green before every commit.** Baseline entering this plan: **22 tests passing, ruff clean.**
- **No JS framework, no bundler, no build step, no npm.** Vanilla ES modules only.
- **No browser calls to the Valet API.** The page reads only `site/data/*.json`. (spec §14)
- **Bilingual from day one.** Every user-facing string resolves through `site/i18n/{en,fr}.json`. **No hardcoded copy in HTML or JS.** (spec §14 — "no late retrofit")
  - Clarification: English text *inside* a `[data-i18n]` element is a permitted pre-boot / no-JS fallback, because `applyStaticText` overwrites it on boot. It must never be the **only** source of a string. Any element holding user-facing text — **including `<title>`** — must carry a `data-i18n` key.
- **Language via `?lang=en|fr`.** Decision 2026-07-15; **supersedes spec §12's URL-segment (`/en`, `/fr`)**. Default `en`; unknown values fall back to `en`.
- **Bright lines (spec §2), non-negotiable:** no financial advice, no rate predictions, no "lock-in" nudges. Descriptive only. A disclaimer ships on the page. Never present a posted rate as a usable consumer rate; the spread is an **observed** quantity, never a derived prediction.
- **Attribution:** BoC credit + a link to `https://www.bankofcanada.ca/terms/` must be visible on the page.
- **Series IDs live in `config/`, never in code.**
- **Exact ECharts version: 6.1.0**, vendored at `site/assets/vendor/echarts-6.1.0.min.js`. Keep its Apache-2.0 license banner intact.

---

### Task 1: Fix the monthly staleness threshold (pipeline goes red 2026-07-16)

**Why this is first:** `config/settings.yml` sets `staleness_days.monthly: 75`. All four monthly series (`CPI_TRIM`, `CPI_MEDIAN`, `CPI_COMMON`, `V122667780`) are **74 days old as of 2026-07-14**. Verified by simulation: at `as_of` 2026-07-16 all four flip to **FAIL**, `run_quality` returns `overall="FAIL"`, and `pipeline/run.py:57` exits **1**.

This is a **false alarm, not real staleness**. Monthly observations are dated to the *month start* (May CPI is dated `2026-05-01`) but publish roughly six weeks later. May CPI stays the newest observation until June CPI publishes around 2026-07-17 — so the newest observation legitimately reaches **~77 days old** on the normal cycle. A 75-day threshold sits *below* the cycle's high-water mark, so it misfires every single month. Raising it to **95** keeps a genuinely discontinued series alarming (the spec's Oct-2019 precedent: a dead series goes months stale) while never firing on a healthy one.

**Files:**
- Modify: `config/settings.yml:3`
- Test: `tests/test_quality.py`

**Interfaces:**
- Consumes: `run_quality(con, config, as_of) -> QualityReport` and `Thresholds.staleness_days: dict[str, int]` (both already exist).
- Produces: nothing new. Behaviour change only.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_quality.py`:

```python
from pathlib import Path

from pipeline.models import load_config


def _monthly_cfg() -> AppConfig:
    return AppConfig(
        start_date="2000-01-01",
        series=[SeriesConfig(id="S", label_en="s", label_fr="s", frequency="monthly", role="inflation")],
        thresholds=Thresholds(
            staleness_days={"daily": 7, "monthly": 95},
            max_null_ratio=0.20,
            value_ranges={"inflation": (-5.0, 25.0)},
        ),
    )


def test_monthly_series_inside_publication_lag_is_ok():
    # May CPI is dated 2026-05-01 and stays the newest observation until June CPI
    # publishes ~2026-07-17. ~77 days old is a normal cycle, not staleness.
    cfg = _monthly_cfg()
    con = build_curated_con(
        [{"series_id": "S", "obs_date": "2026-05-01", "value": "2.0"}],
        cfg,
        ingested_at="2026-07-16T00:00:00",
    )
    report = run_quality(con, cfg, as_of="2026-07-16")
    assert report.series[0].status == "OK"


def test_monthly_series_missing_two_releases_still_fails():
    # A monthly series that has skipped ~2 releases is genuinely stale and must alarm.
    cfg = _monthly_cfg()
    con = build_curated_con(
        [{"series_id": "S", "obs_date": "2026-03-01", "value": "2.0"}],
        cfg,
        ingested_at="2026-07-16T00:00:00",
    )
    report = run_quality(con, cfg, as_of="2026-07-16")
    assert report.series[0].status == "FAIL"


def test_shipped_config_monthly_threshold_survives_publication_lag():
    # Pins the real config file, which is where the bug lived.
    cfg_dir = Path(__file__).resolve().parents[1] / "config"
    cfg = load_config(cfg_dir / "series.yml", cfg_dir / "settings.yml")
    assert cfg.thresholds.staleness_days["monthly"] >= 80
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_quality.py -q -k "publication_lag or two_releases"`

Expected: `test_shipped_config_monthly_threshold_survives_publication_lag` FAILS with `assert 75 >= 80`. The other two PASS already (their fixture hardcodes 95) — they are regression guards proving the fix does not break genuine staleness detection.

- [ ] **Step 3: Apply the fix**

In `config/settings.yml`, change the `staleness_days` line:

```yaml
start_date: "2000-01-01"
thresholds:
  # monthly: CPI observations are dated to the month start but publish ~6 weeks later,
  # so the newest observation legitimately reaches ~77d old just before the next
  # release. 95 tolerates the normal cycle while still alarming on a dead series.
  staleness_days: {daily: 7, weekly: 14, monthly: 95}
  max_null_ratio: 0.20
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest -q`
Expected: PASS (25 tests — 22 baseline + 3 new).

- [ ] **Step 5: Verify the pipeline is no longer red at tomorrow's date**

Run:

```bash
.venv/Scripts/python.exe -c "
from pathlib import Path
from pipeline.models import load_config
from pipeline.quality import run_quality
from pipeline.transform import build_curated_con
from pipeline.run import _read_raw
cfg = load_config(Path('config/series.yml'), Path('config/settings.yml'))
con = build_curated_con(_read_raw(Path('data/raw'), '2026-07-14'), cfg, ingested_at='2026-07-14T00:00:00')
for asof in ['2026-07-16', '2026-07-20', '2026-08-01']:
    r = run_quality(con, cfg, as_of=asof)
    print(asof, r.overall, [s.series_id for s in r.series if s.status != 'OK'])
"
```

Expected: `2026-07-16 OK []`, `2026-07-20 OK []`, `2026-08-01 OK []` (was `FAIL` for the first two before the fix).

- [ ] **Step 6: Commit**

```bash
git add config/settings.yml tests/test_quality.py
git commit -m "fix: monthly staleness threshold false-FAILs on CPI publication lag

Monthly observations are dated to the month start but publish ~6 weeks
later, so the newest CPI legitimately reaches ~77d old before the next
release. The 75d threshold sat below that high-water mark and would have
taken the pipeline red on 2026-07-16 with all four monthly series FAIL.

Raise to 95d: tolerates the normal cycle, still alarms on a dead series."
```

---

### Task 2: Add headline CPI (`STATIC_TOTALCPICHANGE`) and the `headline` role

**Why:** Spec §8 panel 4 calls for "headline CPI + core (trim/median/common)" against the band, but only the three core measures were ever configured. The Bank's inflation-control target is defined on **total CPI**, so panel 4 without headline understates the story. Verified live 2026-07-15: `STATIC_TOTALCPICHANGE` = **3.2%** (2026-05-01) — *above* the 1–3% band while core sits inside it.

Headline needs its own `role`, not `inflation` — `build_web` maps `by_role["inflation"]` into `panel_target.core`, so reusing `inflation` would silently file headline as a core measure.

**Files:**
- Modify: `config/series.yml` (append one series)
- Modify: `config/settings.yml` (add `headline` value range)
- Modify: `pipeline/build_web.py:61-64`
- Test: `tests/test_build_web.py`

**Interfaces:**
- Consumes: `build_web(con, config, metrics, quality, out_dir, as_of) -> list[Path]`; `SeriesConfig(id, kind, label_en, label_fr, frequency, role, metric_key)`.
- Produces: `panel_target.json` gains a **`headline`** key alongside `core` and `band`, shaped like the existing series blocks: `{"id", "label_en", "label_fr", "role", "points": [[date, value], ...]}`. Task 5 (band metric) and Task 9 (panel 4 UI) both depend on this key existing. New `metric_key` **`cpi_headline`** is how Task 3 resolves the series.

- [ ] **Step 1: Write the failing test**

In `tests/test_build_web.py`, add the headline row to `ROWS` and the series to `_cfg()`, then add the test.

Add to `ROWS` (after the `CPI_TRIM` entry):

```python
    {"series_id": "STATIC_TOTALCPICHANGE", "obs_date": "2026-06-30", "value": "3.2"},
```

Add to the `series=[...]` list in `_cfg()` (after the `CPI_TRIM` entry):

```python
            SeriesConfig(id="STATIC_TOTALCPICHANGE", label_en="Total CPI", label_fr="IPC global",
                         frequency="monthly", role="headline", metric_key="cpi_headline"),
```

Add the test:

```python
def test_panel_target_separates_headline_from_core(tmp_path):
    cfg = _cfg()
    con = build_curated_con(ROWS, cfg, ingested_at="2026-07-14T00:00:00")
    metrics = run_metrics(con, cfg)
    quality = report_to_dict(run_quality(con, cfg, as_of="2026-07-14"))
    build_web(con, cfg, metrics, quality, tmp_path, as_of="2026-07-14")
    target = json.loads((tmp_path / "panel_target.json").read_text(encoding="utf-8"))

    assert [s["id"] for s in target["headline"]] == ["STATIC_TOTALCPICHANGE"]
    assert target["headline"][0]["points"] == [["2026-06-30", 3.2]]
    # headline must not leak into core
    assert [s["id"] for s in target["core"]] == ["CPI_TRIM"]
    assert target["band"] == {"low": 1.0, "high": 3.0}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_build_web.py::test_panel_target_separates_headline_from_core -q`
Expected: FAIL with `KeyError: 'headline'`.

- [ ] **Step 3: Emit the headline block**

In `pipeline/build_web.py`, replace the `panel_target.json` write (lines 61-64):

```python
    paths.append(_write(out_dir, "panel_target.json", {
        "headline": [_series_block(con, s) for s in by_role.get("headline", [])],
        "core": [_series_block(con, s) for s in by_role.get("inflation", [])],
        "band": {"low": 1.0, "high": 3.0},
    }))
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_build_web.py -q`
Expected: PASS.

- [ ] **Step 5: Add the series to the real config**

Append to `config/series.yml`:

```yaml
  - {id: STATIC_TOTALCPICHANGE, kind: series, frequency: monthly, role: headline, metric_key: cpi_headline, label_en: "Total CPI (headline)", label_fr: "IPC global (ensemble)"}
```

Add the `headline` range under `value_ranges` in `config/settings.yml` (same bounds as `inflation`):

```yaml
    inflation: [-5.0, 25.0]
    headline:  [-5.0, 25.0]
```

- [ ] **Step 6: Run the full suite and lint**

Run: `.venv\Scripts\python.exe -m pytest -q && .venv\Scripts\python.exe -m ruff check .`
Expected: PASS, ruff clean.

- [ ] **Step 7: Commit**

```bash
git add config/series.yml config/settings.yml pipeline/build_web.py tests/test_build_web.py
git commit -m "feat: add headline CPI (STATIC_TOTALCPICHANGE) with its own role

Spec 8 panel 4 calls for headline + core against the band, but only core
was configured. The inflation-control target is defined on total CPI, so
panel 4 needs headline to make its own claim.

New 'headline' role keeps it out of panel_target.core, which maps from
role=inflation."
```

---

### Task 3: Move the band to config and compute months-inside-band

**Why:** Spec §8 panel 4 requires a "months inside band" indicator. The band `{low: 1.0, high: 3.0}` is currently a magic literal in `build_web.py`; Task 5's metric needs the same two numbers, and duplicating them across modules invites drift. The band is a policy parameter — it belongs in `config/` alongside the series IDs.

The indicator counts **consecutive most-recent** headline observations inside the band. With headline at 3.2 the streak is **0**, which is exactly the honest, descriptive statement the spec wants — no prediction, just "the latest reading is outside the band."

**Files:**
- Modify: `config/settings.yml`
- Modify: `pipeline/models.py`
- Modify: `pipeline/metrics.py`
- Modify: `pipeline/build_web.py`
- Test: `tests/test_metrics.py`, `tests/test_build_web.py`

**Interfaces:**
- Consumes: `AppConfig.by_metric_key(key) -> SeriesConfig`; `run_metrics(con, config) -> dict`.
- Produces:
  - `InflationBand(BaseModel)` with `low: float`, `high: float`; `AppConfig.inflation_band: InflationBand` — **defaulted to `low=1.0, high=3.0`** so existing test fixtures that build `AppConfig(...)` without it keep working.
  - `compute_band_months(con, series_id: str, low: float, high: float) -> dict` returning `{"months_inside": int, "latest_date": str | None, "latest_value": float | None, "latest_inside": bool}`.
  - `run_metrics(...)` return dict gains key **`band_months`** holding that dict.
  - `panel_target.json` gains **`band_months`**; its `band` now comes from config. Task 9 consumes both.

- [ ] **Step 1: Write the failing metric tests**

Append to `tests/test_metrics.py`:

```python
from pipeline.metrics import compute_band_months

BAND_ROWS = [
    {"series_id": "CPI", "obs_date": "2026-02-01", "value": "1.8"},
    {"series_id": "CPI", "obs_date": "2026-03-01", "value": "2.4"},
    {"series_id": "CPI", "obs_date": "2026-04-01", "value": "2.8"},
    {"series_id": "CPI", "obs_date": "2026-05-01", "value": "3.2"},
]


def _band_cfg() -> AppConfig:
    return AppConfig(
        start_date="2000-01-01",
        series=[SeriesConfig(id="CPI", label_en="c", label_fr="c", frequency="monthly",
                            role="headline", metric_key="cpi_headline")],
        thresholds=Thresholds(staleness_days={"monthly": 95}, max_null_ratio=0.2, value_ranges={}),
    )


def test_band_months_zero_when_latest_is_outside():
    con = build_curated_con(BAND_ROWS, _band_cfg(), ingested_at="2026-07-14T00:00:00")
    assert compute_band_months(con, "CPI", 1.0, 3.0) == {
        "months_inside": 0,
        "latest_date": "2026-05-01",
        "latest_value": 3.2,
        "latest_inside": False,
    }


def test_band_months_counts_consecutive_recent_months_inside():
    con = build_curated_con(BAND_ROWS[:3], _band_cfg(), ingested_at="2026-07-14T00:00:00")
    result = compute_band_months(con, "CPI", 1.0, 3.0)
    assert result["months_inside"] == 3
    assert result["latest_inside"] is True


def test_band_months_streak_stops_at_first_breach():
    rows = [{"series_id": "CPI", "obs_date": "2026-01-01", "value": "5.0"}] + BAND_ROWS[:3]
    con = build_curated_con(rows, _band_cfg(), ingested_at="2026-07-14T00:00:00")
    # 5.0 in Jan breaches, so the streak counts only Feb-Apr, not back through it.
    assert compute_band_months(con, "CPI", 1.0, 3.0)["months_inside"] == 3


def test_band_months_handles_empty_series():
    con = build_curated_con([], _band_cfg(), ingested_at="2026-07-14T00:00:00")
    assert compute_band_months(con, "CPI", 1.0, 3.0) == {
        "months_inside": 0,
        "latest_date": None,
        "latest_value": None,
        "latest_inside": False,
    }
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_metrics.py -q -k band`
Expected: FAIL with `ImportError: cannot import name 'compute_band_months'`.

- [ ] **Step 3: Add the band to the config model**

In `pipeline/models.py`, add the model, the field, and wire it through `load_config`:

```python
class InflationBand(BaseModel):
    low: float
    high: float


class AppConfig(BaseModel):
    start_date: str
    series: list[SeriesConfig]
    thresholds: Thresholds
    inflation_band: InflationBand = InflationBand(low=1.0, high=3.0)

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
    )
```

Add to `config/settings.yml` (top level, after `start_date`):

```yaml
inflation_band: {low: 1.0, high: 3.0}
```

- [ ] **Step 4: Implement the metric**

In `pipeline/metrics.py`, add the function and register it in `run_metrics`:

```python
def compute_band_months(con: duckdb.DuckDBPyConnection, series_id: str, low: float, high: float) -> dict:
    rows = con.execute(
        "SELECT date::VARCHAR, value FROM fact_observation "
        "WHERE series_id = ? AND value IS NOT NULL ORDER BY date DESC",
        [series_id],
    ).fetchall()
    if not rows:
        return {"months_inside": 0, "latest_date": None, "latest_value": None, "latest_inside": False}
    streak = 0
    for _, value in rows:
        if low <= value <= high:
            streak += 1
        else:
            break
    latest_date, latest_value = rows[0]
    return {
        "months_inside": streak,
        "latest_date": latest_date,
        "latest_value": latest_value,
        "latest_inside": low <= latest_value <= high,
    }
```

Replace `run_metrics` so it also returns `band_months`:

```python
def run_metrics(con: duckdb.DuckDBPyConnection, config: AppConfig) -> dict:
    band = config.inflation_band
    return {
        "yield_slope": compute_yield_slope(
            con, config.by_metric_key("yield_2y").id, config.by_metric_key("yield_10y").id
        ),
        "household_spread": compute_household_spread(
            con, config.by_metric_key("mortgage_5y_fixed").id, config.by_metric_key("yield_5y").id
        ),
        "band_months": compute_band_months(
            con, config.by_metric_key("cpi_headline").id, band.low, band.high
        ),
    }
```

- [ ] **Step 5: Run the metric tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_metrics.py -q`
Expected: PASS.

> **Note:** `run_metrics` now resolves `cpi_headline`, so any `AppConfig` passed to it must include that series. `tests/test_build_web.py::_cfg()` already gained it in Task 2. `tests/test_metrics.py::_cfg()` does **not** call `run_metrics`, so it needs no change.

- [ ] **Step 6: Publish band + band_months from build_web**

In `pipeline/build_web.py`, replace the `panel_target.json` write:

```python
    paths.append(_write(out_dir, "panel_target.json", {
        "headline": [_series_block(con, s) for s in by_role.get("headline", [])],
        "core": [_series_block(con, s) for s in by_role.get("inflation", [])],
        "band": {"low": config.inflation_band.low, "high": config.inflation_band.high},
        "band_months": metrics["band_months"],
    }))
```

Extend the Task 2 test in `tests/test_build_web.py` — append these assertions to `test_panel_target_separates_headline_from_core`:

```python
    assert target["band_months"]["latest_value"] == 3.2
    assert target["band_months"]["latest_inside"] is False
    assert target["band_months"]["months_inside"] == 0
```

- [ ] **Step 7: Run the full suite and lint**

Run: `.venv\Scripts\python.exe -m pytest -q && .venv\Scripts\python.exe -m ruff check .`
Expected: PASS (30 tests), ruff clean.

- [ ] **Step 8: Commit**

```bash
git add config/settings.yml pipeline/models.py pipeline/metrics.py pipeline/build_web.py tests/test_metrics.py tests/test_build_web.py
git commit -m "feat: config-driven inflation band + months-inside-band metric

Spec 8 panel 4 needs a months-inside-band indicator. Lift the 1-3% band
out of build_web into config/settings.yml so metrics and build_web read
one definition instead of duplicating the literals."
```

---

### Task 4: Refresh live data so the dashboard has headline CPI to draw

**Why:** Tasks 2-3 changed what the pipeline emits, but `site/data/*.json` still holds the 2026-07-14 snapshot with no headline series. Every frontend task from here reads these files, so they must be real and current first. This is also the first live exercise of the config-driven design: a new series should flow end to end with no Python changes beyond the role mapping.

**Files:**
- Modify (generated): `data/raw/2026-07-15/*.json`, `data/curated/*.parquet`, `data/curated/data_quality.json`, `site/data/*.json`

**Interfaces:**
- Consumes: `python -m pipeline.run --run-date <YYYY-MM-DD> --ingested-at <ISO>`
- Produces: a committed snapshot including `STATIC_TOTALCPICHANGE`. Tasks 5-10 read these exact files.

- [ ] **Step 1: Run the pipeline live against Valet**

Run:

```bash
.venv/Scripts/python.exe -m pipeline.run --run-date 2026-07-15 --ingested-at 2026-07-15T00:00:00
```

Expected: `pipeline OK - overall quality: OK` and exit code 0. If it prints FAIL, **stop** — do not paper over it; diagnose which series and why before continuing.

- [ ] **Step 2: Verify headline CPI landed end to end**

Run:

```bash
.venv/Scripts/python.exe -c "
import json
t = json.load(open('site/data/panel_target.json', encoding='utf-8'))
print('headline series:', [s['id'] for s in t['headline']])
print('core series    :', [s['id'] for s in t['core']])
print('band           :', t['band'])
print('band_months    :', t['band_months'])
q = json.load(open('site/data/data_quality.json', encoding='utf-8'))
print('overall        :', q['overall'])
print('n series       :', len(q['series']))
"
```

Expected: headline is `['STATIC_TOTALCPICHANGE']`, core is the three CPI measures, `band` is `{'low': 1.0, 'high': 3.0}`, `band_months.latest_inside` is `False`, overall `OK`, and **10** series (9 previous + headline).

- [ ] **Step 3: Commit the snapshot**

```bash
git add data/raw data/curated site/data
git commit -m "data: refresh snapshot 2026-07-15 with headline CPI

First live run including STATIC_TOTALCPICHANGE. Adding a series took a
config line and a role mapping - no ingest/transform/quality changes."
```

---

### Task 5: Site shell — HTML, CSS, i18n, language toggle, vendored ECharts

**Why:** Everything downstream needs a page that boots, resolves a language, loads the manifest, and proves ECharts is wired — before any chart logic exists. This task renders no panels; it renders the frame and the "last refreshed" line, so a failure here is unambiguous.

**Files:**
- Create: `site/index.html`, `site/assets/css/app.css`, `site/assets/js/i18n.js`, `site/assets/js/data.js`, `site/assets/js/app.js`
- Create: `site/i18n/en.json`, `site/i18n/fr.json`
- Create (downloaded): `site/assets/vendor/echarts-6.1.0.min.js`

**Interfaces:**
- Consumes: `site/data/manifest.json` → `{as_of, last_refreshed, overall_quality, panels}`.
- Produces — Tasks 6-10 depend on these exact signatures:
  - `data.js`: `loadJSON(name: string) -> Promise<object>` (fetches `./data/<name>`)
  - `i18n.js`: `currentLang() -> "en" | "fr"`; `loadDict(lang) -> Promise<object>`; `t(dict, key) -> string` (returns `key` if missing); `applyStaticText(dict) -> void` (fills every `[data-i18n]` element)
  - `app.js`: exports nothing; boots on `DOMContentLoaded`.
  - Global `echarts` from the vendored script tag.

- [ ] **Step 1: Vendor ECharts 6.1.0**

Run:

```bash
mkdir -p site/assets/vendor site/assets/css site/assets/js site/i18n
curl -sSL "https://cdn.jsdelivr.net/npm/echarts@6.1.0/dist/echarts.min.js" -o site/assets/vendor/echarts-6.1.0.min.js
```

Verify it downloaded intact and kept its Apache-2.0 banner:

```bash
ls -l site/assets/vendor/echarts-6.1.0.min.js && head -c 300 site/assets/vendor/echarts-6.1.0.min.js
```

Expected: roughly 1 MB, and the first bytes contain the Apache License notice. If the file is under 100 KB the download failed — do not proceed.

- [ ] **Step 2: Write the i18n dictionaries**

`site/i18n/en.json`:

```json
{
  "app.title": "Monetary-Policy Transmission & Inflation Tracker",
  "app.subtitle": "How the Bank of Canada's policy rate travels through markets to households and prices.",
  "app.langSwitch": "Français",
  "app.lastRefreshed": "Last refreshed",
  "app.dataQuality": "Data quality",
  "app.loading": "Loading…",
  "app.error": "Could not load data. The page shows the last published snapshot.",
  "app.source": "Source: Bank of Canada Valet API",
  "app.terms": "Terms of use",
  "app.disclaimer": "For information only. This page describes published data. It is not financial advice, and it does not forecast interest rates or inflation."
}
```

`site/i18n/fr.json`:

```json
{
  "app.title": "Transmission de la politique monétaire et suivi de l'inflation",
  "app.subtitle": "Comment le taux directeur de la Banque du Canada se transmet aux marchés, aux ménages et aux prix.",
  "app.langSwitch": "English",
  "app.lastRefreshed": "Dernière mise à jour",
  "app.dataQuality": "Qualité des données",
  "app.loading": "Chargement…",
  "app.error": "Impossible de charger les données. La page affiche le dernier instantané publié.",
  "app.source": "Source : API Valet de la Banque du Canada",
  "app.terms": "Conditions d'utilisation",
  "app.disclaimer": "À titre informatif seulement. Cette page décrit des données publiées. Il ne s'agit pas de conseils financiers et elle ne prévoit ni les taux d'intérêt ni l'inflation."
}
```

- [ ] **Step 3: Write `site/assets/js/i18n.js`**

```js
const SUPPORTED = ["en", "fr"];

export function currentLang() {
  const raw = new URLSearchParams(window.location.search).get("lang");
  return SUPPORTED.includes(raw) ? raw : "en";
}

export function otherLang(lang) {
  return lang === "en" ? "fr" : "en";
}

export async function loadDict(lang) {
  const res = await fetch(`./i18n/${lang}.json`);
  if (!res.ok) throw new Error(`i18n ${lang}: ${res.status}`);
  return res.json();
}

export function t(dict, key) {
  return Object.prototype.hasOwnProperty.call(dict, key) ? dict[key] : key;
}

export function applyStaticText(dict) {
  for (const el of document.querySelectorAll("[data-i18n]")) {
    el.textContent = t(dict, el.dataset.i18n);
  }
}
```

- [ ] **Step 4: Write `site/assets/js/data.js`**

```js
export async function loadJSON(name) {
  const res = await fetch(`./data/${name}`);
  if (!res.ok) throw new Error(`${name}: ${res.status}`);
  return res.json();
}
```

- [ ] **Step 5: Write `site/index.html`**

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title data-i18n="app.title">Monetary-Policy Transmission &amp; Inflation Tracker</title>
  <link rel="stylesheet" href="./assets/css/app.css">
  <script src="./assets/vendor/echarts-6.1.0.min.js"></script>
</head>
<body>
  <header class="site-header">
    <div class="header-text">
      <h1 data-i18n="app.title">Monetary-Policy Transmission &amp; Inflation Tracker</h1>
      <p class="subtitle" data-i18n="app.subtitle"></p>
    </div>
    <a id="lang-switch" class="lang-switch" href="?lang=fr" data-i18n="app.langSwitch">Français</a>
  </header>

  <p id="status-bar" class="status-bar">
    <span data-i18n="app.lastRefreshed"></span>:
    <strong id="last-refreshed">—</strong>
    <span class="sep">·</span>
    <span data-i18n="app.dataQuality"></span>:
    <strong id="overall-quality" class="quality">—</strong>
  </p>

  <p id="load-error" class="load-error" hidden data-i18n="app.error"></p>

  <main id="panels"></main>

  <footer class="site-footer">
    <p class="disclaimer" data-i18n="app.disclaimer"></p>
    <p>
      <span data-i18n="app.source"></span> ·
      <a href="https://www.bankofcanada.ca/terms/" data-i18n="app.terms" rel="noopener">Terms of use</a>
    </p>
  </footer>

  <script type="module" src="./assets/js/app.js"></script>
</body>
</html>
```

- [ ] **Step 6: Write `site/assets/css/app.css`**

```css
:root {
  --bg: #ffffff;
  --fg: #1c1c1e;
  --muted: #5f6368;
  --line: #e2e4e8;
  --accent: #96172e; /* Bank of Canada red */
  --ok: #1f7a4d;
  --warn: #9a6700;
  --fail: #b3261e;
  --panel-radius: 10px;
}

* { box-sizing: border-box; }

body {
  margin: 0;
  padding: 1.5rem clamp(1rem, 4vw, 3rem) 3rem;
  background: var(--bg);
  color: var(--fg);
  font: 16px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
}

.site-header {
  display: flex;
  gap: 1rem;
  align-items: flex-start;
  justify-content: space-between;
  border-bottom: 3px solid var(--accent);
  padding-bottom: 1rem;
}

.site-header h1 { margin: 0 0 .25rem; font-size: clamp(1.25rem, 3vw, 1.75rem); }
.subtitle { margin: 0; color: var(--muted); max-width: 60ch; }

.lang-switch {
  flex: none;
  border: 1px solid var(--line);
  border-radius: 999px;
  padding: .35rem .9rem;
  color: var(--fg);
  text-decoration: none;
  font-size: .875rem;
}
.lang-switch:hover { border-color: var(--accent); color: var(--accent); }

.status-bar { color: var(--muted); font-size: .875rem; margin: 1rem 0 0; }
.status-bar .sep { margin: 0 .5rem; }
.quality[data-status="OK"] { color: var(--ok); }
.quality[data-status="WARN"] { color: var(--warn); }
.quality[data-status="FAIL"] { color: var(--fail); }

.load-error {
  border: 1px solid var(--fail);
  border-radius: var(--panel-radius);
  padding: .75rem 1rem;
  color: var(--fail);
}

.panel {
  border: 1px solid var(--line);
  border-radius: var(--panel-radius);
  padding: 1.25rem;
  margin-top: 1.5rem;
}
.panel h2 { margin: 0 0 .25rem; font-size: 1.125rem; }
.panel .panel-note { margin: 0 0 1rem; color: var(--muted); font-size: .875rem; max-width: 75ch; }
.chart { width: 100%; height: 340px; }

.readout { display: flex; flex-wrap: wrap; gap: 1.5rem; margin: 0 0 1rem; }
.readout div { display: flex; flex-direction: column; }
.readout dt, .readout .readout-label { color: var(--muted); font-size: .75rem; text-transform: uppercase; letter-spacing: .04em; }
.readout .readout-value { font-size: 1.5rem; font-weight: 600; font-variant-numeric: tabular-nums; }
.flag-inverted, .flag-outside { color: var(--fail); }
.flag-normal, .flag-inside { color: var(--ok); }

.site-footer { margin-top: 2.5rem; border-top: 1px solid var(--line); padding-top: 1rem; color: var(--muted); font-size: .8125rem; }
.disclaimer { max-width: 75ch; }

@media (max-width: 640px) {
  .site-header { flex-direction: column; }
  .chart { height: 280px; }
}
```

- [ ] **Step 7: Write `site/assets/js/app.js`**

```js
import { applyStaticText, currentLang, loadDict, otherLang } from "./i18n.js";
import { loadJSON } from "./data.js";

async function boot() {
  const lang = currentLang();
  document.documentElement.lang = lang;

  const dict = await loadDict(lang);
  applyStaticText(dict);

  const switcher = document.getElementById("lang-switch");
  switcher.href = `?lang=${otherLang(lang)}`;

  try {
    const manifest = await loadJSON("manifest.json");
    document.getElementById("last-refreshed").textContent = manifest.last_refreshed;
    const quality = document.getElementById("overall-quality");
    quality.textContent = manifest.overall_quality;
    quality.dataset.status = manifest.overall_quality;
  } catch (err) {
    console.error(err);
    document.getElementById("load-error").hidden = false;
  }
}

document.addEventListener("DOMContentLoaded", boot);
```

- [ ] **Step 8: Verify in a real browser**

Serve the site and drive it — do not just eyeball the file.

```bash
.venv/Scripts/python.exe -m http.server 8000 --directory site
```

With the server running, use the Playwright MCP tools:
1. `browser_navigate` → `http://localhost:8000/?lang=en`
2. `browser_console_messages` → **assert zero errors** (a 404 on ECharts or a module path shows up here)
3. `browser_snapshot` → assert the English title renders, "Last refreshed" shows `2026-07-15T00:00:00`, and data quality shows `OK` in green
4. `browser_navigate` → `http://localhost:8000/?lang=fr`
5. `browser_snapshot` → assert the title is French and the switch link now points to `?lang=en`
6. `browser_navigate` → `http://localhost:8000/?lang=xx` → assert it falls back to English

Also confirm ECharts is actually loaded, via `browser_evaluate`:

```js
() => typeof echarts !== "undefined" && echarts.version
```

Expected: a version string starting `6.1`.

Stop the server when done.

- [ ] **Step 9: Commit**

```bash
git add site/index.html site/assets site/i18n
git commit -m "feat: bilingual site shell with vendored ECharts 6.1.0

Boots, resolves ?lang=en|fr, renders the header, last-refreshed and data
quality from manifest.json. No panels yet.

Language via ?lang= rather than the /en /fr URL segments in spec 12 -
the site has no build step, so URL segments would mean duplicating the
HTML shell. Recorded in the spec decisions log."
```

---

### Task 6: Panel 1 — Policy & funding

**Why:** The first link in the transmission chain: the Bank sets the target rate, and CORRA is where overnight funding actually prints. A step chart is the honest form — the policy rate is a decision that holds flat between fixed announcement dates, not a continuous quantity.

**Files:**
- Create: `site/assets/js/charts.js`, `site/assets/js/panels/policy.js`
- Modify: `site/assets/js/app.js`, `site/i18n/en.json`, `site/i18n/fr.json`

**Interfaces:**
- Consumes: `site/data/panel_policy.json` → `{series: [{id, label_en, label_fr, role, points}]}`; `t(dict, key)`; `loadJSON(name)`.
- Produces — Tasks 7-9 depend on these:
  - `charts.js`: `seriesLabel(block, lang) -> string`; `baseOption({dict, yAxisName}) -> object`; `lineSeries(block, lang, opts?) -> object` where `opts` may set `step` and `lineStyle`; `mountChart(el, option) -> echarts.ECharts` (also wires a `resize` listener).
  - `panels/policy.js`: `renderPolicy(root, dict, lang) -> Promise<void>` (appends its own `<section class="panel">`).

- [ ] **Step 1: Write `site/assets/js/charts.js`**

```js
export function seriesLabel(block, lang) {
  return lang === "fr" ? block.label_fr : block.label_en;
}

export function baseOption({ yAxisName = "%" } = {}) {
  return {
    grid: { left: 52, right: 18, top: 28, bottom: 56 },
    tooltip: { trigger: "axis", axisPointer: { type: "line" } },
    legend: { top: 0, icon: "roundRect" },
    xAxis: { type: "time", axisLine: { lineStyle: { color: "#9aa0a6" } } },
    yAxis: {
      type: "value",
      name: yAxisName,
      scale: true,
      splitLine: { lineStyle: { color: "#eef0f3" } },
    },
    dataZoom: [
      { type: "inside" },
      { type: "slider", height: 20, bottom: 12 },
    ],
  };
}

export function lineSeries(block, lang, opts = {}) {
  return {
    name: seriesLabel(block, lang),
    type: "line",
    showSymbol: false,
    connectNulls: false, // nulls are holidays/gaps - show them, never bridge them
    data: block.points,
    ...opts,
  };
}

export function mountChart(el, option) {
  const chart = echarts.init(el);
  chart.setOption(option);
  window.addEventListener("resize", () => chart.resize());
  return chart;
}
```

- [ ] **Step 2: Add the panel copy to both dictionaries**

Add to `site/i18n/en.json`:

```json
  "panel.policy.title": "1 · Policy rate & overnight funding",
  "panel.policy.note": "The Bank sets the target for the overnight rate on eight fixed dates a year. CORRA is the rate at which overnight funding actually transacts, and it tracks the target closely.",
  "panel.policy.axis": "Rate (%)"
```

Add to `site/i18n/fr.json`:

```json
  "panel.policy.title": "1 · Taux directeur et financement à un jour",
  "panel.policy.note": "La Banque fixe la cible du taux du financement à un jour à huit dates préétablies par année. Le CORRA est le taux auquel le financement à un jour se négocie réellement, et il suit la cible de près.",
  "panel.policy.axis": "Taux (%)"
```

- [ ] **Step 3: Write `site/assets/js/panels/policy.js`**

```js
import { loadJSON } from "../data.js";
import { t } from "../i18n.js";
import { baseOption, lineSeries, mountChart } from "../charts.js";

export async function renderPolicy(root, dict, lang) {
  const data = await loadJSON("panel_policy.json");

  const section = document.createElement("section");
  section.className = "panel";
  section.innerHTML = `
    <h2>${t(dict, "panel.policy.title")}</h2>
    <p class="panel-note">${t(dict, "panel.policy.note")}</p>
    <div class="chart" id="chart-policy"></div>`;
  root.appendChild(section);

  const option = baseOption({ yAxisName: t(dict, "panel.policy.axis") });
  option.series = data.series.map((block) =>
    // step:'end' - the target holds flat until the next announcement changes it.
    lineSeries(block, lang, block.role === "policy" ? { step: "end", lineStyle: { width: 2.5 } } : {})
  );

  mountChart(section.querySelector("#chart-policy"), option);
}
```

- [ ] **Step 4: Mount it from `app.js`**

In `site/assets/js/app.js`, add the import and render call. Replace the `try` block:

```js
import { renderPolicy } from "./panels/policy.js";
```

```js
  try {
    const manifest = await loadJSON("manifest.json");
    document.getElementById("last-refreshed").textContent = manifest.last_refreshed;
    const quality = document.getElementById("overall-quality");
    quality.textContent = manifest.overall_quality;
    quality.dataset.status = manifest.overall_quality;

    const panels = document.getElementById("panels");
    await renderPolicy(panels, dict, lang);
  } catch (err) {
    console.error(err);
    failed = true;
  }
```

> **Set `failed = true` — do not set `load-error.hidden` directly here.** `boot()` ends with
> `load-error.hidden = !failed`, so a catch that only flips `hidden` gets silently undone by that
> final line and the banner never appears.

- [ ] **Step 5: Verify in a real browser**

Serve: `.venv/Scripts/python.exe -m http.server 8000 --directory site`

1. `browser_navigate` → `http://localhost:8000/?lang=en`
2. `browser_console_messages` → assert zero errors
3. `browser_take_screenshot` → assert two lines render: a **stepped** policy rate and a CORRA line that hugs it; legend shows both English labels
4. `browser_navigate` → `http://localhost:8000/?lang=fr` → screenshot; assert the legend and note are French
5. `browser_evaluate` → confirm the policy series is genuinely a step chart:

```js
() => echarts.getInstanceByDom(document.getElementById("chart-policy")).getOption().series.map(s => [s.name, s.step])
```

Expected: the policy series reports `"end"`; CORRA reports `undefined`.

- [ ] **Step 6: Commit**

```bash
git add site/assets/js/charts.js site/assets/js/panels/policy.js site/assets/js/app.js site/i18n
git commit -m "feat: panel 1 - policy rate (step) vs CORRA"
```

---

### Task 7: Panel 2 — To markets (yields, 2s10s slope, inversion flag)

**Why:** The second link: the policy rate anchors the short end, and the curve prices expectations further out. The 2s10s slope and its inversion flag are already computed by `compute_yield_slope` — this panel surfaces them **descriptively**. An inverted curve is reported as an observed fact, never as a recession call (spec §2 bright line).

**Files:**
- Create: `site/assets/js/panels/markets.js`
- Modify: `site/assets/js/app.js`, `site/i18n/en.json`, `site/i18n/fr.json`

**Interfaces:**
- Consumes: `site/data/panel_markets.json` → `{yields: [block], policy: [block], yield_slope: [{date, slope, inverted}]}`; `baseOption`, `lineSeries`, `mountChart`, `seriesLabel`, `t`, `loadJSON`.
- Produces: `renderMarkets(root, dict, lang) -> Promise<void>`.

- [ ] **Step 1: Add the panel copy to both dictionaries**

Add to `site/i18n/en.json`:

```json
  "panel.markets.title": "2 · To markets — benchmark GoC yields",
  "panel.markets.note": "The policy rate anchors the short end of the curve. Longer yields also reflect expectations. The 2s10s slope is the 10-year yield minus the 2-year yield; when it is negative the curve is inverted.",
  "panel.markets.axis": "Yield (%)",
  "panel.markets.slopeLabel": "2s10s slope (latest)",
  "panel.markets.curveLabel": "Curve shape",
  "panel.markets.inverted": "Inverted",
  "panel.markets.normal": "Not inverted"
```

Add to `site/i18n/fr.json`:

```json
  "panel.markets.title": "2 · Vers les marchés — rendements de référence GdC",
  "panel.markets.note": "Le taux directeur ancre la partie courte de la courbe. Les rendements à plus long terme reflètent aussi les attentes. L'écart 2 ans-10 ans correspond au rendement à 10 ans moins celui à 2 ans; lorsqu'il est négatif, la courbe est inversée.",
  "panel.markets.axis": "Rendement (%)",
  "panel.markets.slopeLabel": "Écart 2 ans-10 ans (dernier)",
  "panel.markets.curveLabel": "Forme de la courbe",
  "panel.markets.inverted": "Inversée",
  "panel.markets.normal": "Non inversée"
```

- [ ] **Step 2: Write `site/assets/js/panels/markets.js`**

```js
import { loadJSON } from "../data.js";
import { t } from "../i18n.js";
import { baseOption, lineSeries, mountChart } from "../charts.js";

export async function renderMarkets(root, dict, lang) {
  const data = await loadJSON("panel_markets.json");
  const latest = data.yield_slope.length ? data.yield_slope[data.yield_slope.length - 1] : null;

  const inverted = Boolean(latest && latest.inverted);
  const shapeKey = inverted ? "panel.markets.inverted" : "panel.markets.normal";
  const shapeClass = inverted ? "flag-inverted" : "flag-normal";
  const slopeText = latest ? `${latest.slope > 0 ? "+" : ""}${latest.slope.toFixed(2)}` : "—";

  const section = document.createElement("section");
  section.className = "panel";
  section.innerHTML = `
    <h2>${t(dict, "panel.markets.title")}</h2>
    <p class="panel-note">${t(dict, "panel.markets.note")}</p>
    <div class="readout">
      <div>
        <span class="readout-label">${t(dict, "panel.markets.slopeLabel")}</span>
        <span class="readout-value">${slopeText}</span>
      </div>
      <div>
        <span class="readout-label">${t(dict, "panel.markets.curveLabel")}</span>
        <span class="readout-value ${shapeClass}">${t(dict, shapeKey)}</span>
      </div>
    </div>
    <div class="chart" id="chart-markets"></div>`;
  root.appendChild(section);

  const option = baseOption({ yAxisName: t(dict, "panel.markets.axis") });
  option.series = [
    ...data.policy.map((block) =>
      lineSeries(block, lang, { step: "end", lineStyle: { width: 2.5, type: "dashed" } })
    ),
    ...data.yields.map((block) => lineSeries(block, lang)),
  ];

  mountChart(section.querySelector("#chart-markets"), option);
}
```

- [ ] **Step 3: Mount it from `app.js`**

Add the import and the call after `renderPolicy`:

```js
import { renderMarkets } from "./panels/markets.js";
```

```js
    await renderPolicy(panels, dict, lang);
    await renderMarkets(panels, dict, lang);
```

- [ ] **Step 4: Verify in a real browser**

Serve, then:
1. `browser_navigate` → `http://localhost:8000/?lang=en`; `browser_console_messages` → zero errors
2. `browser_take_screenshot` → assert four lines (dashed policy + 2y/5y/10y) and the two readouts
3. Cross-check the readout against the published data — it must not be recomputed in the UI:

```bash
.venv/Scripts/python.exe -c "
import json
d = json.load(open('site/data/panel_markets.json', encoding='utf-8'))
last = d['yield_slope'][-1]
print('latest slope:', last)
"
```

Assert the on-page slope equals that `slope` rounded to 2 dp and that the flag matches `inverted`. As of the 2026-07-15 snapshot the slope is positive (~+0.68), so expect **"Not inverted"** in green.

4. `browser_navigate` → `?lang=fr` → assert readouts read "Non inversée"

- [ ] **Step 5: Commit**

```bash
git add site/assets/js/panels/markets.js site/assets/js/app.js site/i18n
git commit -m "feat: panel 2 - GoC yields vs policy, 2s10s slope + inversion flag"
```

---

### Task 8: Panel 3 — To households (lending rate vs 5-year yield, observed spread)

**Why:** The third link: bank funding costs track the 5-year yield, and the mortgage rate sits above it. **This is the panel most likely to breach a bright line.** The spread is a *description* of what was observed, never a prediction of what a rate "should" be, and `V122667780` is an **actual** insured effective rate — the note must not let a reader take it as a quotable consumer rate.

**Files:**
- Create: `site/assets/js/panels/households.js`
- Modify: `site/assets/js/app.js`, `site/i18n/en.json`, `site/i18n/fr.json`

**Interfaces:**
- Consumes: `site/data/panel_households.json` → `{lending: [block], yield5: [block], spread: [{date, spread}]}`.
- Produces: `renderHouseholds(root, dict, lang) -> Promise<void>`.

- [ ] **Step 1: Add the panel copy to both dictionaries**

Add to `site/i18n/en.json`:

```json
  "panel.households.title": "3 · To households — lending rates",
  "panel.households.note": "Banks fund 5-year fixed mortgages largely off the 5-year Government of Canada yield, so the lending rate tends to sit above it. The gap shown is the observed spread between the two published series — a description of what happened, not a prediction and not a rate you can be quoted.",
  "panel.households.axis": "Rate (%)",
  "panel.households.spreadLabel": "Observed spread (latest)",
  "panel.households.spreadSeries": "Observed spread (mortgage − 5-year yield)"
```

Add to `site/i18n/fr.json`:

```json
  "panel.households.title": "3 · Vers les ménages — taux des prêts",
  "panel.households.note": "Les banques financent les prêts hypothécaires fixes de 5 ans en grande partie à partir du rendement des obligations du gouvernement du Canada à 5 ans; le taux des prêts se situe donc généralement au-dessus. L'écart présenté est l'écart observé entre les deux séries publiées — une description de ce qui s'est produit, et non une prévision ni un taux qui pourrait vous être offert.",
  "panel.households.axis": "Taux (%)",
  "panel.households.spreadLabel": "Écart observé (dernier)",
  "panel.households.spreadSeries": "Écart observé (hypothèque − rendement 5 ans)"
```

- [ ] **Step 2: Write `site/assets/js/panels/households.js`**

```js
import { loadJSON } from "../data.js";
import { t } from "../i18n.js";
import { baseOption, lineSeries, mountChart } from "../charts.js";

export async function renderHouseholds(root, dict, lang) {
  const data = await loadJSON("panel_households.json");
  const latest = data.spread.length ? data.spread[data.spread.length - 1] : null;
  const spreadText = latest ? `${latest.spread.toFixed(2)}` : "—";

  const section = document.createElement("section");
  section.className = "panel";
  section.innerHTML = `
    <h2>${t(dict, "panel.households.title")}</h2>
    <p class="panel-note">${t(dict, "panel.households.note")}</p>
    <div class="readout">
      <div>
        <span class="readout-label">${t(dict, "panel.households.spreadLabel")}</span>
        <span class="readout-value">${spreadText}</span>
      </div>
    </div>
    <div class="chart" id="chart-households"></div>`;
  root.appendChild(section);

  const option = baseOption({ yAxisName: t(dict, "panel.households.axis") });
  option.series = [
    ...data.lending.map((block) => lineSeries(block, lang, { lineStyle: { width: 2.5 } })),
    ...data.yield5.map((block) => lineSeries(block, lang)),
    {
      name: t(dict, "panel.households.spreadSeries"),
      type: "line",
      showSymbol: false,
      connectNulls: false,
      lineStyle: { type: "dotted" },
      areaStyle: { opacity: 0.08 },
      data: data.spread.map((p) => [p.date, p.spread]),
    },
  ];

  mountChart(section.querySelector("#chart-households"), option);
}
```

- [ ] **Step 3: Mount it from `app.js`**

```js
import { renderHouseholds } from "./panels/households.js";
```

```js
    await renderMarkets(panels, dict, lang);
    await renderHouseholds(panels, dict, lang);
```

- [ ] **Step 4: Verify in a real browser**

Serve, then:
1. `browser_navigate` → `?lang=en`; `browser_console_messages` → zero errors
2. `browser_take_screenshot` → assert the mortgage line sits above the 5-year yield with a dotted spread series below
3. Cross-check the readout against published data:

```bash
.venv/Scripts/python.exe -c "
import json
d = json.load(open('site/data/panel_households.json', encoding='utf-8'))
print('latest spread:', d['spread'][-1])
"
```

Assert the on-page value matches (~0.79 in the 2026-07-15 snapshot).

4. **Bright-line check:** read the rendered note in both languages. It must contain no advice, no forecast, and no implication the rate is obtainable. If it reads as a recommendation, rewrite it before committing.

- [ ] **Step 5: Commit**

```bash
git add site/assets/js/panels/households.js site/assets/js/app.js site/i18n
git commit -m "feat: panel 3 - mortgage rate vs 5y yield with observed spread"
```

---

### Task 9: Panel 4 — The target (headline + core vs the 1–3% band)

**Why:** The payoff panel, and the reason Tasks 2-3 exist. The band is drawn with `markArea` bounded by `yAxis` values from `panel_target.band`, so it tracks config rather than a hardcoded literal. The months-inside-band readout comes from `band_months` — computed in SQL, not recomputed in JS, so the page and the pipeline can never disagree.

**Files:**
- Create: `site/assets/js/panels/target.js`
- Modify: `site/assets/js/app.js`, `site/i18n/en.json`, `site/i18n/fr.json`

**Interfaces:**
- Consumes: `site/data/panel_target.json` → `{headline: [block], core: [block], band: {low, high}, band_months: {months_inside, latest_date, latest_value, latest_inside}}`.
- Produces: `renderTarget(root, dict, lang) -> Promise<void>`.

- [ ] **Step 1: Add the panel copy to both dictionaries**

Add to `site/i18n/en.json`:

```json
  "panel.target.title": "4 · The target — CPI vs the 1–3% control range",
  "panel.target.note": "The Bank's inflation-control target is defined on total CPI, with a 1–3% control range shown shaded. Core measures (trim, median, common) strip out volatile components to show the underlying trend.",
  "panel.target.axis": "Year-over-year change (%)",
  "panel.target.bandName": "1–3% control range",
  "panel.target.latestLabel": "Total CPI (latest)",
  "panel.target.streakLabel": "Consecutive months inside the range",
  "panel.target.statusLabel": "Latest reading",
  "panel.target.inside": "Inside the range",
  "panel.target.outside": "Outside the range"
```

Add to `site/i18n/fr.json`:

```json
  "panel.target.title": "4 · La cible — IPC par rapport à la fourchette de 1 à 3 %",
  "panel.target.note": "La cible de maîtrise de l'inflation de la Banque est définie en fonction de l'IPC global, avec une fourchette de maîtrise de 1 à 3 % indiquée en ombré. Les mesures fondamentales (tronquée, médiane, commune) excluent les composantes volatiles afin de faire ressortir la tendance sous-jacente.",
  "panel.target.axis": "Variation sur douze mois (%)",
  "panel.target.bandName": "Fourchette de maîtrise de 1 à 3 %",
  "panel.target.latestLabel": "IPC global (dernier)",
  "panel.target.streakLabel": "Mois consécutifs à l'intérieur de la fourchette",
  "panel.target.statusLabel": "Dernière lecture",
  "panel.target.inside": "À l'intérieur de la fourchette",
  "panel.target.outside": "À l'extérieur de la fourchette"
```

- [ ] **Step 2: Write `site/assets/js/panels/target.js`**

```js
import { loadJSON } from "../data.js";
import { t } from "../i18n.js";
import { baseOption, lineSeries, mountChart } from "../charts.js";

export async function renderTarget(root, dict, lang) {
  const data = await loadJSON("panel_target.json");
  const band = data.band;
  const bm = data.band_months;

  const inside = Boolean(bm.latest_inside);
  const statusKey = inside ? "panel.target.inside" : "panel.target.outside";
  const statusClass = inside ? "flag-inside" : "flag-outside";
  const latestText = bm.latest_value === null ? "—" : `${bm.latest_value.toFixed(1)}%`;

  const section = document.createElement("section");
  section.className = "panel";
  section.innerHTML = `
    <h2>${t(dict, "panel.target.title")}</h2>
    <p class="panel-note">${t(dict, "panel.target.note")}</p>
    <div class="readout">
      <div>
        <span class="readout-label">${t(dict, "panel.target.latestLabel")}</span>
        <span class="readout-value">${latestText}</span>
      </div>
      <div>
        <span class="readout-label">${t(dict, "panel.target.statusLabel")}</span>
        <span class="readout-value ${statusClass}">${t(dict, statusKey)}</span>
      </div>
      <div>
        <span class="readout-label">${t(dict, "panel.target.streakLabel")}</span>
        <span class="readout-value">${bm.months_inside}</span>
      </div>
    </div>
    <div class="chart" id="chart-target"></div>`;
  root.appendChild(section);

  const option = baseOption({ yAxisName: t(dict, "panel.target.axis") });
  const headlineSeries = data.headline.map((block) =>
    lineSeries(block, lang, {
      lineStyle: { width: 3 },
      // The shaded 1-3% control range rides on the headline series, since the
      // target is defined on total CPI. Bounds come from config, not literals.
      markArea: {
        silent: true,
        itemStyle: { color: "rgba(150, 23, 46, 0.07)" },
        label: { show: true, position: "insideTopLeft", color: "#8a8f98", fontSize: 11 },
        data: [[{ name: t(dict, "panel.target.bandName"), yAxis: band.low }, { yAxis: band.high }]],
      },
    })
  );
  const coreSeries = data.core.map((block) =>
    lineSeries(block, lang, { lineStyle: { width: 1.25, opacity: 0.85 } })
  );
  option.series = [...headlineSeries, ...coreSeries];

  mountChart(section.querySelector("#chart-target"), option);
}
```

- [ ] **Step 3: Mount it from `app.js`**

```js
import { renderTarget } from "./panels/target.js";
```

```js
    await renderHouseholds(panels, dict, lang);
    await renderTarget(panels, dict, lang);
```

- [ ] **Step 4: Verify in a real browser**

Serve, then:
1. `browser_navigate` → `?lang=en`; `browser_console_messages` → zero errors
2. `browser_take_screenshot` → assert a shaded horizontal band spans 1% to 3% across the full width, with a thick headline line and three thinner core lines
3. Assert the readouts show total CPI **3.2%**, **"Outside the range"** in red, and **0** consecutive months
4. Confirm the band is config-driven, not hardcoded:

```js
() => echarts.getInstanceByDom(document.getElementById("chart-target")).getOption().series[0].markArea.data
```

Expected: `yAxis` bounds of `1` and `3`.

5. `browser_navigate` → `?lang=fr` → assert "À l'extérieur de la fourchette"

- [ ] **Step 5: Commit**

```bash
git add site/assets/js/panels/target.js site/assets/js/app.js site/i18n
git commit -m "feat: panel 4 - headline + core CPI vs the shaded 1-3% band"
```

---

### Task 10: Resilience, responsiveness, and a full bilingual pass

**Why:** The panels each assume their fetch succeeds and their arrays are non-empty. A reviewer opening this on a phone, or a snapshot where a series went empty, must still get a page rather than a blank screen. Spec §10 requires never publishing an empty page.

**Files:**
- Modify: `site/assets/js/app.js`, `site/assets/js/panels/*.js`, `site/assets/css/app.css`

**Interfaces:**
- Consumes: everything above.
- Produces: no new exports. `app.js` renders panels independently so one failure cannot blank the rest.

- [ ] **Step 1: Make panel failures independent**

Replace the render sequence in `site/assets/js/app.js` so a single bad panel does not abort the others:

```js
import { applyStaticText, currentLang, loadDict, otherLang } from "./i18n.js";
import { loadJSON } from "./data.js";
import { renderPolicy } from "./panels/policy.js";
import { renderMarkets } from "./panels/markets.js";
import { renderHouseholds } from "./panels/households.js";
import { renderTarget } from "./panels/target.js";

const PANELS = [renderPolicy, renderMarkets, renderHouseholds, renderTarget];

async function boot() {
  const lang = currentLang();
  document.documentElement.lang = lang;

  let failed = false;

  // Guarded: if the dictionary fails to load we keep the HTML fallback copy
  // rather than blanking the page. The disclaimer is a spec §2 bright line and
  // must survive a failed fetch.
  let dict = {};
  try {
    dict = await loadDict(lang);
    applyStaticText(dict);
  } catch (err) {
    console.error("i18n", err);
    failed = true;
  }
  document.getElementById("lang-switch").href = `?lang=${otherLang(lang)}`;

  try {
    const manifest = await loadJSON("manifest.json");
    document.getElementById("last-refreshed").textContent = manifest.last_refreshed;
    const quality = document.getElementById("overall-quality");
    quality.textContent = manifest.overall_quality;
    quality.dataset.status = manifest.overall_quality;
  } catch (err) {
    console.error("manifest", err);
    failed = true;
  }

  const root = document.getElementById("panels");
  for (const render of PANELS) {
    try {
      await render(root, dict, lang);
    } catch (err) {
      console.error(render.name, err);
      failed = true;
    }
  }

  document.getElementById("load-error").hidden = !failed;
}

document.addEventListener("DOMContentLoaded", boot);
```

- [ ] **Step 2: Guard the empty-series case**

Each panel indexes `data.<key>[...]`. `markets.js` and `households.js` already guard with `.length ? ... : null`. Add the same guard to `target.js` — replace the `bm` destructure at the top of `renderTarget`:

```js
  const bm = data.band_months ?? {
    months_inside: 0, latest_date: null, latest_value: null, latest_inside: false,
  };
```

- [ ] **Step 3: Verify degraded rendering**

Temporarily break one panel's data file and confirm the others survive:

```bash
mv site/data/panel_markets.json site/data/panel_markets.json.bak
echo '{ broken' > site/data/panel_markets.json
```

Serve, `browser_navigate` → `?lang=en`, then:
- assert panels 1, 3 and 4 still render
- assert the error banner is visible
- assert the console logs the failure

Restore immediately:

```bash
mv site/data/panel_markets.json.bak site/data/panel_markets.json
```

Reload and assert the error banner is gone and all four panels render.

- [ ] **Step 4: Verify responsive layout**

With the server running:
1. `browser_resize` → 375 × 812 → `browser_take_screenshot`; assert no horizontal scroll, charts shrink to 280px, header stacks
2. `browser_resize` → 1440 × 900 → `browser_take_screenshot`; assert charts fill the width

- [ ] **Step 5: Full bilingual sweep**

`browser_navigate` → `?lang=fr` and read the whole page. Assert **no English leaks** — every heading, note, readout, legend label and footer string is French. Any string rendering as a raw key (e.g. `panel.target.inside`) means a missing dictionary entry; fix it.

Include the **browser tab title** — it is the easiest thing to miss because it is not on the page. Check it explicitly:

```js
() => document.title
```

Expected under `?lang=fr`: the French title, not the English one.

Confirm the disclaimer and the BoC terms link are visible in both languages.

- [ ] **Step 6: Run the full suite and lint**

Run: `.venv\Scripts\python.exe -m pytest -q && .venv\Scripts\python.exe -m ruff check .`
Expected: PASS (30 tests), ruff clean.

- [ ] **Step 7: Commit**

```bash
git add site/assets
git commit -m "feat: independent panel failures, empty-series guards, responsive pass

One bad panel data file no longer blanks the page - spec 10 requires
never publishing an empty page."
```

---

## Done when

- All four panels render from committed JSON, in both languages, with zero console errors.
- The pipeline is green at future as-of dates (Task 1) and publishes headline CPI (Tasks 2-4).
- `pytest -q` green (30 tests) and `ruff check .` clean.
- No hardcoded user-facing copy; no browser calls to Valet; disclaimer and BoC attribution visible.

## Deferred to Plan 3 (spec milestone M4)

- Data-Trust tab rendering `data_quality.json`; methodology page with Mermaid lineage; revision-diff quality check; `ci.yml` + `refresh.yml`; README with CI badge; GitHub Pages deploy.
- **Payload size:** `panel_markets.json` is ~886 KB uncompressed (full daily history since 2000). GitHub Pages serves gzip, which should bring it to roughly 150 KB over the wire. Deliberately not optimised now (YAGNI, spec §14 "over-investing in frontend"). **Measure it once Pages is live in Plan 3**; if the transfer is poor, downsample the long view or split per-series files then.
- **Pages vs private repo:** publishing Pages from a private repo needs a paid plan; on a free account the repo must be public. Decide before the deploy step.

## Docs to update when this plan lands

Per the house rule, in the same change as the code:

- `docs/superpowers/specs/2026-07-14-inflation-tracker-design.md` — §12 i18n (`?lang=` supersedes `/en`,`/fr`); §7/§8 (headline CPI added); §15 decisions log.
- `CLAUDE.md` — series table gains `STATIC_TOTALCPICHANGE`; status → Plan 2 of 3.
- **Notion** — progress entry, the plan split (2 of 3), and the staleness-threshold fix.
