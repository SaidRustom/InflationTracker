# Plan 3c — Data & Methods Surface + Accessibility Statement — Design Spec

> **The trust surface: show readers what was revised, what the quality checks say, how the data was
> made — and stand behind a documented accessibility conformance claim.**
> Status: **Approved** (2026-07-17) · Owner: said-rustom · Solo · Portfolio piece
> Source of truth: [Notion — Inflation Tracker](https://app.notion.com/p/39dcea51fedf81028e24e6f748c1482b)
> Amends: `2026-07-14-inflation-tracker-design.md` §12 (i18n → multi-page). Consumes:
> `2026-07-16-revision-diff-design.md` §8.1 (the three-state revision contract).
> Scope: **Plan 3c of 3a/3b/3c/3d**

---

## 1. Purpose

Plans 3a and 3b built the ledger and made the page accessible; the numbers on the trust surface exist
but nothing renders them. This plan builds the reader-facing surface that answers *"can I trust these
numbers, and how were they made?"* — the Data Operations story the portfolio targets — and closes the
accessibility milestone with a **documented, published conformance claim**.

Three things ship:
1. A **Data & Methods page** rendering `revisions.json` (three states) and `data_quality.json`
   (10 series), plus methodology/lineage prose and the honesty rules.
2. A **bilingual accessibility statement** — a real conformance artifact, self-assessed.
3. The **full WCAG 2.1 AA audit** 3b deferred, over the whole site now that both surfaces exist.

## 2. The plan split (context)

| Plan | Scope | Status |
|---|---|---|
| **3a** | Revision-diff pipeline → `revisions.json` | **Done** (merged, live) |
| **3b** | Accessibility remediation + `fr-CA` formatting | **Done** (merged, live) |
| **3c** | *This.* Data & Methods page + accessibility statement + full WCAG audit | Approved |
| **3d** | `ci.yml` + `refresh.yml` + README | After |

## 3. Architecture — three static pages, one shared shell

The site becomes multi-page. No build step, no framework, no npm, no router — **separate real HTML
pages**, the natural static-site pattern and the lowest-risk choice on the accessibility axis (a
hand-rolled client-side router + ARIA tab pattern trades a small duplication problem for a large
fragility problem on the exact axis this milestone cares about).

| File | Role | Nav |
|---|---|---|
| `site/index.html` | Dashboard (four charts) — exists | nav item 1 |
| `site/data-methods.html` | Data & Methods — the trust surface | nav item 2 |
| `site/accessibility.html` | Accessibility statement | footer link (like Terms), **not** in nav |

### 3.1 The shared shell

A real `<nav>` goes in the header: **Dashboard · Data & Methods**. Every internal link **carries
`?lang=`** across (a `fr` reader stays `fr`).

The header (including `<nav>`) and footer are **byte-identical static HTML across all three pages**. A
new pytest test (§9) asserts this — DRY-via-test, the same pattern as the i18n parity test, chosen
because a no-build static site has no templating layer to share the fragment through.

**`aria-current="page"` is applied at runtime, not in the static markup.** If it were baked into each
page's HTML it would sit on a different link per page and the shells could not be byte-identical.
Instead `bootShell` sets `aria-current="page"` on the nav link matching the current page (identified
by its `pathname`). The static nav markup is therefore identical everywhere and the parity test is
simple; a no-JS reader loses only the "you are here" marker, not the navigation itself — an acceptable
progressive-enhancement tradeoff. The same applies to the lang-switch href: the static default is
identical across pages and `bootShell` updates it, exactly as `app.js` does today.

### 3.2 The shared boot

`app.js`'s boot — resolve lang, load dict, `applyStaticText`, set the lang-switch href, guard the
error region — is factored into `site/assets/js/shell.js`:

```js
export async function bootShell(lang)   // returns { dict, failed }
```

- `app.js` calls `bootShell`, then loads the manifest and renders the four panels (unchanged behaviour).
- `data-methods.js` calls `bootShell`, then renders the revision + quality sections.
- `accessibility.html` calls `bootShell` and nothing else — its content is static prose.

`bootShell` must preserve Plan 2's two load-bearing guards verbatim: the guarded i18n boot (a failed
dict load keeps the HTML fallback copy, never blanks the page) and the error banner's `failed` flag.
The factoring moves the code; it does not change its behaviour. **No page loads ECharts unless it
draws charts** — `data-methods.html` and `accessibility.html` do not include the vendored bundle.

## 4. The Data & Methods page

Four sections, in order. All numbers route through `format.js` (`fr-CA` in French); all dates stay
**ISO** (`2026-05-01` — correct in both Canadian locales, per 3b §6.1).

### 4.1 Revision ledger — the three states, verbatim from revision-diff §8.1

Reads `revisions.json`. `status` is the switch — **three states, never two**:

| `status` | Render |
|---|---|
| `never_checked` | *"Revision detection has not run yet."* **MUST NOT** render a count, and **MUST NOT** say "no revisions" — nothing has been looked for. |
| `watching`, `total_events == 0` | *"Watching for revisions since {watching_since} · last checked {last_checked}. None detected."* |
| `watching`, `total_events > 0` | A table (series · date · kind · old → new · detected), plus *"showing {len(events)} of {total_events}"* when capped. |

**Today's live payload is `never_checked`** (only offline runs have occurred), so that is the state
that ships. A two-state renderer that reads `total_events == 0` as "no revisions" is the exact lie
§8.1 exists to prevent — the code branches on `status` first, never on the count.

### 4.2 Data quality — 10 series, status never by colour alone

Reads `data_quality.json`: `{generated_at, overall, series: [{series_id, status, checks:
{freshness, value_range, monotonic, null_ratio}}]}`. Renders a table — series · status · the four
checks.

**SC 1.4.1 (Use of Color):** OK / WARN / FAIL is conveyed by a **text label plus a symbol**
(e.g. ✓ / ! / ✕), with colour only reinforcing. A reader who cannot distinguish the colours still
reads the status. The overall status already shows in the header status bar on `index.html`; the
table is its drill-down.

The check strings (`"fresh: 1d old"`, `"within range"`, …) are pipeline output, not i18n keys. They
are rendered verbatim as data — English-only is acceptable because they are machine-generated
diagnostic values, not page chrome. This is stated so a reviewer does not read it as an i18n gap.

### 4.3 How this is made — lineage prose

Bilingual: the four-stage pipeline (ingest → DuckDB SQL transform → data-quality → build_web), the
Valet source (public, no auth), and the transmission-chain story (policy rate → CORRA → GoC yields →
lending rates → CPI vs the 1–3% band). Prose, in `site/i18n/{en,fr}.json` like every other string.

### 4.4 The honesty rules — the differentiator

Why revisions say *detected*, not *revised* (a vintage diff knows when we looked, not when the Bank
acted). Why the page never forecasts. Why readouts come from the pipeline and are never recomputed in
JS. This section is what distinguishes the artifact for a Data Operations reviewer; it is prose, and
it restates in reader-facing language the disciplines the specs enforce in code.

## 5. The accessibility statement

`site/accessibility.html`, bilingual, linked from the footer of every page. A real conformance
artifact — a documented **self-assessment**, the kind Government of Canada sites publish. It states:

- **Method** — self-assessed by driving a real browser and inspecting the accessibility tree (this
  project's §14 verification method), against WCAG 2.1 Level AA.
- **Scope** — both pages, EN and FR.
- **Result** — per-criterion: the criteria checked and their outcome (pass / remediated).
- **Date** and a contact line.

**Claim discipline — the load-bearing rule of this plan.** The statement says
**"self-assessed against WCAG 2.1 AA"**, never **"certified"** or **"compliant"** unqualified.
A self-assessment is not a third-party certification. Claiming certification would be the exact
species of overclaim the revision-diff spec §4 was caught making — on a project whose entire product
is not overclaiming, and in an accessibility statement of all places, that failure mode is
disqualifying. The README carries the same wording.

## 6. Carried fixes from 3b

Two items 3b explicitly deferred, both closed here:

### 6.1 French y-axis tick labels

ECharts renders its own axis ticks with a period decimal (`2.5`) regardless of `lang` — a literal
counterexample to "every number renders in French", though screen-reader-invisible (the chart is
`role="img"` with a text alternative). Closed by a `yAxis.axisLabel.formatter` in `baseOption()`,
threaded with `lang`, formatting through `num()`. `baseOption`'s signature gains `lang`; the four
panels already have it in scope. This touches `index.html`'s charts only.

### 6.2 The fallback-copy collector — a prerequisite, done first

The `_FallbackCollector` in `tests/test_site_i18n.py` **silently skips nested `data-i18n`** elements
(a child with `data-i18n` inside a captured parent is never checked). 3b left this inert because
`index.html` has no nesting. This page **will** nest translated markup. Hardening the collector to
descend into nested `data-i18n` is **Task 1**, before any nesting is introduced — otherwise the
fallback-copy guard goes silently green while copy drifts.

Both i18n tests (parity, fallback-copy) also **generalize to iterate every HTML page** in `site/`,
not just `index.html`, so the new pages are covered.

## 7. Data flow

No pipeline change. `build_web` already emits `revisions.json` and `data_quality.json`; the Data &
Methods page reads them with the existing `loadJSON`. The methodology and honesty prose, the
accessibility statement, and all new chrome are new i18n strings. Nothing new is computed in JS —
the page reads published values and prose.

## 8. Error handling & edge cases

| Case | Behaviour |
|---|---|
| `revisions.json` fetch fails | The shared error region announces (3b's live region); the section shows its `data-i18n` fallback, not a blank. |
| `data_quality.json` fetch fails | Same — the section degrades to fallback copy, the banner announces. |
| `revisions.json` missing `status` (pre-3a payload) | Treat a missing `status` as `never_checked` — the safe, non-lying default. |
| A quality series has an unexpected `status` value | Render the raw value as text; do not assume OK. |
| No-JS | Each page's static fallback copy (headings, section intros, the disclaimer, the honesty rules) is real HTML, so the page is readable without JS. Only the live tables require JS. |

## 9. Testing

### Python (pytest) — three items

1. **Harden `_FallbackCollector`** (Task 1) to descend into nested `data-i18n`, and add a test that a
   nested element's fallback copy IS checked (guarding against the silent-green regression).
2. **Generalize both i18n tests** (parity, fallback-copy) to iterate every `.html` file in `site/`.
3. **Shell parity test** — the static header (with `<nav>`) and footer fragments are byte-identical
   across `index.html`, `data-methods.html`, `accessibility.html`. A drift fails here. (`aria-current`
   and the lang-switch href are runtime-applied per §3.1, so they are not in the static fragment and do
   not break parity.)

### Frontend — a real browser (§14: no JS test runner)

- **The three revision states**, each forced by stubbing the `revisions.json` response
  (`never_checked` ships live; `watching`+0 and `watching`+N are driven via a route stub, since the
  live payload only exercises one). Assert `never_checked` renders **no count and no "no revisions"**.
- **Quality table**: status is legible without colour — the accessibility tree exposes the text
  label, not just a coloured cell.
- **Navigation**: keyboard-traverse *between* pages; `aria-current="page"` on the active nav item;
  `?lang=` carried across every link; the lang-switch preserves the current page.
- **FR number sweep** now includes the axis ticks: `document.body.innerText` on the FR dashboard has
  no `\d+\.\d+`, and the chart's own tick labels read `2,5`.
- **The audit** (final task): every applicable Level A + AA criterion across both pages, via the
  accessibility tree; findings remediated; the statement's per-criterion results written from what
  was actually observed.
- Zero console errors, both languages, all three pages.

## 10. What we claim

Self-assessed against **WCAG 2.1 Level AA**, method and per-criterion results documented in the
published accessibility statement. **Never** "certified" or bare "compliant". The statement and the
README use identical wording.

## 11. Risks

| Risk | Mitigation |
|---|---|
| The revision block reads `total_events==0` as "no revisions" | §4.1 — branch on `status` first; the three states are distinct; browser-tested |
| Quality status conveyed by colour alone | §4.2 — text label + symbol; verified in the a11y tree |
| The shared shell drifts across three pages | §9 — byte-identical shell parity test |
| Nested `data-i18n` copy drifts undetected on the new page | §6.2 — harden the collector *first*, before nesting |
| "self-assessed" drifts into "certified" | §5, §10 — wording fixed in the spec, statement, and README |
| Plan 2's swallowed-error guards regress in the shell factoring | §3.2 — `bootShell` preserves both guards verbatim; browser-tested via route interception |
| A page loads ECharts it doesn't need | §3.1 — only `index.html` includes the vendored bundle |

## 12. Decisions log

- **2026-07-17 — Separate HTML pages, not a client-side router.** Natural static pattern; avoids the
  ARIA-tab fragility on the axis this milestone cares about. Shell kept in sync by a parity test.
- **2026-07-17 — One combined "Data & Methods" page**, not separate data-trust and methodology pages.
  Both answer one reader question; one surface to build, audit, and keep in the parity test.
- **2026-07-17 — Accessibility statement is a published self-assessment**, footer-linked, claiming
  "self-assessed against WCAG 2.1 AA" — never "certified". The honest and portfolio-strongest framing.
- **2026-07-17 — Quality status never by colour alone** (SC 1.4.1): text label + symbol.
- **2026-07-17 — Missing `status` ⇒ `never_checked`** — the non-lying default for a pre-3a payload.
- **2026-07-17 — Harden the fallback-copy collector first** (Task 1), before the new page nests
  translated markup — closes 3b's silent-green trap before it can bite.

## 13. References

- `2026-07-16-revision-diff-design.md` §8.1 — the three-state contract this page renders.
- `2026-07-17-plan-3b-design.md` §4/§10 — the claim-discipline precedent; §6.1 dates-stay-ISO; the two
  carried items (§6 here).
- WCAG 2.1: <https://www.w3.org/TR/WCAG21/>
- Accessibility statement precedent: Government of Canada accessibility statements.
