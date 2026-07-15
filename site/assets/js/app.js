import { applyStaticText, currentLang, loadDict, otherLang } from "./i18n.js";
import { loadJSON } from "./data.js";
import { renderPolicy } from "./panels/policy.js";

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
    document.getElementById("last-refreshed").textContent = manifest.last_refreshed;
    const quality = document.getElementById("overall-quality");
    quality.textContent = manifest.overall_quality;
    quality.dataset.status = manifest.overall_quality;

    const panels = document.getElementById("panels");
    await renderPolicy(panels, dict, lang);
  } catch (err) {
    console.error(err);
    failed = true;
  }

  document.getElementById("load-error").hidden = !failed;
}

document.addEventListener("DOMContentLoaded", boot);
