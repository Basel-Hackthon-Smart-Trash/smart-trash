"""Fill-level prediction: when will each bin be full?

Model (multiplicative, explainable):

    fill speed (bin, time) = bin's normal speed at that hour
                             x weekend factor        (learned per bin, shrunk to city value)
                             x temperature factor    (learned for the whole city: % per °C)
                             x event factor          (learned per event type, e.g. football, fair)

"Normal speed" = a normal weekday at 10 °C without events.
The forecast starts from the current fill and adds the expected speed in
15-minute steps until 100 % -> predicted_full_at.
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from . import config, features

MAX_HORIZON_H = 72
REF_TEMP = 10.0
WEEKEND_SHRINK = 3.0            # days of "city opinion" mixed into each bin's own weekend factor
DEFAULT_EVENT_FACTOR = 1.5      # used for event types never seen before (assumption)


# ---------------------------------------------------------------- data preparation
def slices(readings: pd.DataFrame, max_gap_h: float = 6.0) -> pd.DataFrame:
    """Cut every step between two readings into pieces per clock hour.
    Returns start, end_of_step, hour, rate (% per hour), weight (hours)."""
    r = readings.sort_values("timestamp")
    t = r.timestamp.to_numpy()
    f = r.fill_percent.to_numpy(dtype=float)
    out = []
    for i in range(1, len(r)):
        dt_h = (t[i] - t[i - 1]) / np.timedelta64(1, "h")
        d = f[i] - f[i - 1]
        if dt_h <= 0 or dt_h > max_gap_h or d <= -config.EMPTY_DROP_POINTS or f[i] >= 99:
            continue
        rate = d / dt_h
        start = pd.Timestamp(t[i - 1])
        covered = 0.0
        while covered < dt_h - 1e-9:
            part = min(1 - (start.minute / 60 + start.second / 3600), dt_h - covered)
            out.append((start, pd.Timestamp(t[i]), start.hour, rate, part))
            covered += part
            start += pd.Timedelta(hours=part)
    return pd.DataFrame(out, columns=["start", "step_end", "hour", "rate", "weight"])


def hourly_rates(readings: pd.DataFrame) -> pd.Series:
    """Simple model (hour of day only). Kept as a baseline for evaluate.py."""
    s = slices(readings)
    if s.empty:
        return pd.Series(np.nan, index=range(24))
    g = s.assign(rw=s.rate * s.weight).groupby("hour")
    return (g.rw.sum() / g.weight.sum()).clip(lower=0).reindex(range(24))


# ---------------------------------------------------------------- learned model
@dataclass
class BinModel:
    profile: np.ndarray            # % per hour, normal weekday at 10 °C, no event (24 values)
    weekend: float


@dataclass
class CityModel:
    temp_effect: float = 0.0                                   # relative change per °C
    weekend: float = 1.0
    event_factor: dict = field(default_factory=dict)          # type -> factor
    bins: dict = field(default_factory=dict)                  # bin id -> BinModel
    city_profile: np.ndarray = field(default_factory=lambda: np.zeros(24))

    def temp_factor(self, temp: float) -> float:
        return max(0.5, 1 + self.temp_effect * (temp - REF_TEMP))

    def multiplier(self, b: dict, t, ctx: features.Context, weekend_f: float) -> tuple[float, str | None]:
        m = weekend_f if features.day_type(t) == "weekend" else 1.0
        m *= self.temp_factor(ctx.temp(t))
        ev = ctx.events_at(b["lat"], b["lon"], t)
        name = None
        if ev:
            e = max(ev, key=lambda e: self.event_factor.get(e.type, DEFAULT_EVENT_FACTOR))
            m *= self.event_factor.get(e.type, DEFAULT_EVENT_FACTOR)
            name = e.name
        return m, name


def fit(bins: list[dict], readings_by_bin: dict, ctx: features.Context, until=None) -> CityModel:
    """Learn the model from all healthy bins. 'until' = only use data before this time."""
    model = CityModel()
    loc = {b["id"]: b for b in bins}
    tab = {}
    hourly_temp = ctx.weather if not ctx.weather.empty else None
    for bid, r in readings_by_bin.items():
        s = r if "rate" in r.columns else slices(r)
        if until is not None:
            s = s[s.step_end <= until]
        if len(s) < 24 or bid not in loc:
            continue
        b = loc[bid]
        s = s.copy()
        s["weekend"] = (s.start.dt.weekday >= 5).to_numpy()
        if hourly_temp is not None:
            s["temp"] = hourly_temp.reindex(s.start.dt.floor("h")).fillna(REF_TEMP).to_numpy()
        else:
            s["temp"] = REF_TEMP
        ev = np.full(len(s), None, dtype=object)
        for e in ctx.events:
            if features.distance_m(b["lat"], b["lon"], e.lat, e.lon) <= e.radius_m:
                m = ((s.start >= e.start) & (s.start < e.end)).to_numpy()
                ev[m] = e.type
        s["event"] = ev
        tab[bid] = s
    if not tab:
        return model

    profiles = {}
    bin_weekend = {bid: 1.0 for bid in tab}
    for _ in range(3):                                           # alternate: profiles <-> effects
        # 1. each bin's normal profile, after removing the known effects
        for bid, s in tab.items():
            m = np.where(s.weekend, bin_weekend[bid], 1.0) * np.maximum(0.5, 1 + model.temp_effect * (s.temp - REF_TEMP))
            m = m * np.array([model.event_factor.get(e, 1.0) if e else 1.0 for e in s.event])
            rw = (s.rate / m) * s.weight
            g = pd.DataFrame({"h": s.hour, "rw": rw, "w": s.weight}).groupby("h").sum()
            prof = (g.rw / g.w).reindex(range(24))
            profiles[bid] = prof.clip(lower=0).to_numpy()
        city = np.nanmean(np.vstack(list(profiles.values())), axis=0)
        city = np.nan_to_num(city)
        for bid in profiles:
            profiles[bid] = np.where(np.isnan(profiles[bid]), city, profiles[bid])

        # 2. daily totals vs. expected -> weekend and temperature effect (event-free bin-days)
        rows = []
        for bid, s in tab.items():
            exp = profiles[bid][s.hour] * s.weight
            day = s.start.dt.normalize()
            d = pd.DataFrame({"day": day, "obs": s.rate * s.weight, "exp": exp, "w": s.weight,
                              "tw": s.temp * exp, "weekend": s.weekend, "ev": s.event.notna()}).groupby("day").agg(
                obs=("obs", "sum"), exp=("exp", "sum"), w=("w", "sum"), tw=("tw", "sum"),
                weekend=("weekend", "first"), ev=("ev", "any"))
            d = d[(d.w >= 12) & (~d.ev) & (d.exp > 1)]
            d["bid"] = bid
            rows.append(d)
        D = pd.concat(rows)
        D["ratio"] = D.obs / D.exp
        D["t"] = D.tw / D.exp - REF_TEMP
        X = np.column_stack([np.ones(len(D)), D.weekend.astype(float), D.t])
        W = np.sqrt(D.exp.to_numpy())
        coef, *_ = np.linalg.lstsq(X * W[:, None], D.ratio.to_numpy() * W, rcond=None)
        b0 = coef[0] if coef[0] > 0.2 else 1.0
        model.weekend = float(np.clip((coef[0] + coef[1]) / b0, 0.5, 3.0))
        model.temp_effect = float(np.clip(coef[2] / b0, -0.05, 0.15))

        # per-bin weekend factor, shrunk towards the city value
        for bid, d in D.groupby("bid"):
            adj = d.ratio / np.maximum(0.5, 1 + model.temp_effect * d.t)
            we, wd = adj[d.weekend], adj[~d.weekend]
            if len(we) and len(wd) and wd.mean() > 0:
                raw = we.mean() / wd.mean()
                bin_weekend[bid] = float((len(we) * raw + WEEKEND_SHRINK * model.weekend) / (len(we) + WEEKEND_SHRINK))
            else:
                bin_weekend[bid] = model.weekend

        # 3. event factors per type: observed / expected during events
        obs, exp = {}, {}
        for bid, s in tab.items():
            ev = s[s.event.notna()]
            if ev.empty:
                continue
            base = profiles[bid][ev.hour] * np.where(ev.weekend, bin_weekend[bid], 1.0) \
                * np.maximum(0.5, 1 + model.temp_effect * (ev.temp - REF_TEMP))
            for typ, grp in ev.assign(base=base).groupby("event"):
                obs[typ] = obs.get(typ, 0) + (grp.rate * grp.weight).sum()
                exp[typ] = exp.get(typ, 0) + (grp.base * grp.weight).sum()
        model.event_factor = {k: float(np.clip(obs[k] / exp[k], 1.0, 6.0)) for k in obs if exp[k] > 1}

    model.city_profile = city
    model.bins = {bid: BinModel(profiles[bid], bin_weekend[bid]) for bid in profiles}
    return model


# ---------------------------------------------------------------- forecast
@dataclass
class Prediction:
    fill_percent: float
    predicted_full_at: datetime | None   # None = not full within 72 h
    hours_until_full: float | None
    peak_hour: int
    drivers: list = field(default_factory=list)   # why it fills: event / weekend / warm


def predict_bin(b: dict, readings: pd.DataFrame, now: datetime, model: CityModel,
                ctx: features.Context) -> Prediction:
    r = readings.sort_values("timestamp")
    current = float(r.fill_percent.iloc[-1])
    bm = model.bins.get(b["id"], BinModel(model.city_profile, model.weekend))

    fill, t = current, now
    full_at, event_seen, weekend_seen, max_temp = None, None, False, -99.0
    for _ in range(MAX_HORIZON_H * 4):
        if fill >= 100:
            full_at = t
            break
        m, ev = model.multiplier(b, t, ctx, bm.weekend)
        event_seen = event_seen or ev
        weekend_seen = weekend_seen or features.day_type(t) == "weekend"
        max_temp = max(max_temp, ctx.temp(t))
        fill += bm.profile[t.hour] * m * 0.25
        t += timedelta(minutes=15)

    if current >= 100:
        full_at = now
    hours = None if full_at is None else round((full_at - now).total_seconds() / 3600, 1)
    drivers = []
    if event_seen:
        drivers.append(event_seen)
    if weekend_seen and bm.weekend > 1.1:
        drivers.append("weekend")
    if max_temp >= 15 and model.temp_effect > 0.01:
        drivers.append(f"warm ({max_temp:.0f} °C)")
    return Prediction(round(current, 1), full_at, hours, int(np.argmax(bm.profile)), drivers)


def forecast_fill(b: dict, current: float, now: datetime, model: CityModel,
                  ctx: features.Context, hours: int) -> dict:
    """Expected fill level after 1..hours hours (for evaluate.py)."""
    bm = model.bins.get(b["id"], BinModel(model.city_profile, model.weekend))
    fill, t, out = current, now, {}
    for step in range(1, hours * 4 + 1):
        m, _ = model.multiplier(b, t, ctx, bm.weekend)
        fill = min(100.0, fill + bm.profile[t.hour] * m * 0.25)
        t += timedelta(minutes=15)
        if step % 4 == 0:
            out[step // 4] = fill
    return out


def status_for(p: Prediction) -> str:
    h = p.hours_until_full
    if p.fill_percent >= config.RED_FILL or (h is not None and h <= config.RED_FULL_WITHIN_H):
        return "red"
    orange_soon = (config.ORANGE_FULL_WITHIN_H is not None and h is not None
                   and h <= config.ORANGE_FULL_WITHIN_H)
    if p.fill_percent >= config.ORANGE_FILL or orange_soon:
        return "orange"
    return "green"


def reason_for(p: Prediction, status: str) -> str:
    why = f" ({', '.join(p.drivers)})" if p.drivers else ""
    if status == "red":
        if p.fill_percent >= config.RED_FILL:
            return f"{p.fill_percent:.0f} % full now"
        return f"Full by {p.predicted_full_at:%a %H:%M}, before the next tour{why}"
    if status == "orange":
        return f"{p.fill_percent:.0f} % full, emptied while the truck is in the area"
    return "Not full before the next tour"
