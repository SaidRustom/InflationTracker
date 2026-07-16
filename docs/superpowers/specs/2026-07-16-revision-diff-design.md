# Revision-Diff — Design Spec

> **Detecting and publishing what the Bank of Canada changed after it published it**
> Status: **Approved** (2026-07-16) · Owner: said-rustom · Solo · Portfolio piece
> Source of truth: [Notion — Inflation Tracker](https://app.notion.com/p/39dcea51fedf81028e24e6f748c1482b)
> Amends: `2026-07-14-inflation-tracker-design.md` §9 (data-quality) and §12 (Data-Trust tab)
> Scope: the headline feature of **Plan 3 (M4)**

---

## 1. Purpose

Detect when the Valet API **changes an observation it has already published**, record every such
change in a permanent ledger, and show it to the reader on the Data-Trust tab.

Revisions are what a central-bank data operation actually lives with: the number changing underneath
you is the *normal* case, not the exception. A public dashboard that can say

> *CPI-trim for 2026-03 changed from 2.9 to 3.1 — detected 2026-06-20*

makes visible the thing every other candidate dashboard silently hides. It also converts this repo's
committed-JSON git history from a happy accident into a designed product.

**Audience: the reader.** This is a transparency artifact, not an internal alarm. Wiring revisions
into `data_quality.json` as a check is a deliberate non-goal (§3).

## 2. Goals

- Detect `revised` / `late_publication` / `withdrawn` events between consecutive source vintages.
- Never attribute our own code changes to the Bank of Canada.
- Never claim to have checked the source when we did not.
- Never claim to know *when the Bank revised* — only when **we detected** it.
- State how far back detection can see, so an empty ledger is honest rather than reassuring.
- Bounded repo growth: the ledger is permanent, the vintages are not.

## 3. Non-goals

- **Revisions do not fail the pipeline.** They are normal. `run.py` exit status is unaffected.
- **No quality-check integration.** Surfacing `withdrawn` as a WARN in `data_quality.json` is the
  obvious follow-on and is explicitly deferred — it serves the "internal guard" purpose, which is
  not the purpose chosen for this feature.
- **No arbitrary vintage reconstruction.** We are not building ALFRED. Only the last two vintages
  are retained; the ledger, not the archive, is the product.
- **No revision markers on the four transmission charts.** Data-Trust tab only (spec §14: do not
  over-invest in the frontend).

## 4. Why diff raw vintages (the decision that matters)

Three sources of a baseline were considered:

| | Baseline | Verdict |
|---|---|---|
| **A** | Retained raw vintage, **re-parsed with today's parser** | **Chosen** |
| B | `data/curated/fact_observation.parquet` from the previous run | Rejected |
| C | Previously published `site/data/*.json` via git history | Rejected |

B and C compare **old code's output** against **new code's output**. The day a rounding rule or a
parse bug changes, every affected observation surfaces as a Bank of Canada revision — the artifact
would attribute our own commit to the Bank, confidently and in public. This pipeline is young;
`parse.py` and `transform.sql` *will* change.

A is immune, and the reason is precise: because the **source bytes** are retained and *both sides are
re-parsed with the current parser*, any change to our own code moves both sides identically and
cancels. What survives the diff is only what Valet actually said differently.

> A revision is a change in what the **source published** — not a change in what our code computed.
> Only A measures that.

B's attractions (zero new storage, a `FULL OUTER JOIN` in DuckDB that showcases the JD's SQL) do not
outweigh publishing false attributions. A costs ~3.4 MB steady-state.

## 5. Placement and retention

`pipeline/revisions.py`, called from `run.py` **after ingest, before transform** — it compares source
bytes, so it must run before anything derived exists.

Retention keeps the **last two** `data/raw/<run_date>/` directories:

- The run needs baseline *and* fresh fetch alive simultaneously, so a single `latest/` cannot work.
- Keeping run-date naming means `ingest.py` is unchanged and `--offline` keeps working untouched.
- Baseline = the newest vintage directory with a date **older than** `--run-date`.
- Prune to 2 **only on a run that actually reached the source** (i.e. the same condition that gates
  detection in §9). An offline run or a cache-fallback run leaves the vintages alone — it has no new
  vintage to make room for, and pruning on a run that fetched nothing risks discarding a baseline in
  exchange for nothing. **~3.4 MB steady-state**, versus ~0.63 GB/yr unbounded.

Vintages already committed remain in git history; nothing is lost retroactively.

## 6. Detection

Build `{(series_id, obs_date): float | None}` from each vintage via the existing
`flatten_observations`, **then cast to float**.

The cast must live here: `parse.py` returns `value` as a **string** (`{"v": "1.5"}` → `"1.5"`); the
float cast currently happens only in DuckDB. Without it, `"1.50"` → `"1.5"` reports as a revision
when nothing changed.

Classify every key present in the baseline:

| Baseline → New | Event |
|---|---|
| `2.9` → `3.1` | `revised` |
| `null` → `3.1` | `late_publication` |
| `3.1` → `null` | `withdrawn` |
| date present → date absent | `withdrawn` (`new = null`) |
| `null` → `null` | *(none)* |
| absent → present | *(none — a new observation)* |

**Series present in only one vintage are skipped entirely, not diffed.** `STATIC_TOTALCPICHANGE`
exists only in the 2026-07-15 vintage because Plan 2 added it. Without this rule, adding a series to
config reads as new data and *removing* one fires ~6,384 fake withdrawals. Config churn is not a BoC
revision. (A genuine Valet series disappearance surfaces as a `ValetError` in ingest, not here.)

## 7. The ledger — `data/curated/revisions.json`

Append-only. Permanent. The product.

```json
{
  "watching_since": "2026-07-14",
  "last_checked": "2026-07-16",
  "events": [
    {
      "series_id": "CPI_TRIM",
      "date": "2026-03-01",
      "kind": "revised",
      "old": 2.9,
      "new": 3.1,
      "detected_at": "2026-06-20"
    }
  ]
}
```

- **`watching_since`** — written once at ledger creation, never mutated. Means: *we hold a vintage
  from this date; anything the Bank changed before it is invisible to us.*
- **`last_checked`** — updated only on a run that actually reached the source (§9). Separates
  "never revised" from "the cron has been dead for three weeks".
- **`detected_at`, not `revised_on`** — diffing vintages reveals when we *noticed*, never when the
  Bank *acted*. With a daily cron we noticed within a day; if the cron fails for a week, within a
  week. Claiming a revision date we cannot know would breach the same bright line that keeps forecast
  language off this site.
- **Idempotent** — dedupe on the full tuple `(series_id, date, kind, old, new, detected_at)`, so
  re-running a run-date cannot duplicate rows.

`kind` is a closed set: `revised` | `late_publication` | `withdrawn`.

## 8. Publication and UI

`build_web` emits `site/data/revisions.json`, enriching `series_id` with EN/FR labels from config —
the ledger itself stays minimal and label-free.

Publishes the most recent **N** events (default 100) plus `total_events`, so the tab can state
*"showing 100 of 342"*. No silent truncation. `config/settings.yml` has no `revisions` block today —
the plan adds `revisions.publish_limit`, keeping the limit in **config, not code**, per the house rule
that already governs series IDs and staleness thresholds.

**Data-Trust tab** renders a table — series label · observation date · kind · old → new · detected —
above the honesty line:

> **Watching for revisions since 2026-07-14 · last checked 2026-07-16.**

The empty state shows that sentence, **not** "no revisions found". With two days of history, that
line *is* the feature: it states the limit of what the page can see. All strings live in
`site/i18n/{en,fr}.json` per the house rule, and numbers use the `fr-CA` formatting fix landing
alongside in Plan 3.

## 9. Error handling & edge cases

Three ways this could claim to have checked when it did not — all three must leave `last_checked`
untouched and skip detection:

| Case | Behaviour |
|---|---|
| `--offline` | No fetch happened. Skip detection; `last_checked` unchanged. |
| Ingest fell back to cached raw (`run.py` catches `ValetError`) | The source was never reached. Skip detection; `last_checked` unchanged. Otherwise the page would claim "checked today" during a Valet outage. |
| First run, no baseline vintage | No events. Create the ledger with `watching_since = run_date`. |
| Ledger missing or corrupt | **Fail the run loudly.** Never silently recreate — that erases history, and an append-only ledger that quietly resets is worse than none. |
| Re-run of the same `--run-date` | Idempotent via the dedupe key (§7). |

## 10. Testing (TDD, pytest, matching the existing suite)

**Unit — `pipeline/revisions.py`:**

- Each of the five classifications in §6.
- `"1.50"` vs `"1.5"` → **no event** (the normalization trap).
- `null` → `null` → no event.
- Series in only one vintage → skipped, no events.
- First run, no baseline → empty ledger, `watching_since` set.
- Idempotency: same run-date twice → no duplicate rows.
- `watching_since` never mutates on later runs.
- `last_checked` untouched when offline and when ingest fell back to cache.
- Prune keeps exactly 2 vintages.
- Corrupt ledger → raises, does not reset.

**Unit — `build_web`:** caps at `publish_limit`, reports `total_events`, enriches EN/FR labels.

**Integration — the two real committed vintages as a fixture** (`data/raw/2026-07-14` vs
`2026-07-15`): expect **0 revisions**, 4 series each +1 observation, and `STATIC_TOTALCPICHANGE`
ignored as a config addition rather than reported as anything. A regression test against every
false-positive class above, built from data already in the repo.

## 11. Risks

| Risk | Mitigation |
|---|---|
| Our code changes read as BoC revisions | §4 — re-parse both sides with today's parser |
| Config churn reads as withdrawals | §6 — skip series present in only one vintage |
| Page claims freshness it doesn't have | §9 — `last_checked` only on a run that reached the source |
| Empty ledger reads as "nothing ever changes" | §8 — `watching_since` stated on the tab, always |
| A mass restatement bloats the ledger | Accepted. ~6,384 events ≈ 640 KB, once, and it is the truth. Publication is capped at N with the total stated, so the page stays small. |
| Float equality | Both sides parse from the same textual source with no arithmetic; `float("1.50") == float("1.5")`. Safe. |

## 12. Decisions log

- **2026-07-16 — Purpose: public transparency artifact**, not an internal quality guard. Decides the
  architecture: the deliverable is a permanent published ledger.
- **2026-07-16 — Retention: permanent ledger, last 2 vintages.** Refined from "last 1" because the
  run needs baseline and fetch simultaneously, and run-date naming keeps `ingest.py` and `--offline`
  untouched.
- **2026-07-16 — Three typed events, one row shape.** A withdrawal is not a revision; conflating them
  loses the "series can disappear" signal that `CLAUDE.md` names as a live risk.
- **2026-07-16 — Diff raw vintages (A), not curated (B) or published JSON (C).** §4. The only option
  that cannot attribute our commits to the Bank.
- **2026-07-16 — `detected_at`, not `revised_on`.** Corrects an overclaim made in the review that
  prompted this feature (*"revised … on 2026-06-20"*). We know when we looked, not when they acted.

## 13. References

- Approved design record: `docs/superpowers/specs/2026-07-14-inflation-tracker-design.md`
- Plan 2 (M3 dashboard, complete): `docs/superpowers/plans/2026-07-15-inflation-tracker-dashboard.md`
- BoC Valet API terms: <https://www.bankofcanada.ca/terms/>
- Prior art for vintage/revision archives: ALFRED (ArchivaL Federal Reserve Economic Data) — the
  canonical "what did the data look like on date X" store. This design deliberately keeps the ledger
  and drops the archive.
