import httpx
import pytest

from pipeline.valet_client import ValetClient, ValetError

BODY = {"observations": [{"d": "2026-07-13", "V39079": {"v": "2.25"}}]}


def _client(handler) -> ValetClient:
    return ValetClient(http=httpx.Client(transport=httpx.MockTransport(handler)))


def test_series_url_and_params():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json=BODY)

    body = _client(handler).get_observations("V39079", start="2020-01-01")
    assert body == BODY
    assert "/observations/V39079/json" in seen["url"]
    assert "start_date=2020-01-01" in seen["url"]


def test_group_url():
    def handler(request: httpx.Request) -> httpx.Response:
        assert "/observations/group/bond_yields_benchmark/json" in str(request.url)
        return httpx.Response(200, json=BODY)

    _client(handler).get_observations("bond_yields_benchmark", kind="group", recent=1)


def test_retries_then_raises_on_persistent_5xx():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503)

    with pytest.raises(ValetError):
        ValetClient(
            http=httpx.Client(transport=httpx.MockTransport(handler)),
            max_retries=2,
            backoff=0.0,
        ).get_observations("V39079")
    assert calls["n"] == 3
