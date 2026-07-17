import { count, num } from "./format.js";
import { t } from "./i18n.js";

// ECharts 6.1.0's default palette, pinned rather than inherited. The tooltip
// draws its own swatches and needs each series' colour up front; leaving it
// implicit would also let an ECharts upgrade silently repaint every panel.
const PALETTE = [
  "#5070dd", "#b6d634", "#505372", "#ff994d", "#0ca8df",
  "#ffd10a", "#fb628b", "#785db0", "#3fbe95",
];

export function seriesLabel(block, lang) {
  return lang === "fr" ? block.label_fr : block.label_en;
}

// Last observation on or before `iso`, or null if the series hasn't started yet.
// Dates are ISO 'YYYY-MM-DD', which sort lexicographically, so plain string
// comparison is chronological and sidesteps timezone parsing entirely.
function lastObservedOnOrBefore(data, iso) {
  let lo = 0;
  let hi = data.length - 1;
  let idx = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (data[mid][0] <= iso) {
      idx = mid;
      lo = mid + 1;
    } else {
      hi = mid - 1;
    }
  }
  // Walk back over nulls: a holiday gap is an absence, not an observation.
  for (let i = idx; i >= 0; i -= 1) {
    if (data[i][1] != null) return data[i];
  }
  return null;
}

function hoveredIso(hovered) {
  const v = Array.isArray(hovered.value) ? hovered.value[0] : hovered.axisValue;
  if (typeof v === "string") return v;
  const d = new Date(v); // defensive: only reached if no series held the exact instant
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

// ECharts' axis tooltip lists only the series holding a point at the exact
// hovered timestamp. Panel 3 mixes a monthly series (mortgage: 161 points,
// dated to month start) with a daily one (5yr yield: 6384 points), and only 90
// of those dates coincide - so on ~99% of the axis the monthly series silently
// vanished from the tooltip and the panel looked broken.
//
// Resolve every series to its last observation on or before the hovered date
// instead. Anything carried forward is labelled with the date it actually comes
// from, so a May mortgage rate read on a June hover is never passed off as a
// June observation. This mirrors the pipeline's own ASOF-join semantics and the
// step:'end' treatment the policy rate already gets in policy.js.
export function asOfTooltipFormatter(series, asOfLabel, lang) {
  return (params) => {
    const hovered = Array.isArray(params) ? params[0] : params;
    if (!hovered) return "";
    const iso = hoveredIso(hovered);
    const rows = series
      .map((s) => {
        const pt = lastObservedOnOrBefore(s.data, iso);
        if (!pt) return ""; // series has no observation yet at this date
        const swatch =
          `<span style="display:inline-block;width:9px;height:9px;border-radius:50%;` +
          `background:${s.color};margin-right:6px"></span>`;
        const carried = pt[0] !== iso ? ` <span style="opacity:.55">(${asOfLabel} ${pt[0]})</span>` : "";
        return `<div style="white-space:nowrap">${swatch}${s.name}: <b>${num(pt[1], lang)}</b>${carried}</div>`;
      })
      .filter(Boolean);
    return `<div style="font-weight:600;margin-bottom:4px">${iso}</div>${rows.join("")}`;
  };
}

export function baseOption({ yAxisName = "%" } = {}) {
  return {
    // SC 2.3.3 is AAA and not part of this plan's claim, but suppressing the
    // load animation for readers who asked for less motion is nearly free.
    animation: !window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    color: PALETTE,
    grid: { left: 52, right: 18, top: 28, bottom: 56 },
    tooltip: { trigger: "axis", axisPointer: { type: "line" } },
    legend: { type: "scroll", top: 0, icon: "roundRect" },
    xAxis: { type: "time", axisLine: { lineStyle: { color: "#9aa0a6" } } },
    yAxis: {
      type: "value",
      name: yAxisName,
      scale: true,
      splitLine: { lineStyle: { color: "#eef0f3" } },
    },
    dataZoom: [
      // The slider below is the zoom control; drag still pans. Wheel-zoom is locked
      // off because ECharts' inside roam controller preventDefaults/stopPropagates
      // wheel events - on a page of four stacked charts that strands a reader
      // mid-scroll. zoomOnMouseWheel alone only suppresses the rescale, not the
      // event capture; zoomLock is what restores page scrolling.
      { type: "inside", zoomLock: true },
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

// The chart's text alternative. Composed ONLY from published values - series
// labels, the first and last dates, and each series' latest non-null value.
// Deliberately no characterisation ("rising", "inverted"): those are derived
// claims, and CLAUDE.md's never-recompute-in-JS rule governs the accessible
// readout exactly as it governs the visual one. Otherwise the screen-reader
// text could contradict the visible page.
//
// It also does not restate the readouts (slope, spread, months-in-band) - those
// are already accessible HTML text, so repeating them here is noise, not access.
export function chartAria(series, dict, lang) {
  const withData = series.filter((s) => s.data.length);
  if (!withData.length) return t(dict, "chart.aria.empty");

  const names = withData.map((s) => s.name).join(", ");
  let start = withData[0].data[0][0];
  let end = withData[0].data[withData[0].data.length - 1][0];
  for (const s of withData) {
    const first = s.data[0][0];
    const last = s.data[s.data.length - 1][0];
    if (first < start) start = first;
    if (last > end) end = last;
  }

  const latest = withData
    .map((s) => {
      const pt = lastObservedOnOrBefore(s.data, end);
      return pt ? `${s.name}: ${num(pt[1], lang)}` : null;
    })
    .filter(Boolean)
    .join(", ");

  return t(dict, "chart.aria", { series: names, start, end, latest });
}

// 12 rows x ~2-4 series x 4 panels is ~150 rows page-wide. Full tables would be
// ~25,000 cells - fidelity that serves nobody, and slower for everyone.
const RECENT_ROWS = 12;

// One table PER SERIES, not one per panel. A panel-wide table breaks on panel 3
// for the same reason the tooltip did: the mortgage is monthly (161 points), the
// 5-year yield daily (6,384), and only 90 dates coincide - so the 12 most recent
// dates are all daily and the mortgage column would be entirely empty.
function seriesTable(s, dict, lang) {
  const table = document.createElement("table");

  const caption = document.createElement("caption");
  caption.textContent = t(dict, "chart.table.caption", {
    series: s.name,
    shown: count(Math.min(RECENT_ROWS, s.data.length), lang),
    total: count(s.data.length, lang),
  });
  table.appendChild(caption);

  const thead = document.createElement("thead");
  const headRow = document.createElement("tr");
  for (const key of ["chart.table.date", "chart.table.value"]) {
    const th = document.createElement("th");
    th.scope = "col";
    th.textContent = t(dict, key);
    headRow.appendChild(th);
  }
  thead.appendChild(headRow);
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  for (const [date, value] of s.data.slice(-RECENT_ROWS).reverse()) {
    const row = document.createElement("tr");
    const dateCell = document.createElement("th");
    dateCell.scope = "row";
    dateCell.textContent = date; // ISO: correct in BOTH en-CA and fr-CA
    const valueCell = document.createElement("td");
    // A null is a holiday/gap. Say so with an em dash rather than leaving a
    // blank cell, which reads as an oversight.
    valueCell.textContent = value == null ? "—" : num(value, lang);
    row.append(dateCell, valueCell);
    tbody.appendChild(row);
  }
  table.appendChild(tbody);
  return table;
}

// Built with DOM APIs, not innerHTML: every cell goes through textContent, so
// there is no escaping question to get wrong on a new surface.
export function dataDetails(series, dict, lang, jsonName) {
  const details = document.createElement("details");
  details.className = "chart-data";

  const summary = document.createElement("summary");
  summary.textContent = t(dict, "chart.table.summary");
  details.appendChild(summary);

  for (const s of series) {
    if (s.data.length) details.appendChild(seriesTable(s, dict, lang));
  }

  const link = document.createElement("a");
  link.href = `./data/${jsonName}`;
  link.textContent = t(dict, "chart.table.fullData");
  const p = document.createElement("p");
  p.className = "chart-data-link";
  p.appendChild(link);
  details.appendChild(p);

  return details;
}

export function mountChart(el, option, { dict, lang, jsonName } = {}) {
  // Declared outside the `if` because Tasks 3 and 4 also consume it.
  const palette = option.color || PALETTE;
  const series = option.series.map((s, i) => ({
    name: s.name,
    data: s.data,
    color: palette[i % palette.length],
  }));

  if (dict) {
    option.tooltip = {
      ...option.tooltip,
      formatter: asOfTooltipFormatter(series, t(dict, "tooltip.asOf"), lang),
    };
    el.setAttribute("role", "img");
    el.setAttribute("tabindex", "0");
    el.setAttribute("aria-label", chartAria(series, dict, lang));
  }

  const chart = echarts.init(el);
  chart.setOption(option);

  if (dict && jsonName) {
    el.insertAdjacentElement("afterend", dataDetails(series, dict, lang, jsonName));
  }

  window.addEventListener("resize", () => chart.resize());
  return chart;
}
