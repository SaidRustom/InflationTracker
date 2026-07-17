# Plan 3b — Accessibility & `fr-CA` Foundation — Design Spec

> **The reader-facing foundation: make the page usable without sight or a mouse, and make its
> numbers French.**
> Status: **Approved** (2026-07-17) · Owner: said-rustom · Solo · Portfolio piece
> Source of truth: [Notion — Inflation Tracker](https://app.notion.com/p/39dcea51fedf81028e24e6f748c1482b)
> Amends: `2026-07-14-inflation-tracker-design.md` §12 (i18n) and §14 (frontend investment)
> Scope: **Plan 3b of 3a/3b/3c/3d**

---

## 1. Purpose

Two gaps found by the BoC-reviewer critique of 2026-07-16, both **currently disqualifying for a
federal institution**, both verified against the code rather than assumed:

- **Accessibility.** Four `<canvas>` charts with no text alternative, no keyboard path, no focus
  styles. A screen-reader user cannot reach a single chart value; a keyboard user cannot read the
  tooltip at all. WCAG 2.1 AA is binding on a federal institution.
- **French is half-done.** Every number goes through `toFixed()`; there is **no `Intl` anywhere** in
  `site/assets/js/`. French renders `3.97` where `fr-CA` requires `3,97`. Translated ≠ localized, and
  on a Bank-branded page anglophone number formatting generates a complaint.

This plan fixes **what demonstrably fails on the page that exists today**. It adds no new surfaces.

## 2. Scope and the plan split

Plan 3 was originally one plan carrying four subsystems. It is now four:

| Plan | Scope | Status |
|---|---|---|
| **3a** | Revision-diff: pipeline → published `site/data/revisions.json` | **Done** (merged 2026-07-16, 90 tests) |
| **3b** | *This.* Accessibility remediation + `fr-CA` formatting | Approved |
| **3c** | Data-Trust tab + methodology page — the two new surfaces | Next |
| **3d** | `ci.yml` + `refresh.yml` + README | After |

**Why the foundation comes before the surfaces:** both new surfaces in 3c need a nav/shell that does
not exist yet, and building either *before* this plan means writing fresh `toFixed` calls and
canvas-without-`aria` — adding to the exact debt 3b exists to clear.

## 3. Goals

- A screen-reader user can obtain every chart's series, date range, latest values, and its recent
  observations as real numbers.
- A keyboard user can reach every interactive element and **see** where focus is.
- The error banner announces when it appears.
- Every number renders per `fr-CA` in French and `en-CA` in English.
- **Claim only what is verified.**

## 4. Non-goals

- **No blanket "WCAG 2.1 AA compliant" claim.** We claim exactly the criteria we test (§10). A
  compliance claim is an audit result we have not produced. Claiming it would be the same species of
  overclaim as `2026-07-16-revision-diff-design.md` §4 — on a project whose whole product is not
  overclaiming, that is the defect that matters most.
- **No full WCAG audit.** Right instinct, wrong time: 3c adds two surfaces, so an audit now would need
  re-running. Do it in 3c, over the whole site.
- **No new surfaces** — Data-Trust tab, methodology page: 3c.
- **No pipeline changes.** Everything here is composed from already-published JSON.
- **No JS test runner** — spec §14 stands. Verified by driving a real browser (§11).
- **No `axe-core`.** It would be a new vendored dependency for test-time only. Reconsider in 3c's audit.

## 5. Why ECharts' built-in `aria` is not used

**Measured, not assumed.** The vendored ECharts 6.1.0 does ship `aria: { enabled: true }`. Enabling it
on panel 4 generates 1,173 characters of:

> *"This is a chart. It consists of 4 series count. The 0 series is a Line chart representing Total CPI
> (headline). The first 10 items are: 946702800000, 2.2, 949381200000, 2.7, …"*

It is unusable here, on four independent counts:

1. **Raw epoch milliseconds** (`946702800000`) read aloud to a screen-reader user.
2. **Broken grammar** — "4 series count", "The 0 series".
3. **Hardcoded English.** No FR. This alone disqualifies it — it would break bilingual parity.
4. **A silent truncation** to "the first 10 items" of 317 — the *oldest* ten, not the newest.

Turning it on would *look* like accessibility while being noise. We hand-roll (§7).

## 6. The formatting layer — `site/assets/js/format.js`

One new module. `Intl.NumberFormat(lang === "fr" ? "fr-CA" : "en-CA")`, with **cached formatter
instances** — the tooltip calls these on every hover and `Intl` construction is expensive.

```js
export function num(value, lang, digits = 2)     // 3.97  | 3,97
export function signed(value, lang, digits = 2)  // +0.71 | +0,71
export function count(value, lang)               // 4,482 | 4 482   (NBSP in fr)
export function pct(value, lang, digits = 1)     // 3.2%  | 3,2 %   (NBSP before % in fr)
```

Outputs above are **measured** from `Intl` in a real browser, not guessed. `pct` uses
`style: "unit", unit: "percent"`, which produces the `fr-CA` NBSP-before-`%` convention for free.
`signed` uses `signDisplay: "exceptZero"`.

**Replaces all four `toFixed` sites** — verified at these exact lines:

| Site | What |
|---|---|
| `site/assets/js/charts.js:68` | tooltip value |
| `site/assets/js/panels/households.js:8` | observed spread |
| `site/assets/js/panels/markets.js:12` | 2s10s slope |
| `site/assets/js/panels/target.js:15` | latest headline CPI |

`signDisplay` also retires `markets.js`'s hand-rolled `+` prefix — and closes a carried Minor,
confirmed against the code: `panels/households.js:8` omits the `+` that `panels/markets.js:12` adds,
so the two readouts are inconsistent today.

### 6.1 Dates are deliberately untouched

**Measured:** both `en-CA` and `fr-CA` render `2026-05-01`. Canada uses ISO in both official
languages, so every existing date is already correct bilingually. No date work is needed.

One exception, and it is chrome rather than data: `last_refreshed` currently renders the raw
`2026-07-15T00:00:00`. It becomes a localized long date — `July 15, 2026` / `15 juillet 2026` — via
`Intl.DateTimeFormat`. The rule: **data stays ISO** (unambiguous, matches the source, matches the
tooltip and tables); **chrome gets prose**.

## 7. Chart text alternative

Each panel's `.chart` div gains `role="img"`, `tabindex="0"`, and an i18n-templated `aria-label`:

> *Line chart. Target for the overnight rate, CORRA. 2000-01-04 to 2026-07-14. Latest: target 2.25%,
> CORRA 2.28%.*

**Composed from verbatim reads only** — series labels (already i18n'd), `points[0][0]`,
`points[last][0]`, and the latest non-null value per series via `lastObservedOnOrBefore`, which
already exists in `charts.js` from the 2026-07-16 tooltip fix.

**No computed characterization** — no "rising", no "inverted", no "above target". Those are *derived
claims*, and `CLAUDE.md`'s rule that readouts come from published JSON and are never recomputed in JS
applies to the accessible readout exactly as it does to the visual one. Otherwise the accessible text
could contradict the visible page — the precise class of bug this project keeps catching.

The label deliberately does **not** restate the readouts (2s10s slope, spread, months-in-band). Those
are already accessible HTML text; duplicating them into the label is noise, not access.

## 8. The data table — one per series

A native `<details>` below each chart. Native because it is keyboard-accessible with zero JS, and
because it is **visible to everyone who opens it** rather than SR-only hidden content.

```html
<details class="chart-data">
  <summary>View data as a table</summary>
  <table>
    <caption>Insured 5yr+ fixed mortgage rate — 12 most recent of 161</caption>
    <thead><tr><th scope="col">Date</th><th scope="col">Rate (%)</th></tr></thead>
    <tbody>…</tbody>
  </table>
  <table>
    <caption>GoC benchmark yield: 5 year — 12 most recent of 6,384</caption>
    …
  </table>
  <p><a href="./data/panel_households.json">Full data</a></p>
</details>
```

**One table per series, each stating its own cap.** A single panel-wide table breaks on panel 3 for
the same reason the tooltip did: the mortgage is monthly (161 points), the 5-year yield is daily
(6,384), and **only 90 of 161 dates coincide**. The 12 most recent dates are therefore all daily, and
the mortgage column would be **entirely empty**. Per-series tables stay coherent under mixed
frequency.

- `RECENT_ROWS = 12`, a named constant in `charts.js`.
- Each caption states *"12 most recent of N"* — **no silent truncation**, per the house rule.
- Counts run through `count()` so N is `6 384` in French.
- Each panel links its own JSON for the full data.
- Null observations (holidays) render as an em dash, not a blank — absence stated, not implied.

## 9. Dynamic content — one live region, deliberately

**The error banner** is wrapped in an always-present `aria-live="polite"` container:

```html
<div aria-live="polite">
  <p id="load-error" class="load-error" hidden data-i18n="app.error">…</p>
</div>
```

This shape is load-bearing. Live regions announce on **content change, not visibility change**, and a
`hidden` region is ignored entirely — so adding `aria-live` to the existing banner would announce
**nothing**. Unhiding the child *inside* a live parent changes the parent's computed text, which does
announce. The banner's `hidden` default and its `data-i18n` fallback copy both stay: Plan 2 fixed a
swallowed-error bug here twice, and neither guard may regress.

**The status bar gets no live region, on purpose.** It is written once at boot and read normally in
document order. Announcing "Last refreshed…, Data quality OK" over every page load is interruption,
not accessibility.

`prefers-reduced-motion: reduce` disables ECharts' load animation (`animation: false`). Good practice;
**not part of the claim** — SC 2.3.3 is AAA.

## 10. What we claim

Remediated and verified against:

| SC | Level | What was wrong |
|---|---|---|
| **1.1.1** Non-text Content | A | Four canvases with no text alternative |
| **1.4.13** Content on Hover or Focus | AA | Tooltip reachable only by mouse |
| **2.4.1** Bypass Blocks | A | No skip link |
| **2.4.7** Focus Visible | AA | **Zero** focus styles in 82 lines of CSS |
| **4.1.3** Status Messages | AA | Error banner revealed silently |

Wording for the README and spec: *"the four charts, the error banner, the status bar and keyboard
navigation were remediated and verified against SC 1.1.1, 1.4.13, 2.4.1, 2.4.7 and 4.1.3."*
**Never** "WCAG 2.1 AA compliant".

## 11. Testing

### Python (pytest) — two integrity tests, the only pytest work here

The pipeline does not change. Both of these are carried Notion backlog items, and 3b is the
i18n-touching plan:

1. **i18n key parity** — `en.json` and `fr.json` have identical key sets. 3b adds ~10 keys, and FR
   parity is an Official Languages matter, not a nicety. Currently verified only by hand.
2. **`index.html` fallback copy matches `en.json`** — every `[data-i18n]` element's inline text equals
   its `en.json` value, so the spec §2 disclaimer cannot drift between its two sources. Plan 2 flagged
   this as unguarded: "no automated guard ties HTML fallback copy to en.json".

### Frontend — a real browser (spec §14: no JS test runner)

Playwright's `browser_snapshot` **returns the accessibility tree**, so we assert against what a screen
reader actually receives, not against markup we hope implies it:

- Each chart appears as a labelled image; the label names its series, range, and latest values.
- The `<details>` tables are reachable and their captions state the caps.
- **The banner announces**: force a fetch failure with a route interceptor (Plan 2's method — the
  browser's disk cache will serve a 200 for a file you renamed, so only interception proves it) and
  confirm the live region's computed text changes.
- Tab order: pressing Tab reaches skip link → lang switch → each chart → each `<summary>`, with a
  visible focus indicator at each stop.
- `fr-CA` output verified live in both languages: `3,97`, `+0,71`, `4 482`, `3,2 %`.
- Zero console errors, both languages.

## 12. Risks

| Risk | Mitigation |
|---|---|
| The accessible text contradicts the visual page | §7 — composed from published values only; no derived claims |
| `aria-live` added but never announces (hidden region) | §9 — always-present live parent; verified by route interceptor, not by inspection |
| The `<details>` tables bloat the DOM | 12 rows × ~2-4 series × 4 panels ≈ 150 rows total. Full tables (25k cells) explicitly rejected in §8 |
| A capped table reads as the whole series | §8 — every caption states "12 most recent of N" |
| Plan 2's swallowed-error guards regress | §9 — the `hidden` default and `data-i18n` fallback are load-bearing and named here |
| "Verified" drifts into "compliant" | §4, §10 — the claim wording is fixed in the spec |

## 13. Decisions log

- **2026-07-17 — 3b is foundation only; surfaces are 3c.** Both new surfaces need a nav that does not
  exist; building them first would add to the debt 3b clears.
- **2026-07-17 — Labelled chart + per-series `<details>` table**, not aria-label alone (a SR user could
  never reach an observation) and not full tables (~25k cells serving nobody).
- **2026-07-17 — ECharts' built-in `aria` rejected on measured evidence** (§5): epoch milliseconds,
  broken grammar, hardcoded English, silent truncation.
- **2026-07-17 — Dates untouched** (§6.1): both Canadian locales are ISO. Measured.
- **2026-07-17 — Claim the tested criteria, never blanket AA** (§4, §10).
- **2026-07-17 — Status bar gets no live region** (§9): announcing it on every load is interruption.

## 14. References

- BoC-reviewer critique that prompted this: Notion progress log, 2026-07-16.
- `docs/superpowers/specs/2026-07-14-inflation-tracker-design.md` — §12 i18n, §14 frontend investment.
- `docs/superpowers/specs/2026-07-16-revision-diff-design.md` — §8.1 binds 3c's Data-Trust tab to
  three states; the overclaim lesson in its §4.1/§11 is why §4 and §10 here are worded as they are.
- WCAG 2.1: <https://www.w3.org/TR/WCAG21/>
