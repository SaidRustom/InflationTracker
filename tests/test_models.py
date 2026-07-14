from pathlib import Path

from pipeline.models import AppConfig, load_config

CONFIG = Path("config")


def test_load_config_reads_series_and_thresholds():
    cfg = load_config(CONFIG / "series.yml", CONFIG / "settings.yml")
    assert isinstance(cfg, AppConfig)
    ids = {s.id for s in cfg.series}
    assert {"V39079", "BD.CDN.5YR.DQ.YLD", "V122667780", "CPI_TRIM"} <= ids
    assert cfg.thresholds.staleness_days["daily"] >= 1


def test_by_metric_key_resolves_yield_ids():
    cfg = load_config(CONFIG / "series.yml", CONFIG / "settings.yml")
    assert cfg.by_metric_key("yield_5y").id == "BD.CDN.5YR.DQ.YLD"
    assert cfg.by_metric_key("mortgage_5y_fixed").id == "V122667780"
