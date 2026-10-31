"""Compare collection rules over many days in a row.

Each morning: decide which bins to empty -> plan routes -> empty them.
During the day: bins fill up. A bin that reaches 100 % before the next
morning counts as an overflow.

    uv run python -m smartbins.policy_test --streets real
    uv run python -m smartbins.policy_test --streets straight
"""
import argparse
import json
import math

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans

from . import streets

BUSY_HOURS = 14   # waste mostly comes in during ~14 hours per day

# name: (red fill %, red if full within h (busy hours), orange fill %, take orange?)
POLICIES = {
    "A  red>=80 or full<10h (current)":            (80, 10, None, False),
    "B  red>=90, orange 70-90, take both":         (90, None, 70, True),
    "C  red>=90 or full<12h, orange 70-90, both":  (90, 12, 70, True),
    "D  red>=90 or full<14h, orange 70-90, both":  (90, 14, 70, True),
    "E  red>=90 or full<16h, orange 70-90, both":  (90, 16, 70, True),
    "F  old schedule (every 2nd day)":             (None, None, None, False),
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--streets", choices=["real", "straight"], default="real")
    ap.add_argument("--days", type=int, default=60)
    ap.add_argument("--runs", type=int, default=5, help="repeat with different random days")
    ap.add_argument("--capacity", type=int, default=40)
    a = ap.parse_args()

    data = json.loads((streets.ROOT / "data" / "bins_locations.json").read_text(encoding="utf-8"))
    B = data["bins"]
    n = len(B)
    M = streets.load_matrix() if a.streets == "real" else streets.straight_line_matrix()
    XY = np.array([[b["lat"] * 111, b["lon"] * 75] for b in B])
    busy = np.array([b["busyness"] for b in B])

    def plan_km(idx):
        if len(idx) == 0:
            return 0.0, 0
        k = math.ceil(len(idx) / a.capacity)
        parts = [idx] if k == 1 else [idx[l == c] for l in [KMeans(k, n_init=5, random_state=0).fit(XY[idx]).labels_] for c in range(k)]
        return sum(streets.tour_length(M, [int(i) + 1 for i in p]) for p in parts), k

    rows = []
    for run in range(a.runs):
        rng = np.random.default_rng(100 + run)
        base_rate = (8 + 50 * busy) * rng.uniform(0.7, 1.3, n)          # % per day
        # the same sequence of days for every policy (fair comparison)
        day_factor = rng.choice([0.6, 1.0, 1.0, 1.0, 1.5], size=a.days)  # quiet/normal/busy mix
        event_day = rng.random(a.days) < 0.1
        event_center = XY[rng.choice(np.argsort(busy)[-40:], size=a.days)]
        noise = rng.uniform(0.85, 1.15, (a.days, n))
        start_fill = rng.uniform(0, 60, n)

        for name, (red_fill, red_h, orange_fill, take_orange) in POLICIES.items():
            fill = start_fill.copy()
            for d in range(a.days):
                rate = base_rate * day_factor[d] * noise[d]
                if event_day[d]:
                    rate = np.where(np.hypot(*(XY - event_center[d]).T) < 0.6, rate * 3, rate)
                expected = base_rate * day_factor[d]                       # what the forecast knows

                # 1. Morning decision
                if red_fill is None:                                        # old schedule
                    pick = np.where((np.arange(n) + d) % 2 == 0)[0]
                else:
                    h_full = (100 - fill) / (expected / BUSY_HOURS)
                    red = fill >= red_fill
                    if red_h is not None:
                        red |= h_full <= red_h
                    take = red.copy()
                    if take_orange:
                        take |= fill >= orange_fill
                    pick = np.where(take)[0]

                km, trucks = plan_km(pick)
                emptied_fill = fill[pick]
                fill[pick] = 0.0

                # 2. Bins fill up during the day
                fill = fill + rate
                overflow = int((fill >= 100).sum())
                # bins that overflow even right after emptying: need 2 visits per day, no rule can fix that
                unavoidable = int((rate >= 100).sum())
                fill = np.minimum(fill, 100)

                rows.append(dict(policy=name, run=run, day=d, km=km, trucks=trucks,
                                 emptied=len(pick), overflow=overflow, avoidable_overflow=overflow - unavoidable,
                                 avg_fill_emptied=float(emptied_fill.mean()) if len(pick) else np.nan,
                                 early=int((emptied_fill < 50).sum())))
        print(f"  run {run + 1}/{a.runs} done")

    df = pd.DataFrame(rows)
    out = streets.ROOT / "data" / f"policy_test_{a.streets}.csv"
    df.to_csv(out, index=False)
    s = df.groupby("policy").agg(km_per_day=("km", "mean"), trucks=("trucks", "mean"),
                                 bins_emptied=("emptied", "mean"),
                                 avg_fill_when_emptied=("avg_fill_emptied", "mean"),
                                 emptied_below_50=("early", "mean"),
                                 overflows_per_day=("overflow", "mean"),
                                 avoidable_overflows=("avoidable_overflow", "mean"))
    print(f"\nAverage per day ({a.streets} distances, {a.runs} x {a.days} days, capacity {a.capacity}):")
    print(s.round(1).to_string())
    print(f"Saved -> {out}")


if __name__ == "__main__":
    main()
