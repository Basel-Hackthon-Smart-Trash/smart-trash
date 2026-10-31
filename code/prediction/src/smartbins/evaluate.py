"""How accurate is the prediction? Backtest on the sensor readings.

At many cut-off times the models only see data BEFORE the cut-off and predict
the fill level 3, 6, 12 and 24 h ahead; then we compare with what really happened.
Periods after an emptying are skipped (the model can't know when the crew comes).

Compared:
  - full model:   hour of day + weekend + temperature + events (learned)
  - hour only:    the earlier model (hour of day only)
  - last trend:   speed of the last 6 h continues
  - no change:    fill level stays as it is

    uv run python -m smartbins.evaluate
    uv run python -m smartbins.evaluate --every-h 3 --fresh
Note: the weather "forecast" here is the real temperature (perfect forecast, optimistic).
"""
import argparse
import json
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from . import config, faults, features, predict

ROOT = Path(__file__).resolve().parents[2]
HORIZONS_H = [3, 6, 12, 24]


def path_simple(rates: pd.Series, start_fill: float, start, hours: int) -> dict:
    fill, t, out = start_fill, start, {}
    for step in range(1, hours * 4 + 1):
        fill = min(100.0, fill + rates[t.hour] * 0.25)
        t += timedelta(minutes=15)
        if step % 4 == 0:
            out[step // 4] = fill
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--every-h", type=float, default=0, help="only keep one reading every N hours")
    ap.add_argument("--fresh", action="store_true", help="plus one fresh reading right before the cut-off")
    a = ap.parse_args()

    bins = json.loads((ROOT / "data" / "bins_locations.json").read_text(encoding="utf-8"))["bins"]
    loc = {b["id"]: b for b in bins}
    ctx = features.load_context()
    full = pd.read_csv(ROOT / "data" / "readings.csv", parse_dates=["timestamp"])
    end = full.timestamp.max()
    faulty = {sid for sid, g in full.groupby("sensor_id") if faults.has_fault(faults.check_sensor(g, end))}
    r = full
    if a.every_h:
        step = pd.Timedelta(hours=a.every_h)
        r = r[((r.timestamp - r.timestamp.min()) % step) == pd.Timedelta(0)]
        print(f"Using one reading every {a.every_h:g} h" + (" + fresh reading before planning" if a.fresh else ""))

    full_by = {sid: g.sort_values("timestamp").set_index("timestamp") for sid, g in full.groupby("sensor_id")}
    seen_by = {sid: g.sort_values("timestamp") for sid, g in r.groupby("sensor_id") if sid not in faulty}
    if a.fresh:
        pass  # added per cut-off below
    slices_by = {sid: predict.slices(g) for sid, g in seen_by.items()}      # computed once
    cuts = pd.date_range(end - timedelta(days=6), end - timedelta(hours=24), freq="12h").floor("4h").unique()

    rows = []
    for cut in cuts:
        hist_by = {}
        for sid, g in seen_by.items():
            h = g[g.timestamp <= cut]
            if a.fresh and cut in full_by[sid].index and (h.empty or h.timestamp.iloc[-1] != cut):
                h = pd.concat([h, full_by[sid].loc[[cut]].reset_index()])
            if not h.empty and h.timestamp.max() - h.timestamp.min() >= timedelta(hours=48):
                hist_by[sid] = h
        cut_slices = {sid: slices_by[sid][slices_by[sid].step_end <= cut] for sid in hist_by}
        model = predict.fit(bins, cut_slices, ctx)
        for sid, hist in hist_by.items():
            now_fill = float(hist.fill_percent.iloc[-1])
            p_full = predict.forecast_fill(loc[sid], now_fill, cut, model, ctx, max(HORIZONS_H))
            cs = cut_slices[sid]
            g = cs.assign(rw=cs.rate * cs.weight).groupby("hour")
            hour_rates = (g.rw.sum() / g.weight.sum()).clip(lower=0).reindex(range(24)).fillna(0)
            p_hour = path_simple(hour_rates, now_fill, cut, max(HORIZONS_H))
            recent = hist[hist.timestamp >= cut - timedelta(hours=max(6, 2 * (a.every_h or 0.5)))]
            span = (recent.timestamp.iloc[-1] - recent.timestamp.iloc[0]).total_seconds() / 3600 if len(recent) > 1 else 0
            trend = max(0.0, (recent.fill_percent.iloc[-1] - recent.fill_percent.iloc[0]) / span) if span else 0.0

            fg = full_by[sid]
            future = fg[(fg.index > cut) & (fg.index <= cut + timedelta(hours=max(HORIZONS_H)))]
            drops = future.fill_percent.diff() <= -config.EMPTY_DROP_POINTS
            emptied_at = future.index[drops.values][0] if drops.any() else None
            for h in HORIZONS_H:
                t = cut + timedelta(hours=h)
                if emptied_at is not None and emptied_at <= t:
                    break
                rows.append(dict(sensor=sid, horizon_h=h, actual=fg.fill_percent.asof(t),
                                 full_model=p_full[h], hour_only=p_hour[h],
                                 last_trend=min(100.0, now_fill + trend * h), no_change=now_fill))
        print(f"  cut-off {cut:%a %d.%m %H:%M}: model learned temp {model.temp_effect:+.3f}/°C, "
              f"weekend x{model.weekend:.2f}, events {({k: round(v, 1) for k, v in model.event_factor.items()})}")

    df = pd.DataFrame(rows)
    print(f"\n{len(df)} forecasts checked ({df.sensor.nunique()} healthy sensors)")
    print("Average error in percentage points (lower = better):")
    cols = ["full_model", "hour_only", "last_trend", "no_change"]
    res = df.groupby("horizon_h")[cols].apply(lambda x: (x.sub(df.loc[x.index, "actual"], axis=0)).abs().mean())
    res["forecasts"] = df.groupby("horizon_h").size()
    print(res.round(1).to_string())

    d24 = df[df.horizon_h == 24]
    for c in ["full_model", "hour_only"]:
        pred, real = d24[c] >= config.RED_FILL, d24.actual >= config.RED_FILL
        print(f"'Full within 24 h?' {c:10}: correct {(pred == real).mean() * 100:.0f} %, "
              f"missed {(~pred & real).sum()}, false alarms {(pred & ~real).sum()}")
    df.to_csv(ROOT / "data" / "evaluation.csv", index=False)


if __name__ == "__main__":
    main()
