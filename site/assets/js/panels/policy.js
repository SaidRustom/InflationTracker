import { loadJSON } from "../data.js";
import { t } from "../i18n.js";
import { baseOption, lineSeries, mountChart } from "../charts.js";

export async function renderPolicy(root, dict, lang) {
  const data = await loadJSON("panel_policy.json");

  const section = document.createElement("section");
  section.className = "panel";
  section.innerHTML = `
    <h2>${t(dict, "panel.policy.title")}</h2>
    <p class="panel-note">${t(dict, "panel.policy.note")}</p>
    <div class="chart" id="chart-policy"></div>`;
  root.appendChild(section);

  const option = baseOption({ yAxisName: t(dict, "panel.policy.axis") });
  option.series = data.series.map((block) =>
    // step:'end' - the target holds flat until the next announcement changes it.
    lineSeries(block, lang, block.role === "policy" ? { step: "end", lineStyle: { width: 2.5 } } : {})
  );

  mountChart(section.querySelector("#chart-policy"), option);
}
