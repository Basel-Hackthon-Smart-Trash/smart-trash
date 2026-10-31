"""Routing: truck limits (this package) + route optimisation (team package smart_bin_routing).

Division of work, without changing the team's routing logic:
  1. smartbins (prediction) decides WHICH bins are emptied today (rule in config.py).
     Those bins get a CollectionDemand; all other bins get none, so the routing
     package excludes them with the diagnostic "missing_collection_demand".
  2. This module splits the selected bins into truck tours so that every tour keeps
     the load and shift-time limits (config.py, assumptions).
  3. For each tour, smart_bin_routing.plan_collection() validates the input and finds
     the stop order with OR-Tools (one truck, one trip), unchanged.

Output format (read by the website):
    [{"zone": 1, "stops": [...], "distance_km": 6.4, "duration_h": 3.1, "load_l": 4200,
      "on_foot_stops": 3, "within_limits": true, "status": "feasible", "diagnostics": [...]}, ...]
"""
import math
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
from sklearn.cluster import KMeans
from smart_bin_routing import (
    BinMetadata,
    CollectionDemand,
    CollectionPlanRequest,
    DemandPolicy,
    FillObservation,
    GeoLocation,
    PlanningConfig,
    PlanningSnapshot,
    SolverConfig,
    plan_collection,
)
from smart_bin_routing.contracts import TravelCostMatrix

from . import config, streets

MORNING_EXTRA_POINTS = 15     # bins keep filling until the truck arrives (assumption)
TZ = ZoneInfo(config.TIMEZONE)


def _aware(ts: str | datetime) -> datetime:
    t = datetime.fromisoformat(ts) if isinstance(ts, str) else ts
    return t if t.tzinfo else t.replace(tzinfo=TZ)


def _load_l(b: dict) -> float:
    fill = b.get("fill_percent") or 100.0       # unknown -> assume full
    return b.get("volume_l", config.BIN_VOLUME_L) * min(100.0, fill + MORNING_EXTRA_POINTS) / 100


def _planning_config() -> PlanningConfig:
    return PlanningConfig(
        start_node_id=config.DEPOT_NODE_ID,
        end_node_id=config.DEPOT_NODE_ID,
        truck_capacity=config.TRUCK_CAPACITY_L,
        demand_unit="L",
        yellow_threshold=config.ORANGE_FILL / 100,
        red_threshold=config.RED_FILL / 100,
        observation_max_age_seconds=config.NO_DATA_HOURS * 3600,
        demand_policy=DemandPolicy.ALLOW_MARKED_ESTIMATES,   # our litres are estimates, marked as such
    )


def _solve_tour(group: list[dict], M: np.ndarray, snap_m: np.ndarray, index: dict, now: datetime) -> dict:
    """One truck tour: build the team package's inputs, call plan_collection, translate back."""
    ids = [config.DEPOT_NODE_ID] + [b["id"] for b in group]
    mi = [0] + [index[b["id"]] for b in group]
    dist = tuple(tuple(float(M[i, j]) if np.isfinite(M[i, j]) else None for j in mi) for i in mi)
    snapshot = PlanningSnapshot(
        bins=tuple(BinMetadata(b["id"], source_id=b.get("osm_id"), location=GeoLocation(b["lon"], b["lat"]))
                   for b in group),
        observations=tuple(FillObservation(b["id"], min(1.0, max(0.0, b["fill_percent"] / 100)),
                                           _aware(b["observed_at"]))
                           for b in group if b.get("fill_percent") is not None and b.get("observed_at")),
        demands=tuple(CollectionDemand(b["id"], round(_load_l(b), 1), "L", estimated=True) for b in group),
    )
    request = CollectionPlanRequest(
        snapshot=snapshot,
        config=_planning_config(),
        planning_time=_aware(now),
        travel_costs=TravelCostMatrix(tuple(ids), distances=dist, distance_unit="km"),
        solver_config=SolverConfig(time_limit_seconds=config.ROUTING_TIME_LIMIT_S),
    )
    result = plan_collection(request)
    sr = result.solver_result
    stops = list(result.stops)
    km = float(sr.travel_distance) if sr and sr.travel_distance is not None else math.nan
    on_foot = sum(1 for b in group if snap_m[index[b["id"]]] > streets.ON_FOOT_M)
    walk_km = sum(2 * snap_m[index[b["id"]]] / 1000 for b in group if snap_m[index[b["id"]]] > streets.ON_FOOT_M)
    hours = (km / config.AVG_SPEED_KMH if not math.isnan(km) else math.nan) \
        + len(group) * config.SERVICE_MIN_PER_BIN / 60 + walk_km / config.WALK_SPEED_KMH
    excluded = [a.bin_id for a in result.bins if not a.included_in_route]
    return {"stops": stops, "distance_km": round(km, 1) if not math.isnan(km) else None,
            "duration_h": round(hours, 2) if not math.isnan(hours) else None,
            "load_l": round(sum(_load_l(b) for b in group)), "on_foot_stops": on_foot,
            "status": result.status.value, "excluded": excluded,
            "diagnostics": sorted({d.code for d in result.diagnostics})}


def plan_routes(to_empty: list[dict], all_bins: list[dict], now: datetime | None = None) -> tuple[list[dict], str]:
    M, kind = streets.get_matrix()
    snap_m = streets.get_snap_m(len(all_bins) + 1)
    index = {b["id"]: i + 1 for i, b in enumerate(all_bins)}      # matrix index (0 = depot)
    if not to_empty:
        return [], kind
    now = now or datetime.now(TZ)

    total_load = sum(_load_l(b) for b in to_empty)
    service_h = len(to_empty) * config.SERVICE_MIN_PER_BIN / 60
    k = max(1, math.ceil(total_load / config.TRUCK_CAPACITY_L), math.ceil(service_h / config.SHIFT_HOURS))
    XY = np.array([[b["lat"] * 111, b["lon"] * 75] for b in to_empty])

    while True:
        labels = np.zeros(len(to_empty), dtype=int) if k == 1 else \
            KMeans(n_clusters=min(k, len(to_empty)), n_init=5, random_state=0).fit(XY).labels_
        routes = []
        for area in sorted(set(labels)):
            group = [b for b, l in zip(to_empty, labels) if l == area]
            r = _solve_tour(group, M, snap_m, index, now)
            r["within_limits"] = (r["status"] == "feasible" and r["load_l"] <= config.TRUCK_CAPACITY_L
                                  and r["duration_h"] is not None and r["duration_h"] <= config.SHIFT_HOURS)
            routes.append(r)
        if all(r["within_limits"] for r in routes) or k >= min(config.MAX_TRUCKS, len(to_empty)):
            break
        k += 1

    if not all(r["within_limits"] for r in routes):
        print(f"WARNING: even {k} trucks can't keep all limits. Check TRUCK_CAPACITY_L / SHIFT_HOURS / MAX_TRUCKS.")
    return [{"zone": i, **r} for i, r in enumerate(routes, 1)], kind
