"""Run fault detection + prediction for all bins and write predictions.json.

Input:  data/bins_locations.json  (id, lat, lon, zone)   -> from backend
        data/readings.csv         (sensor readings)       -> from backend
Output: data/predictions.json     -> for the routing algorithm and the website
"""
import argparse
import json
from datetime import datetime
from pathlib import Path

import pandas as pd

from . import config, faults, features, predict


def run(bins: list[dict], readings: pd.DataFrame, now: datetime,
        ctx: features.Context | None = None) -> dict:
    ctx = ctx or features.load_context()
    readings = readings.copy()
    readings["timestamp"] = pd.to_datetime(readings["timestamp"])
    readings = readings[readings.timestamp <= now]
    by_sensor = dict(tuple(readings.groupby("sensor_id")))

    # Learn the model (weekday, temperature, events) from all healthy sensors
    issues_of = {b["id"]: faults.check_sensor(by_sensor.get(b["id"], pd.DataFrame(columns=readings.columns)), now)
                 for b in bins}
    healthy = {bid: r for bid, r in by_sensor.items() if not faults.has_fault(issues_of.get(bid, []))}
    model = predict.fit(bins, healthy, ctx)

    out = []
    for b in bins:
        r = by_sensor.get(b["id"], pd.DataFrame(columns=readings.columns))
        issues = issues_of[b["id"]]
        base = {"id": b["id"], "lat": b["lat"], "lon": b["lon"], "zone": b.get("zone"),
                "observed_at": r.timestamp.max().isoformat() if not r.empty else None,
                "osm_id": b.get("osm_id"), "volume_l": b.get("volume_l", config.BIN_VOLUME_L),
                # Sensor battery (last reading), shown to the crew; below config.LOW_BATTERY it is a warning
                "battery_percent": (round(float(r.battery_percent.iloc[-1]), 1)
                                    if not r.empty and "battery_percent" in r.columns else None)}

        if faults.has_fault(issues) or r.empty:
            # Don't trust the sensor: show it as a fault, route falls back to the fixed schedule
            out.append({**base,
                        "fill_percent": float(r.fill_percent.iloc[-1]) if not r.empty else None,
                        "fill_band": (predict.fill_band(float(r.fill_percent.iloc[-1]))
                                       if not r.empty else None),
                        "predicted_full_at": None, "hours_until_full": None,
                        "status": "fault", "fault": True,
                        "reason": "; ".join(i.message for i in issues if i.severity == "fault"),
                        "issues": [i.__dict__ for i in issues]})
            continue

        p = predict.predict_bin(b, r, now, model, ctx)
        status = predict.status_for(p)
        out.append({**base,
                    "fill_percent": p.fill_percent,
                    "fill_band": predict.fill_band(p.fill_percent),
                    "predicted_full_at": p.predicted_full_at.isoformat() if p.predicted_full_at else None,
                    "hours_until_full": p.hours_until_full,
                    "status": status, "fault": False,
                    "reason": predict.reason_for(p, status),
                    "issues": [i.__dict__ for i in issues]})

    learned = {"temp_effect_per_degree": round(model.temp_effect, 4),
               "weekend_factor_city": round(model.weekend, 2),
               "event_factor": {k: round(v, 2) for k, v in model.event_factor.items()}}
    return {"generated_at": now.isoformat(), "simulated": True, "model": learned, "bins": out}


def load_bins(path: Path) -> tuple[list[dict], dict | None]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data["bins"], data.get("depot")


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    ap = argparse.ArgumentParser()
    ap.add_argument("--bins", default=root / "data" / "bins_locations.json")
    ap.add_argument("--readings", default=root / "data" / "readings.csv")
    ap.add_argument("--out", default=root / "data" / "predictions.json")
    ap.add_argument("--now", default="2026-11-01T06:00:00")
    a = ap.parse_args()

    bins, depot = load_bins(a.bins)
    readings = pd.read_csv(a.readings)
    result = run(bins, readings, datetime.fromisoformat(a.now))
    result["depot"] = depot
    Path(a.out).write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")

    counts = pd.Series([b["status"] for b in result["bins"]]).value_counts().to_dict()
    print(f"{len(result['bins'])} bins -> {a.out}  {counts}")
    print(f"Learned: {result['model']}")


if __name__ == "__main__":
    main()
