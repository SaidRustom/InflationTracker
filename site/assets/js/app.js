import { applyStaticText, currentLang, loadDict, otherLang } from "./i18n.js";
import { loadJSON } from "./data.js";
import { renderPolicy } from "./panels/policy.js";
import { renderMarkets } from "./panels/markets.js";
import { renderHouseholds } from "./panels/households.js";
import { renderTarget } from "./panels/target.js";

const PANELS = [renderPolicy, renderMarkets, renderHouseholds, renderTarget];

async function boot() {
  const lang = currentLang();
  document.documentElement.lang = lang;

  let failed = false;

  // Guarded: if the dictionary fails to load we keep the HTML fallback copy
  // rather than blanking the page. The disclaimer is a spec §2 bright line and
  // must survive a failed fetch.
  let dict = {};
  try {
    dict = await loadDict(lang);
    applyStaticText(dict);
  } catch (err) {
    console.error("i18n", err);
    failed = true;
  }
  document.getElementById("lang-switch").href = `?lang=${otherLang(lang)}`;

  try {
    const manifest = await loadJSON("manifest.json");
    const refreshed = new Date(manifest.last_refreshed);
    document.getElementById("last-refreshed").textContent = Number.isNaN(refreshed.getTime())
      ? manifest.last_refreshed
      : new Intl.DateTimeFormat(lang === "fr" ? "fr-CA" : "en-CA", { dateStyle: "long" }).format(refreshed);
    const quality = document.getElementById("overall-quality");
    quality.textContent = manifest.overall_quality;
    quality.dataset.status = manifest.overall_quality;
  } catch (err) {
    console.error("manifest", err);
    failed = true;
  }

  const root = document.getElementById("panels");
  for (const render of PANELS) {
    try {
      await render(root, dict, lang);
    } catch (err) {
      console.error(render.name, err);
      failed = true;
    }
  }

  document.getElementById("load-error").hidden = !failed;
}

document.addEventListener("DOMContentLoaded", boot);
