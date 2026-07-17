// Canadian locale formatting. fr-CA is NOT en-CA with a comma: it uses a
// narrow no-break space for grouping and a no-break space before %. Formatter
// construction is expensive and the tooltip calls these on every hover, so
// instances are cached per (locale, shape).
const CACHE = new Map();

function formatter(lang, shape, opts) {
  const locale = lang === "fr" ? "fr-CA" : "en-CA";
  const id = `${locale}|${shape}`;
  let f = CACHE.get(id);
  if (!f) {
    f = new Intl.NumberFormat(locale, opts);
    CACHE.set(id, f);
  }
  return f;
}

export function num(value, lang, digits = 2) {
  return formatter(lang, `num${digits}`, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
}

// signDisplay:"exceptZero" replaces the hand-rolled "+" prefix in markets.js and
// closes the inconsistency with households.js, which omitted it.
export function signed(value, lang, digits = 2) {
  return formatter(lang, `signed${digits}`, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
    signDisplay: "exceptZero",
  }).format(value);
}

export function count(value, lang) {
  return formatter(lang, "count", {}).format(value);
}

// style:"unit" gives fr-CA its no-break space before the % sign for free.
export function pct(value, lang, digits = 1) {
  return formatter(lang, `pct${digits}`, {
    style: "unit",
    unit: "percent",
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
}
