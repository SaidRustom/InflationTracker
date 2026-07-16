import { loadJSON } from "../data.js";
import { t } from "../i18n.js";
import { baseOption, lineSeries, mountChart } from "../charts.js";

export async function renderTarget(root, dict, lang) {
  const data = await loadJSON("panel_target.json");
  const band = data.band;
  const bm = data.band_months ?? {
    months_inside: 0, latest_date: null, latest_value: null, latest_inside: false,
  };

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

  mountChart(section.querySelector("#chart-target"), option, {
    asOfLabel: t(dict, "tooltip.asOf"),
  });
}
