import { loadJSON } from "../data.js";
import { t } from "../i18n.js";
import { baseOption, lineSeries, mountChart } from "../charts.js";
import { signed } from "../format.js";

export async function renderHouseholds(root, dict, lang) {
  const data = await loadJSON("panel_households.json");
  const latest = data.spread.length ? data.spread[data.spread.length - 1] : null;
  const spreadText = latest ? signed(latest.spread, lang) : "—";

  const section = document.createElement("section");
  section.className = "panel";
  section.innerHTML = `
    <h2>${t(dict, "panel.households.title")}</h2>
    <p class="panel-note">${t(dict, "panel.households.note")}</p>
    <div class="readout">
      <div>
        <span class="readout-label">${t(dict, "panel.households.spreadLabel")}</span>
        <span class="readout-value">${spreadText}</span>
      </div>
    </div>
    <div class="chart" id="chart-households"></div>`;
  root.appendChild(section);

  const option = baseOption({ yAxisName: t(dict, "panel.households.axis") });
  option.series = [
    ...data.lending.map((block) => lineSeries(block, lang, { lineStyle: { width: 2.5 } })),
    ...data.yield5.map((block) => lineSeries(block, lang)),
    {
      name: t(dict, "panel.households.spreadSeries"),
      type: "line",
      showSymbol: false,
      connectNulls: false,
      lineStyle: { type: "dotted" },
      areaStyle: { opacity: 0.08 },
      data: data.spread.map((p) => [p.date, p.spread]),
    },
  ];

  mountChart(section.querySelector("#chart-households"), option, { dict, lang, jsonName: "panel_households.json" });
}
