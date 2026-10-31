"""Compare zone strategies on many simulated days.

    uv run python -m smartbins.zone_test --streets real       # needs data/street_matrix.npz
    uv run python -m smartbins.zone_test --streets straight   # no internet needed

Strategies (only RED bins are emptied):
  baseline : old fixed schedule, every bin every 2nd day, 5 fixed zones
  fixed    : 5 fixed location zones, each empties its red bins
  fill     : fill-based zone, split by location into ceil(red / capacity) areas
"""
import argparse
import json
import math

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans

from . import config, streets

SCENARIOS = {"quiet": 0.6, "normal": 1.0, "busy weekend": 1.5, "event": 1.0}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--streets", choices=["real", "straight"], default="real")
    ap.add_argument("--days", type=int, default=50, help="days per scenario")
    ap.add_argument("--capacity", type=int, default=40, help="bins per truck tour (assumption)")
    a = ap.parse_args()

    data = json.loads((streets.ROOT / "data" / "bins_locations.json").read_text(encoding="utf-8"))
    B = data["bins"]
    n = len(B)
    M = streets.load_matrix() if a.streets == "real" else streets.straight_line_matrix()
    if not np.isfinite(M).all():
        bad = np.where(~np.isfinite(M).all(axis=0) | ~np.isfinite(M).all(axis=1))[0]
        print(f"Warning: {len(bad)} points unreachable by car, they are skipped")
    ok = np.isfinite(M).all(axis=0) & np.isfinite(M).all(axis=1)

    XY = np.array([[b["lat"] * 111, b["lon"] * 75] for b in B])
    busy = np.array([b["busyness"] for b in B])
    zone = np.array([b["zone"] for b in B])
    reachable = np.where(ok[1:])[0]                 # bin indices (0-based) reachable by car
    rng = np.random.default_rng(1)

    def tours(idx):                                  # idx: 0-based bin indices
        return streets.tour_length(M, [int(i) + 1 for i in idx])

    def split(idx, k):
        if k <= 1 or len(idx) <= 1:
            return [idx]
        lab = KMeans(n_clusters=k, n_init=5, random_state=0).fit(XY[idx]).labels_
        return [idx[lab == c] for c in range(k)]

    rows = []
    for name, f in SCENARIOS.items():
        for s in range(a.days):
            daily = (8 + 50 * busy) * rng.uniform(0.7, 1.3, n) * f
            if name == "event":
                c = XY[rng.choice(np.argsort(busy)[-40:])]
                daily = np.where(np.hypot(*(XY - c).T) < 0.6, daily * 3, daily)
            fill = np.minimum(100, daily * rng.uniform(6, 48, n) / 24)
            h_full = (100 - fill) / (daily / 14)
            red = (fill >= config.RED_FILL) | (h_full <= config.RED_FULL_WITHIN_H)
            r = np.intersect1d(np.where(red)[0], reachable)

            fixed_km, fixed_trucks = 0.0, 0
            for z in sorted(set(zone)):
                ri = r[zone[r] == z]
                k = math.ceil(len(ri) / a.capacity) if len(ri) else 0
                fixed_km += sum(tours(p) for p in split(ri, k)) if k else 0
                fixed_trucks += k

            k = max(1, math.ceil(len(r) / a.capacity))
            fill_km = sum(tours(p) for p in split(r, k)) if len(r) else 0.0

            half = np.intersect1d(np.where((np.arange(n) + s) % 2 == 0)[0], reachable)
            base_km, base_trucks = 0.0, 0
            for z in sorted(set(zone)):
                zi = half[zone[half] == z]
                kk = max(1, math.ceil(len(zi) / a.capacity))
                base_km += sum(tours(p) for p in split(zi, kk))
                base_trucks += kk
            missed = int(((fill >= 100) & ~np.isin(np.arange(n), half)).sum())

            rows.append(dict(scenario=name, red=len(r), baseline_km=base_km, fixed_km=fixed_km,
                             fill_km=fill_km, trucks_baseline=base_trucks, trucks_fixed=fixed_trucks,
                             trucks_fill=k if len(r) else 0, full_but_not_scheduled=missed))
        print(f"  {name}: done")

    df = pd.DataFrame(rows)
    out = streets.ROOT / "data" / f"zone_test_{a.streets}.csv"
    df.to_csv(out, index=False)
    summary = df.groupby("scenario", sort=False).median(numeric_only=True).round(1)
    print(f"\nMedian per scenario ({a.streets} distances, {a.days} days each, capacity {a.capacity}):")
    print(summary.to_string())
    better = (df.fill_km < df.fixed_km - 0.01).mean() * 100
    worse = (df.fill_km > df.fixed_km + 0.01).mean() * 100
    print(f"\nFill zones better than fixed zones: {better:.0f} % of days, worse: {worse:.0f} %")
    print(f"Saving vs fixed zones (median): {((df.fixed_km - df.fill_km) / df.fixed_km.clip(lower=1e-9)).median() * 100:.0f} %")
    print(f"Saving vs old schedule (median): {((df.baseline_km - df.fill_km) / df.baseline_km).median() * 100:.0f} %")
    print(f"Saved -> {out}")


if __name__ == "__main__":
    main()
