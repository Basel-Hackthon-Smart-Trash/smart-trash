"""Create realistic fake data until real sensors exist.

Writes:
  data/readings.csv  sensor_id, timestamp, fill_percent, battery_percent  (what the backend delivers)
  data/weather.csv   timestamp, temp_c   (history + 3-day forecast)
  data/events.json   example events (dates are EXAMPLES, check the real calendar)

The fake bins react to weekday, temperature and events, so the model can learn it.
"""
import json
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from . import config, features

ROOT = Path(__file__).resolve().parents[2]

# Share of daily waste per hour of the day (low at night, peaks at lunch and evening)
HOURLY_PROFILE = np.array([
    0.2, 0.1, 0.1, 0.1, 0.1, 0.2, 0.5, 0.8, 1.0, 1.1, 1.3, 1.6,
    1.9, 1.7, 1.4, 1.3, 1.4, 1.7, 1.9, 1.6, 1.2, 0.9, 0.6, 0.4,
])
HOURLY_PROFILE = HOURLY_PROFILE / HOURLY_PROFILE.sum()

# "True" effects hidden in the fake data (the model must find them on its own)
TRUE_TEMP_EFFECT = 0.04            # +4 % waste per degree above 10 °C
TRUE_EVENT_FACTOR = {"football": 3.0, "fair": 2.0}


def example_events(now: datetime) -> list[dict]:
    """EXAMPLE events around 'now'. Replace with the real Basel calendar."""
    d = now.replace(hour=0, minute=0)
    ev = []
    # Football at St. Jakob-Park: two past home matches, one tomorrow evening
    for days, h in [(-8, 18), (-4, 19), (1, 16)]:
        s = d + timedelta(days=days, hours=h)
        ev.append({"name": "FCB home match", "type": "football", "lat": 47.5416, "lon": 7.6203,
                   "radius_m": 900, "start": s.isoformat(), "end": (s + timedelta(hours=5)).isoformat()})
    # Autumn fair on Messeplatz and Petersplatz: started 7 days ago, runs 11:00-22:00 daily
    for name, lat, lon in [("Herbstmesse Messeplatz", 47.5635, 7.6000),
                           ("Herbstmesse Petersplatz", 47.5605, 7.5815)]:
        for days in range(-7, 4):
            s = d + timedelta(days=days, hours=11)
            ev.append({"name": name, "type": "fair", "lat": lat, "lon": lon, "radius_m": 450,
                       "start": s.isoformat(), "end": (s + timedelta(hours=11)).isoformat()})
    return ev


def simulate_weather(start: datetime, end: datetime, rng) -> pd.DataFrame:
    hours = pd.date_range(start, end, freq="h", inclusive="left")
    days = sorted({h.normalize() for h in hours})
    daily = 9 + np.cumsum(rng.normal(0, 1.6, len(days)))                     # random walk around 9 °C
    daily = np.clip(daily, 0, 20)
    by_day = dict(zip(days, daily))
    temp = [by_day[h.normalize()] + 4 * np.sin((h.hour - 9) / 24 * 2 * np.pi) for h in hours]
    return pd.DataFrame({"timestamp": hours, "temp_c": np.round(temp, 1)})


def simulate(bins: list[dict], end: datetime, days: int = 14, seed: int = 42):
    rng = np.random.default_rng(seed)
    step = timedelta(minutes=config.READING_INTERVAL_MIN)
    start = end - timedelta(days=days)
    times = pd.date_range(start, end, freq=step, inclusive="left")

    weather = simulate_weather(start, end + timedelta(days=3), rng)
    events_raw = example_events(end)
    ctx = features.Context(weather.set_index("timestamp")["temp_c"],
                           features.load_context(Path("/nonexistent"), Path("/nonexistent")).events)
    ctx.events = [features.Event(e["name"], e["type"], e["lat"], e["lon"], e["radius_m"],
                                 datetime.fromisoformat(e["start"]), datetime.fromisoformat(e["end"]))
                  for e in events_raw]
    temp_at = {t: ctx.temp(t) for t in times}

    rows = []
    for i, b in enumerate(bins):
        busy = b.get("busyness", 0.5)
        daily = (8 + 50 * busy) * rng.uniform(0.7, 1.3)                   # % per normal weekday at 10 °C
        weekend = 1 + 0.5 * busy * rng.uniform(0.6, 1.4)                  # busier bins: bigger weekend effect
        fill = rng.uniform(5, 40)
        battery = rng.uniform(40, 100)
        fault = "none"
        if i % 60 == 4:
            fault = "stuck"
        elif i % 60 == 24:
            fault = "jump_freeze"
        elif i % 60 == 44:
            fault = "offline"
        near_events = [e for e in ctx.events if features.distance_m(b["lat"], b["lon"], e.lat, e.lon) <= e.radius_m]

        frozen_value = None
        for t in times:
            f = HOURLY_PROFILE[t.hour] * 24 / 24                              # share of the day per hour
            mult = (weekend if t.weekday() >= 5 else 1.0)
            mult *= max(0.5, 1 + TRUE_TEMP_EFFECT * (temp_at[t] - 10))
            for e in near_events:
                if e.start <= t < e.end:
                    mult *= TRUE_EVENT_FACTOR[e.type]
                    break
            fill += daily * f * mult * (step / timedelta(hours=1))
            fill += rng.normal(0, 0.6)
            fill = min(fill, 100)
            # Fixed schedule today: crew empties at 07:00 every 2nd day
            if t.hour == 7 and t.minute == 0 and t.dayofyear % 2 == 0:
                fill = rng.uniform(0, 5)
            battery -= 0.002

            value = fill
            if fault == "stuck" and t >= end - timedelta(hours=24):
                frozen_value = frozen_value if frozen_value is not None else round(fill, 1)
                value = frozen_value
            if fault == "jump_freeze" and t >= end - timedelta(hours=14):
                frozen_value = frozen_value if frozen_value is not None else min(fill + 55, 100)
                value = frozen_value
            if fault == "offline" and t >= end - timedelta(hours=10):
                continue
            rows.append({"sensor_id": b["id"], "timestamp": t,
                         "fill_percent": round(float(np.clip(value, 0, 100)), 1),
                         "battery_percent": round(battery, 1)})
    return pd.DataFrame(rows), weather, events_raw


if __name__ == "__main__":
    bins = json.loads((ROOT / "data" / "bins_locations.json").read_text(encoding="utf-8"))["bins"]
    now = datetime(2026, 11, 1, 6, 0)
    readings, weather, events = simulate(bins, end=now)
    readings.to_csv(ROOT / "data" / "readings.csv", index=False)
    weather.to_csv(ROOT / "data" / "weather.csv", index=False)
    (ROOT / "data" / "events.json").write_text(json.dumps(events, indent=1), encoding="utf-8")
    print(f"{len(readings)} readings for {readings.sensor_id.nunique()} sensors, "
          f"{len(weather)} weather hours, {len(events)} events -> data/")
