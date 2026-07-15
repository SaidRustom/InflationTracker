const SUPPORTED = ["en", "fr"];

export function currentLang() {
  const raw = new URLSearchParams(window.location.search).get("lang");
  return SUPPORTED.includes(raw) ? raw : "en";
}

export function otherLang(lang) {
  return lang === "en" ? "fr" : "en";
}

export async function loadDict(lang) {
  const res = await fetch(`./i18n/${lang}.json`);
  if (!res.ok) throw new Error(`i18n ${lang}: ${res.status}`);
  return res.json();
}

export function t(dict, key) {
  return Object.prototype.hasOwnProperty.call(dict, key) ? dict[key] : key;
}

export function applyStaticText(dict) {
  for (const el of document.querySelectorAll("[data-i18n]")) {
    el.textContent = t(dict, el.dataset.i18n);
  }
}
