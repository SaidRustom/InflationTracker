from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class SeriesConfig(BaseModel):
    id: str
    kind: str = "series"
    label_en: str
    label_fr: str
    frequency: str
    role: str
    metric_key: str | None = None
    source_url: str | None = None


class Thresholds(BaseModel):
    staleness_days: dict[str, int]
    max_null_ratio: float
    value_ranges: dict[str, tuple[float, float]]


class InflationBand(BaseModel):
    low: float
    high: float


class RevisionsConfig(BaseModel):
    # publish_limit must be >= 1: `events[-limit:]` with limit=0 is events[0:],
    # i.e. the ENTIRE ledger, so a 0 would silently publish everything instead of
    # nothing. Reject it at load rather than let it become a silent uncapped feed.
    publish_limit: int = Field(default=100, ge=1)


class AppConfig(BaseModel):
    start_date: str
    series: list[SeriesConfig]
    thresholds: Thresholds
    inflation_band: InflationBand = InflationBand(low=1.0, high=3.0)
    revisions: RevisionsConfig = RevisionsConfig()

    def by_metric_key(self, key: str) -> SeriesConfig:
        for s in self.series:
            if s.metric_key == key:
                return s
        raise KeyError(f"no series with metric_key={key!r}")


def load_config(series_path: Path, settings_path: Path) -> AppConfig:
    series = yaml.safe_load(series_path.read_text(encoding="utf-8"))["series"]
    settings = yaml.safe_load(settings_path.read_text(encoding="utf-8"))
    return AppConfig(
        start_date=settings["start_date"],
        series=[SeriesConfig(**s) for s in series],
        thresholds=Thresholds(**settings["thresholds"]),
        inflation_band=InflationBand(**settings["inflation_band"]),
        revisions=RevisionsConfig(**settings.get("revisions", {})),
    )
