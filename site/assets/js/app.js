import { applyStaticText, currentLang, loadDict, otherLang } from "./i18n.js";
import { loadJSON } from "./data.js";

async function boot() {
  const lang = currentLang();
  document.documentElement.lang = lang;

  const dict = await loadDict(lang);
  applyStaticText(dict);

  const switcher = document.getElementById("lang-switch");
  switcher.href = `?lang=${otherLang(lang)}`;

  try {
    const manifest = await loadJSON("manifest.json");
    document.getElementById("last-refreshed").textContent = manifest.last_refreshed;
    const quality = document.getElementById("overall-quality");
    quality.textContent = manifest.overall_quality;
    quality.dataset.status = manifest.overall_quality;
  } catch (err) {
    console.error(err);
    document.getElementById("load-error").hidden = false;
  }
}

document.addEventListener("DOMContentLoaded", boot);
