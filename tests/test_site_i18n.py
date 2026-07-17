import json
from html.parser import HTMLParser
from pathlib import Path

SITE = Path(__file__).resolve().parents[1] / "site"


def _dict(lang: str) -> dict:
    return json.loads((SITE / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))


class _FallbackCollector(HTMLParser):
    """Collect {data-i18n key: inline text} from index.html.

    The page's [data-i18n] elements are never nested, so one open element at a
    time is enough. convert_charrefs turns &amp; back into & so the HTML compares
    against en.json's raw text.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.pairs: dict[str, str] = {}
        self._key: str | None = None
        self._buf: list[str] = []
        self._depth = 0

    def handle_starttag(self, tag, attrs):
        if self._key is not None:
            self._depth += 1
            return
        found = dict(attrs).get("data-i18n")
        if found is not None:
            self._key = found
            self._buf = []
            self._depth = 0

    def handle_data(self, data):
        if self._key is not None:
            self._buf.append(data)

    def handle_endtag(self, tag):
        if self._key is None:
            return
        if self._depth > 0:
            self._depth -= 1
            return
        self.pairs[self._key] = "".join(self._buf).strip()
        self._key = None


def test_en_and_fr_have_identical_keys():
    en, fr = _dict("en"), _dict("fr")
    assert set(en) == set(fr), (
        f"en-only={sorted(set(en) - set(fr))} fr-only={sorted(set(fr) - set(en))}"
    )


def test_no_empty_translations():
    for lang in ("en", "fr"):
        for key, value in _dict(lang).items():
            assert value.strip(), f"{lang}.json: {key!r} is empty"


def test_index_fallback_copy_matches_en_json():
    en = _dict("en")
    collector = _FallbackCollector()
    collector.feed((SITE / "index.html").read_text(encoding="utf-8"))

    # Guard against a vacuous pass: if the parser silently collected nothing,
    # the loop below would assert nothing at all.
    assert len(collector.pairs) >= 8, f"only found {len(collector.pairs)} [data-i18n] elements"

    for key, text in collector.pairs.items():
        assert key in en, f"index.html uses data-i18n={key!r}, absent from en.json"
        assert text == en[key], f"{key}: HTML fallback {text!r} != en.json {en[key]!r}"
