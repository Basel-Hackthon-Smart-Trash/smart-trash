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
      "driving_duration_h": 1.2, "service_duration_h": 1.8, "walking_duration_h": 0.1,
      "on_foot_stops": 3, "within_limits": true, "status": "feasible", "diagnostics": [...]}, ...]
"""

import json
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
from smart_bin_routing import (
    BinMetadata,
    CollectionDemand,
    CollectionPlanRequest,
    DemandPolicy,
    FillObservation,
    GeoLocation,
    GraphArtifact,
    MatchingConfig,
    PlanningConfig,
    PlanningSnapshot,
    RoadCostMetric,
    RoadLocation,
    SolverConfig,
    UnusableMatchPolicy,
    build_road_costs,
    build_route_geometry,
    load_graph,
    plan_collection,
)
from smart_bin_routing.adapters.road_costs import RoadCostResult
from smart_bin_routing.contracts import TravelCostMatrix

from . import config, streets

MORNING_EXTRA_POINTS = 15  # bins keep filling until the truck arrives (assumption)
TZ = ZoneInfo(config.TIMEZONE)
GRAPH_DIR = (
    Path(__file__).resolve().parents[3] / "routing" / ".cache" / "real-bin-demo-graph"
)
ROAD_MATCH_MAX_M = 1000.0


@dataclass(frozen=True)
class RoadContext:
    artifact: GraphArtifact
    costs: RoadCostResult
    snap_m: np.ndarray


def _aware(ts: str | datetime) -> datetime:
    t = datetime.fromisoformat(ts) if isinstance(ts, str) else ts
    return t if t.tzinfo else t.replace(tzinfo=TZ)


def _load_l(b: dict) -> float:
    fill = b.get("fill_percent") or 100.0  # unknown -> assume full
    return (
        b.get("volume_l", config.BIN_VOLUME_L)
        * min(100.0, fill + MORNING_EXTRA_POINTS)
        / 100
    )


def _planning_config() -> PlanningConfig:
    return PlanningConfig(
        start_node_id=config.DEPOT_NODE_ID,
        end_node_id=config.DEPOT_NODE_ID,
        truck_capacity=config.TRUCK_CAPACITY_L,
        demand_unit="L",
        yellow_threshold=config.ORANGE_FILL / 100,
        red_threshold=config.RED_FILL / 100,
        observation_max_age_seconds=config.NO_DATA_HOURS * 3600,
        demand_policy=DemandPolicy.ALLOW_MARKED_ESTIMATES,  # our litres are estimates, marked as such
    )


def _road_context(all_bins: list[dict], depot: dict) -> RoadContext | None:
    """Load the approved graph and build costs in the same node order as the bins."""
    graph_dir = Path(GRAPH_DIR)
    if not graph_dir.is_dir():
        return None
    locations = (
        RoadLocation(config.DEPOT_NODE_ID, GeoLocation(depot["lon"], depot["lat"])),
        *(RoadLocation(b["id"], GeoLocation(b["lon"], b["lat"])) for b in all_bins),
    )
    artifact = load_graph(graph_dir)
    # Round trips need one strongly connected road component. The cached graph
    # retains small disconnected islands, which can otherwise make valid bins
    # appear unreachable from the depot.
    import networkx as nx

    component = max(nx.strongly_connected_components(artifact.graph), key=len)
    if len(component) != len(artifact.graph):
        artifact = GraphArtifact(
            artifact.graph.subgraph(component).copy(),
            artifact.provenance,
            artifact.graph_path,
        )
    costs = build_road_costs(
        artifact,
        locations,
        depot_id=config.DEPOT_NODE_ID,
        matching=MatchingConfig(ROAD_MATCH_MAX_M, UnusableMatchPolicy.REJECT),
        objective=RoadCostMetric.DISTANCE,
    )
    snap_m = np.array(
        [match.distance_meters or 0.0 for match in costs.matching.matches]
    )
    return RoadContext(artifact, costs, snap_m)


def _geometry_payload(geometry) -> dict:
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "source_id": leg.source_id,
                    "target_id": leg.target_id,
                    "distance_meters": leg.distance_meters,
                    "duration_seconds": leg.duration_seconds,
                },
                "geometry": (
                    {
                        "type": "LineString",
                        "coordinates": [list(point) for point in leg.geometry],
                    }
                    if leg.geometry is not None
                    else None
                ),
            }
            for leg in geometry.legs
        ],
    }


def _solve_tour(
    group: list[dict],
    M: np.ndarray,
    snap_m: np.ndarray,
    index: dict,
    now: datetime,
    road: RoadContext | None = None,
) -> dict:
    """One truck tour: build the team package's inputs, call plan_collection, translate back."""
    ids = [config.DEPOT_NODE_ID] + [b["id"] for b in group]
    mi = [0] + [index[b["id"]] for b in group]
    dist = tuple(
        tuple(float(M[i, j]) if np.isfinite(M[i, j]) else None for j in mi) for i in mi
    )
    snapshot = PlanningSnapshot(
        bins=tuple(
            BinMetadata(
                b["id"],
                source_id=b.get("osm_id"),
                location=GeoLocation(b["lon"], b["lat"]),
            )
            for b in group
        ),
        observations=tuple(
            FillObservation(
                b["id"],
                min(1.0, max(0.0, b["fill_percent"] / 100)),
                _aware(b["observed_at"]),
            )
            for b in group
            if b.get("fill_percent") is not None and b.get("observed_at")
        ),
        demands=tuple(
            CollectionDemand(b["id"], round(_load_l(b), 1), "L", estimated=True)
            for b in group
        ),
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
    route_geometry = None
    if road is not None and result.status.value == "feasible":
        route_geometry = build_route_geometry(result, road.costs, road.artifact)

    routed_bins = {b["id"]: b for b in group if b["id"] in stops}
    on_foot = sum(1 for bin_id in stops if snap_m[index[bin_id]] > streets.ON_FOOT_M)
    walk_km = sum(
        2 * snap_m[index[bin_id]] / 1000
        for bin_id in stops
        if snap_m[index[bin_id]] > streets.ON_FOOT_M
    )
    km = (
        route_geometry.distance_meters / 1000
        if route_geometry is not None
        else float(sr.travel_distance)
        if sr and sr.travel_distance is not None
        else math.nan
    )
    driving_hours = (
        route_geometry.duration_seconds / 3600
        if route_geometry is not None
        else km / config.AVG_SPEED_KMH
        if not math.isnan(km)
        else math.nan
    )
    service_hours = len(stops) * config.SERVICE_MIN_PER_BIN / 60
    walking_hours = walk_km / config.WALK_SPEED_KMH
    hours = driving_hours + service_hours + walking_hours
    excluded = [a.bin_id for a in result.bins if not a.included_in_route]
    route = {
        "stops": stops,
        "distance_km": float(round(km, 1)) if not math.isnan(km) else None,
        "duration_h": float(round(hours, 2)) if not math.isnan(hours) else None,
        "driving_duration_h": (
            float(round(driving_hours, 2)) if not math.isnan(driving_hours) else None
        ),
        "service_duration_h": float(round(service_hours, 2)),
        "walking_duration_h": float(round(walking_hours, 2)),
        "load_l": round(sum(_load_l(b) for b in routed_bins.values())),
        "on_foot_stops": on_foot,
        "status": result.status.value,
        "excluded": excluded,
        "diagnostics": sorted({d.code for d in result.diagnostics}),
    }
    if route_geometry is not None:
        route["route_mode"] = "REAL_ROAD_NETWORK"
        route["road_route"] = {
            "crs": "EPSG:4326",
            "geometry": _geometry_payload(route_geometry),
            "physical_distance": {
                "value": float(route_geometry.distance_meters),
                "unit": "m",
            },
        }
    else:
        route["route_mode"] = "STRAIGHT_LINE_FALLBACK"
    return route


def _route_aware_groups(
    bins: list[dict], matrix: np.ndarray, index: dict[str, int], truck_count: int
) -> list[list[dict]]:
    """Order bins on the supplied road matrix before splitting them into tours."""

    ordered_indices, _ = streets.tour(
        matrix, [index[bin_record["id"]] for bin_record in bins]
    )
    bins_by_index = {index[bin_record["id"]]: bin_record for bin_record in bins}
    ordered_bins = [bins_by_index[item] for item in ordered_indices]
    groups: list[list[dict]] = []
    remaining_load = sum(_load_l(bin_record) for bin_record in ordered_bins)
    remaining_groups = truck_count
    current: list[dict] = []
    current_load = 0.0
    for bin_record in ordered_bins:
        bin_load = _load_l(bin_record)
        should_split = (
            current
            and remaining_groups > 1
            and current_load + bin_load > remaining_load / remaining_groups
        )
        if should_split:
            groups.append(current)
            remaining_load -= current_load
            remaining_groups -= 1
            current = []
            current_load = 0.0
        current.append(bin_record)
        current_load += bin_load
    if current:
        groups.append(current)
    return groups


def plan_routes(
    to_empty: list[dict],
    all_bins: list[dict],
    now: datetime | None = None,
    depot: dict | None = None,
) -> tuple[list[dict], str]:
    # Green-flagged bins must not affect clustering, truck sizing, or route output.
    to_empty = [
        bin_record for bin_record in to_empty if bin_record.get("fill_band") != "green"
    ]
    if depot is None:
        data = json.loads(
            (streets.ROOT / "data" / "bins_locations.json").read_text(encoding="utf-8")
        )
        depot = data["depot"]
    road = _road_context(to_empty, depot)
    if road is not None:
        M = np.array(road.costs.costs.distances, dtype=float) / 1000.0
        M[~np.isfinite(M)] = np.inf
        snap_m = road.snap_m
        kind = "real streets"
    else:
        M, kind = streets.get_matrix()
        snap_m = streets.get_snap_m(len(all_bins) + 1)
    matrix_bins = to_empty if road is not None else all_bins
    index = {
        b["id"]: i + 1 for i, b in enumerate(matrix_bins)
    }  # matrix index (0 = depot)
    if not to_empty:
        return [], kind
    now = now or datetime.now(TZ)

    total_load = sum(_load_l(b) for b in to_empty)
    service_h = len(to_empty) * config.SERVICE_MIN_PER_BIN / 60
    k = max(
        1,
        math.ceil(total_load / config.TRUCK_CAPACITY_L),
        math.ceil(service_h / config.SHIFT_HOURS),
    )
    while True:
        routes = []
        groups = _route_aware_groups(to_empty, M, index, min(k, len(to_empty)))
        for group in groups:
            r = _solve_tour(group, M, snap_m, index, now, road)
            r["within_limits"] = bool(
                r["status"] == "feasible"
                and r["load_l"] <= config.TRUCK_CAPACITY_L
                and r["duration_h"] is not None
                and r["duration_h"] <= config.SHIFT_HOURS
            )
            routes.append(r)
        if all(r["within_limits"] for r in routes) or k >= min(
            config.MAX_TRUCKS, len(to_empty)
        ):
            break
        k += 1

    if not all(r["within_limits"] for r in routes):
        print(
            f"WARNING: even {k} trucks can't keep all limits. Check TRUCK_CAPACITY_L / SHIFT_HOURS / MAX_TRUCKS."
        )
    return [{"zone": i, **r} for i, r in enumerate(routes, 1)], kind
