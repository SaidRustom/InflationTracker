export function seriesLabel(block, lang) {
  return lang === "fr" ? block.label_fr : block.label_en;
}

export function baseOption({ yAxisName = "%" } = {}) {
  return {
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
      // The slider below gives deliberate zoom control. Wheel-zoom would otherwise
      // swallow page scroll: ECharts' inside handler stops propagation, so a reader
      // scrolling past a chart gets captured and silently rescales the time axis.
      { type: "inside", zoomOnMouseWheel: false },
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
