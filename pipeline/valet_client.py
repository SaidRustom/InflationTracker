import time

import httpx


class ValetError(Exception):
    pass


class ValetClient:
    def __init__(
        self,
        base_url: str = "https://www.bankofcanada.ca/valet",
        http: httpx.Client | None = None,
        max_retries: int = 3,
        backoff: float = 0.5,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._http = http or httpx.Client(timeout=30.0)
        self._max_retries = max_retries
        self._backoff = backoff

    def get_observations(
        self,
        name: str,
        kind: str = "series",
        start: str | None = None,
        recent: int | None = None,
    ) -> dict:
        path = f"/observations/group/{name}/json" if kind == "group" else f"/observations/{name}/json"
        params: dict[str, str] = {}
        if start is not None:
            params["start_date"] = start
        if recent is not None:
            params["recent"] = str(recent)

        last_err: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                resp = self._http.get(self._base + path, params=params)
            except httpx.TransportError as exc:
                last_err = exc
            else:
                if resp.status_code < 400:
                    return resp.json()
                if resp.status_code < 500:
                    raise ValetError(f"{resp.status_code} for {name}: {resp.text[:200]}")
                last_err = ValetError(f"{resp.status_code} for {name}")
            if attempt < self._max_retries:
                time.sleep(self._backoff * (attempt + 1))
        raise ValetError(f"exhausted retries for {name}: {last_err}")
