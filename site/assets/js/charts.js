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
export function asOfTooltipFormatter(series, asOfLabel) {
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
        return `<div style="white-space:nowrap">${swatch}${s.name}: <b>${pt[1].toFixed(2)}</b>${carried}</div>`;
      })
      .filter(Boolean);
    return `<div style="font-weight:600;margin-bottom:4px">${iso}</div>${rows.join("")}`;
  };
}

export function baseOption({ yAxisName = "%" } = {}) {
  return {
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

export function mountChart(el, option, { asOfLabel } = {}) {
  if (asOfLabel) {
    const palette = option.color || PALETTE;
    const series = option.series.map((s, i) => ({
      name: s.name,
      data: s.data,
      color: palette[i % palette.length],
    }));
    option.tooltip = { ...option.tooltip, formatter: asOfTooltipFormatter(series, asOfLabel) };
  }
  const chart = echarts.init(el);
  chart.setOption(option);
  window.addEventListener("resize", () => chart.resize());
  return chart;
}
