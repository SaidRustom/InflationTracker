# CLAUDE.md — Inflation Tracker (BoC Monetary-Policy Dashboard)

> **House rule (read first):** The **Notion page is the single source of truth.** Keep it current as
> work lands — status, decisions, architecture, progress log. Update Notion in the *same change* as
> the code/docs. Canonical design prose lives in `docs/superpowers/specs/`; Notion mirrors + tracks it.

**Notion (source of truth):** Inflation Tracker — BoC Monetary-Policy Dashboard
https://app.notion.com/p/39dcea51fedf81028e24e6f748c1482b
(Projects DB · Stage: Planning · Lead: said-rustom)

**Status:** Plans **1 and 2 of 3 complete and merged to `main`** (2026-07-15). Plan 1 = pipeline;
Plan 2 = the bilingual ECharts dashboard (M3) — four panels rendering the transmission chain from
committed JSON, EN/FR via `?lang=`, **30 tests, ruff clean**. The **Pages deploy landed early**
(2026-07-16, ahead of Plan 3 — see *Live* below). **Next: Plan 3 (M4)** — Data-Trust tab,
methodology page, revision-diff check, `ci.yml` + `refresh.yml`, README.
**Owner:** said-rustom · Solo · Portfolio piece for a Bank of Canada Developer (Data Operations) application.

**Remote:** `origin` → https://github.com/SaidRustom/InflationTracker (**public** since 2026-07-16,
default branch `main`).

**Live:** https://saidrustom.github.io/InflationTracker/ — deployed by `.github/workflows/pages.yml`
on push to `main` touching `site/**`. The repo went public to make Pages free (Pages from a private
repo needs a paid plan); this closes the open question Plan 2 left, and the design called for a
public dashboard anyway. Pages source is `build_type: workflow` — it uploads `site/` as an artifact
rather than serving a branch, because the branch-based source can only serve `/` or `/docs`.
Everything in `site/` is referenced **relatively** (`./assets/…`, `./data/…`), which is what lets it
work under the `/InflationTracker/` subpath — keep it that way.

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
| Headline inflation vs target | `STATIC_TOTALCPICHANGE` (3.2% on 2026-05-01) | Monthly | `cpi_headline` |

The design brainstorm named the `bond_yields_benchmark` group and the `A4_RATES_*` tables; the built
pipeline resolves those to the individual series above (ingest fetches one file per series ID).

Base URL: `https://www.bankofcanada.ca/valet/` · no auth · JSON/CSV/XML · `?recent=N` / date-range params.
Series IDs belong in **config**, not code. A series can disappear — treat staleness as a real risk.

## Doc map
- **Notion page** — source of truth / tracker (link above).
- `docs/superpowers/specs/2026-07-14-inflation-tracker-design.md` — approved design record (see its
  decisions log for the 2026-07-15 amendments: `?lang=` i18n, headline CPI, plan split, staleness fix).
- `docs/superpowers/specs/2026-07-16-revision-diff-design.md` — approved design for the **revision-diff**,
  Plan 3a's headline feature (**built and merged**). Amends §9/§12. Key rule: revisions are detected by
  diffing **retained raw vintages re-parsed with today's parser** — never the curated parquet or published
  JSON, because those compare old code's output to new code's output and would attribute our own commits
  to the Bank. See its **§4.1**: re-parsing does *not* cancel a change to the **fetch window**
  (`start_date`, `recent`) — that is closed separately by `_meta.json` per vintage + skip-on-mismatch.
- `docs/superpowers/specs/2026-07-17-plan-3b-design.md` — approved design for **Plan 3b** (**built and
  merged**): accessibility remediation + `fr-CA` formatting. Key rules: the chart `aria-label` is composed
  from **published values only** (a derived claim there could contradict the visual readouts); **dates are
  already correct in both languages** (en-CA and fr-CA both render ISO); ECharts' built-in `aria` is
  **rejected on measured evidence**; and we claim only the five tested success criteria, never blanket
  "WCAG 2.1 AA".
- `docs/superpowers/specs/2026-07-17-plan-3c-design.md` — approved design for **Plan 3c**: the **Data &
  Methods page** (renders `revisions.json`'s three states + `data_quality.json` + methodology/honesty
  prose) + a **published bilingual accessibility statement** + the full WCAG audit. Key rules: **separate
  static HTML pages** with a shared shell kept in sync by a byte-identical **parity test** (no router, no
  ARIA tabs); the revision block **branches on `status` first**, never on the count (never_checked ≠ "no
  revisions"); quality status is **never colour alone** (text + symbol); and the statement claims
  **"self-assessed against WCAG 2.1 AA", never "certified"**.
- `docs/superpowers/plans/2026-07-14-inflation-tracker-pipeline.md` — Plan 1 of 3 (pipeline). Done.
- `docs/superpowers/plans/2026-07-15-inflation-tracker-dashboard.md` — Plan 2 of 3 (M3 dashboard). Done.
  Its "Deferred to Plan 3" section is the input to the next plan.

## The site (`site/`, built by Plan 2)
No build step, no framework, no npm. `python -m http.server 8000 --directory site` to run it locally.
- Language via **`?lang=en|fr`** (default `en`, unknown falls back). *Amends spec §12's `/en` `/fr`.*
- Every user-facing string lives in `site/i18n/{en,fr}.json`. English text inside a `[data-i18n]`
  element is a permitted pre-boot/no-JS fallback — never a string's only source. `<title>` included.
- The page **never calls Valet**; it reads only committed `site/data/*.json`.
- ECharts **6.1.0 vendored** at `site/assets/vendor/` (Apache-2.0, keep the banner).
- Readouts (2s10s slope, spread, months-in-band) are **read from the published JSON, never recomputed
  in JS** — that is what keeps the page and the pipeline from disagreeing.
- **No JS test runner, deliberately** (spec §14: don't over-invest in the frontend). Frontend changes
  are verified by driving a real browser. Two cautions learned the hard way: the browser's disk cache
  will happily serve a 200 for a file you just renamed (use a route interceptor to force a real
  failure), and synthetic wheel events are untrusted in Chromium, so they never scroll the page.

## Working on this repo
- Env: Python 3.12 in `.venv`. **Create it with stdlib `venv`, not `uv venv`** — uv's launcher stub
  gets blocked on this machine ("Access is denied"); a stdlib venv copies a real `python.exe` and works.
  Install deps with `uv pip install --python .venv\Scripts\python.exe -e ".[dev]"`.
- Test + lint: `.venv\Scripts\python.exe -m pytest -q` and `... -m ruff check .`
- Refresh data: `python -m pipeline.run --run-date <YYYY-MM-DD> --ingested-at <ISO>` (add `--offline`
  to rebuild from cached raw without hitting Valet).
