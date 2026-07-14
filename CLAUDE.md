# CLAUDE.md — Inflation Tracker (BoC Monetary-Policy Dashboard)

> **House rule (read first):** The **Notion page is the single source of truth.** Keep it current as
> work lands — status, decisions, architecture, progress log. Update Notion in the *same change* as
> the code/docs. Canonical design prose lives in `docs/superpowers/specs/`; Notion mirrors + tracks it.

**Notion (source of truth):** Inflation Tracker — BoC Monetary-Policy Dashboard
https://app.notion.com/p/39dcea51fedf81028e24e6f748c1482b
(Projects DB · Stage: Planning · Lead: said-rustom)

**Status:** Planning — brainstorming the design (2026-07-14). No code scaffolded yet.
**Owner:** said-rustom · Solo · Portfolio piece for a Bank of Canada Developer (Data Operations) application.

## What this is
A free, public web dashboard on the **Bank of Canada Valet API** visualizing the **monetary-policy
transmission chain**: policy rate → CORRA → benchmark GoC bond yields → chartered-bank lending rates
→ CPI vs the 1–3% inflation-control target. Built as an **end-to-end data product** (ingestion →
transform → data-quality → visualization), because the target role is data-engineering-first.

## Verified BoC Valet series (checked live 2026-07-13/14)
| Purpose | Series / Group | Frequency |
|---|---|---|
| Policy rate (target overnight) | `V39079` (2.25% on 2026-07-13) | Daily (8 fixed dates) |
| Overnight funding | `AVG.INTWO` (CORRA) | Daily |
| Benchmark GoC yields | group `bond_yields_benchmark` (2/3/5/7/10yr) | Daily |
| Chartered-bank lending rates | `A4_RATES_MORTGAGES`, `A4_RATES_CONSUMER` | Weekly/Monthly |
| Core inflation vs target | `CPI_TRIM`, `CPI_MEDIAN`, `CPI_COMMON` | Monthly |

Base URL: `https://www.bankofcanada.ca/valet/` · no auth · JSON/CSV/XML · `?recent=N` / date-range params.
Series IDs belong in **config**, not code. A series can disappear — treat staleness as a real risk.

## Doc map
- **Notion page** — source of truth / tracker (link above).
- `docs/superpowers/specs/2026-07-14-inflation-tracker-design.md` — approved design record (once written).
