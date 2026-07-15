import { loadJSON } from "../data.js";
import { t } from "../i18n.js";
import { baseOption, lineSeries, mountChart } from "../charts.js";

export async function renderMarkets(root, dict, lang) {
  const data = await loadJSON("panel_markets.json");
  const latest = data.yield_slope.length ? data.yield_slope[data.yield_slope.length - 1] : null;

  const inverted = Boolean(latest && latest.inverted);
  const shapeKey = inverted ? "panel.markets.inverted" : "panel.markets.normal";
  const shapeClass = inverted ? "flag-inverted" : "flag-normal";
  const slopeText = latest ? `${latest.slope > 0 ? "+" : ""}${latest.slope.toFixed(2)}` : "—";

  const section = document.createElement("section");
  section.className = "panel";
  section.innerHTML = `
    <h2>${t(dict, "panel.markets.title")}</h2>
    <p class="panel-note">${t(dict, "panel.markets.note")}</p>
    <div class="readout">
      <div>
        <span class="readout-label">${t(dict, "panel.markets.slopeLabel")}</span>
        <span class="readout-value">${slopeText}</span>
      </div>
      <div>
        <span class="readout-label">${t(dict, "panel.markets.curveLabel")}</span>
        <span class="readout-value ${shapeClass}">${t(dict, shapeKey)}</span>
      </div>
    </div>
    <div class="chart" id="chart-markets"></div>`;
  root.appendChild(section);

  const option = baseOption({ yAxisName: t(dict, "panel.markets.axis") });
  option.series = [
    ...data.policy.map((block) =>
      lineSeries(block, lang, { step: "end", lineStyle: { width: 2.5, type: "dashed" } })
    ),
    ...data.yields.map((block) => lineSeries(block, lang)),
  ];

  mountChart(section.querySelector("#chart-markets"), option);
}
