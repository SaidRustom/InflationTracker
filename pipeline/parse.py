def flatten_observations(raw: dict) -> list[dict]:
    rows: list[dict] = []
    for obs in raw.get("observations", []):
        date = obs.get("d")
        if date is None:
            continue
        for key, cell in obs.items():
            if key == "d":
                continue
            value = cell.get("v") if isinstance(cell, dict) else None
            if value == "":
                value = None
            rows.append({"series_id": key, "obs_date": date, "value": value})
    return rows
