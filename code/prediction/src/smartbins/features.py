"""Outside information for the forecast: day type, weather and events.

weather.csv : timestamp, temp_c       (history + forecast, hourly)
              later: real data from MeteoSwiss / Open-Meteo
events.json : [{"name", "type", "lat", "lon", "radius_m", "start", "end"}, ...]
              later: city event calendar, FCB fixtures, Messe Basel
"""
import json
import math
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]


def day_type(t) -> str:
    """'weekend' for Saturday/Sunday, else 'weekday'. (Holidays: add here later.)"""
    return "weekend" if t.weekday() >= 5 else "weekday"


def distance_m(lat1, lon1, lat2, lon2) -> float:
    return math.hypot((lat1 - lat2) * 111_000, (lon1 - lon2) * 75_000)


@dataclass
class Event:
    name: str
    type: str
    lat: float
    lon: float
    radius_m: float
    start: datetime
    end: datetime

    def affects(self, lat: float, lon: float, t) -> bool:
        return self.start <= t < self.end and distance_m(lat, lon, self.lat, self.lon) <= self.radius_m


@dataclass
class Context:
    weather: pd.Series = field(default_factory=pd.Series)   # temp_c indexed by hour
    events: list[Event] = field(default_factory=list)

    def temp(self, t, default: float = 10.0) -> float:
        if self.weather.empty:
            return default
        return float(self.weather.asof(pd.Timestamp(t).floor("h"))) if pd.Timestamp(t) >= self.weather.index[0] else default

    def events_at(self, lat: float, lon: float, t) -> list[Event]:
        return [e for e in self.events if e.affects(lat, lon, t)]


def load_context(weather_file: Path | None = None, events_file: Path | None = None) -> Context:
    weather_file = weather_file or ROOT / "data" / "weather.csv"
    events_file = events_file or ROOT / "data" / "events.json"
    weather = pd.Series(dtype=float)
    if weather_file.exists():
        w = pd.read_csv(weather_file, parse_dates=["timestamp"]).sort_values("timestamp")
        weather = w.set_index("timestamp")["temp_c"]
    events = []
    if events_file.exists():
        for e in json.loads(events_file.read_text(encoding="utf-8")):
            events.append(Event(e["name"], e["type"], e["lat"], e["lon"], e["radius_m"],
                                datetime.fromisoformat(e["start"]), datetime.fromisoformat(e["end"])))
    return Context(weather, events)
