"""Run the whole chain once (e.g. every morning):

readings -> fault detection + prediction -> routes -> data/bins.json (for the website)

uv run python -m smartbins.run_daily
uv run python -m smartbins.run_daily --now 2026-11-01T06:00:00
"""

import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

import pandas as pd

from . import config, pipeline, routing

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--now", default="2026-11-01T06:00:00")
    ap.add_argument("--out", default=ROOT / "data" / "bins.json")
    a = ap.parse_args()
    now = datetime.fromisoformat(a.now)

    # 1. Inputs (from the backend later)
    bins, depot = pipeline.load_bins(ROOT / "data" / "bins_locations.json")
    readings = pd.read_csv(ROOT / "data" / "readings.csv")

    # 2. Fault detection + prediction
    result = pipeline.run(bins, readings, now)
    result["depot"] = depot

    # 3. Which bins to empty today
    take = {"red", "orange"} if config.TAKE_ORANGE else {"red"}
    to_empty = [
        b
        for b in result["bins"]
        if b["status"] in take and b.get("fill_band") != "green"
    ]

    # 4. Routes (placeholder until the routing algorithm is merged)
    result["routes"], kind = routing.plan_routes(to_empty, bins, now, depot)
    truck_of = {sid: r["zone"] for r in result["routes"] for sid in r["stops"]}
    for b in result["bins"]:
        b.pop("issues", None)  # the website doesn't need the details
        b["zone"] = truck_of.get(b["id"], 0)  # 0 = not emptied today
    result["note"] = (
        f"Bin locations: OpenStreetMap. Fill levels: simulated. "
        f"Routes: team routing package (OR-Tools) on {kind}."
    )

    Path(a.out).write_text(
        json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8"
    )

    counts = Counter(b["status"] for b in result["bins"])
    km = sum(r["distance_km"] for r in result["routes"])
    print(f"Learned: {result['model']}")
    print(f"Status: {dict(counts)}")
    print(
        f"Emptied today: {len(to_empty)} bins, {len(result['routes'])} trucks, {km:.1f} km ({kind})"
    )
    for r in result["routes"]:
        ok = "ok" if r["within_limits"] else "OVER LIMIT"
        print(
            f"  Truck {r['zone']}: {len(r['stops'])} bins, {r['distance_km']} km, {r['duration_h']} h, "
            f"{r['load_l']} L, {r['on_foot_stops']} on foot  [{ok}, routing: {r['status']}]"
        )
    print(f"Saved -> {a.out}  (copy it to the website's data folder)")


if __name__ == "__main__":
    main()
