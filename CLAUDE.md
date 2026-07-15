# CLAUDE.md — Inflation Tracker (BoC Monetary-Policy Dashboard)

> **House rule (read first):** The **Notion page is the single source of truth.** Keep it current as
> work lands — status, decisions, architecture, progress log. Update Notion in the *same change* as
> the code/docs. Canonical design prose lives in `docs/superpowers/specs/`; Notion mirrors + tracks it.

**Notion (source of truth):** Inflation Tracker — BoC Monetary-Policy Dashboard
https://app.notion.com/p/39dcea51fedf81028e24e6f748c1482b
(Projects DB · Stage: Planning · Lead: said-rustom)

**Status:** Plan 1 of 2 (data pipeline) **complete and merged to `main`** (2026-07-15) — ingest →
transform → metrics → quality → build_web all green (22 tests, ruff clean) with a live BoC snapshot
published to `site/data/`. **Next:** Plan 2 — static dashboard, Data-Trust + methodology pages,
revision-diff check, CI workflows, GitHub Pages deploy. No git remote configured yet.
**Owner:** said-rustom · Solo · Portfolio piece for a Bank of Canada Developer (Data Operations) application.

## What this is
A free, public web dashboard on the **Bank of Canada Valet API** visualizing the **monetary-policy
transmission chain**: policy rate → CORRA → benchmark GoC bond yields → chartered-bank lending rates
→ CPI vs the 1–3% inflation-control target. Built as an **end-to-end data product** (ingestion →
transform → data-quality → visualization), because the target role is data-engineering-first.

## Verified BoC Valet series (as implemented in `config/series.yml`)
| Purpose | Series | Frequency | `metric_key` |
|---|---|---|---|
| Policy rate (target overnight) | `V39079` (2.25% on 2026-07-13) | Daily (8 fixed dates) | — |
| Overnight funding | `AVG.INTWO` (CORRA) | Daily | — |
| Benchmark GoC yields | `BD.CDN.2YR.DQ.YLD`, `BD.CDN.5YR.DQ.YLD`, `BD.CDN.10YR.DQ.YLD` | Daily | `yield_2y/5y/10y` |
| Chartered-bank lending rate | `V122667780` (insured 5yr+ fixed mortgage) | Monthly | `mortgage_5y_fixed` |
| Core inflation vs target | `CPI_TRIM`, `CPI_MEDIAN`, `CPI_COMMON` | Monthly | — |

The design brainstorm named the `bond_yields_benchmark` group and the `A4_RATES_*` tables; the built
pipeline resolves those to the individual series above (ingest fetches one file per series ID).

Base URL: `https://www.bankofcanada.ca/valet/` · no auth · JSON/CSV/XML · `?recent=N` / date-range params.
Series IDs belong in **config**, not code. A series can disappear — treat staleness as a real risk.

## Doc map
- **Notion page** — source of truth / tracker (link above).
- `docs/superpowers/specs/2026-07-14-inflation-tracker-design.md` — approved design record.
- `docs/superpowers/plans/2026-07-14-inflation-tracker-pipeline.md` — Plan 1 of 2 (pipeline). Done.

## Working on this repo
- Env: Python 3.12 in `.venv`. **Create it with stdlib `venv`, not `uv venv`** — uv's launcher stub
  gets blocked on this machine ("Access is denied"); a stdlib venv copies a real `python.exe` and works.
  Install deps with `uv pip install --python .venv\Scripts\python.exe -e ".[dev]"`.
- Test + lint: `.venv\Scripts\python.exe -m pytest -q` and `... -m ruff check .`
- Refresh data: `python -m pipeline.run --run-date <YYYY-MM-DD> --ingested-at <ISO>` (add `--offline`
  to rebuild from cached raw without hitting Valet).
