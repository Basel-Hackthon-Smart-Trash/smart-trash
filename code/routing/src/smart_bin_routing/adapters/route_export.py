"""Versioned, JSON-compatible export for collection-plan results."""

from __future__ import annotations

import json
import math
from datetime import datetime
from enum import Enum
from typing import Any

from ..orchestration import CollectionPlanRequest, CollectionPlanResult
from .osmnx_graph import GraphArtifact
from .road_costs import RoadCostResult
from .route_geometry import RouteGeometry, build_route_geometry

EXPORT_SCHEMA_VERSION = 1


class RouteExportError(ValueError):
    """A collection plan cannot be represented by the export schema."""


def _json_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise RouteExportError("non-finite values are not valid in route payloads")
        return value
    if isinstance(value, dict):
        return {_json_value(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    raise RouteExportError(f"unsupported value in route payload: {type(value).__name__}")


def _diagnostic(item: Any) -> dict[str, Any]:
    return _json_value(
        {
            "code": item.code,
            "message": item.message,
            "severity": item.severity,
            "bin_id": getattr(item, "bin_id", None),
        }
    )


def _geometry_payload(geometry: RouteGeometry) -> dict[str, Any]:
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
                    "keyed_edges": _json_value(leg.keyed_edges),
                },
                "geometry": (
                    {"type": "LineString", "coordinates": [list(point) for point in leg.geometry]}
                    if leg.geometry is not None
                    else None
                ),
            }
            for leg in geometry.legs
        ],
    }


def _provenance(
    request: CollectionPlanRequest, road_costs: RoadCostResult | None
) -> dict[str, Any]:
    costs = request.travel_costs
    result: dict[str, Any] = {
        "travel_cost": {
            "node_order": list(costs.node_ids),
            "distance_unit": costs.distance_unit,
            "duration_unit": costs.duration_unit,
            "provenance": dict(costs.provenance),
        }
    }
    if road_costs is not None:
        road = road_costs.provenance
        result["road"] = {
            "graph_identity": road.graph_identity,
            "objective": road.objective.value,
            "depot_id": road.depot_id,
            "location_order": list(road.location_order),
            "distance_unit": road.distance_unit,
            "duration_unit": road.duration_unit,
            "matching": {
                "max_snap_distance_meters": road.matching.max_snap_distance_meters,
                "unusable_policy": road.matching.unusable_policy.value,
                "diagnostics": [
                    {
                        "code": diagnostic.code,
                        "message": diagnostic.message,
                        "severity": diagnostic.severity,
                    }
                    for diagnostic in road_costs.matching.diagnostics
                ],
            },
            "graph_crs": road_costs.matching.graph_crs,
        }
    return result


def serialize_collection_plan(
    request: CollectionPlanRequest,
    result: CollectionPlanResult,
    *,
    road_costs: RoadCostResult | None = None,
    artifact: GraphArtifact | None = None,
    request_id: str | None = None,
    plan_id: str | None = None,
) -> dict[str, Any]:
    """Return a standard JSON-compatible payload without inventing missing data."""

    payload: dict[str, Any] = {
        "schema_version": EXPORT_SCHEMA_VERSION,
        "request_id": request_id,
        "plan_id": plan_id,
        "status": result.status.value,
        "diagnostics": [_diagnostic(item) for item in result.diagnostics],
        "stops": [],
        "assessments": [
            {
                "bin_id": item.bin_id,
                "classification": item.classification.value,
                "routing_ready": item.routing_ready,
                "included_in_route": item.included_in_route,
                "diagnostics": [_diagnostic(diagnostic) for diagnostic in item.diagnostics],
            }
            for item in result.bins
        ],
        "metrics": {
            "capacity": request.config.truck_capacity,
            "capacity_unit": request.config.demand_unit,
            "supplied_demands": [
                {"bin_id": demand.bin_id, "amount": demand.amount, "unit": demand.unit}
                for demand in request.snapshot.demands
            ],
        },
        "provenance": _provenance(request, road_costs),
    }
    solver = result.solver_result
    if solver is not None:
        payload["solver"] = {
            "status": solver.status.value,
            "route_nodes": list(solver.route_nodes),
            "objective_value": solver.objective_value,
            "objective_cost": solver.total_travel_cost,
            "objective_cost_unit": solver.travel_cost_unit,
            "collected_demand": solver.collected_demand,
            "loads_after_stop": list(solver.loads_after_stop),
            "diagnostics": list(solver.diagnostics),
            "metadata": dict(solver.solver_metadata),
        }
        payload["stops"] = [
            {
                "sequence": sequence,
                "bin_id": bin_id,
                "demand": next(
                    (
                        {"amount": demand.amount, "unit": demand.unit}
                        for demand in request.snapshot.demands
                        if demand.bin_id == bin_id
                    ),
                    None,
                ),
                "load_after_stop": (
                    solver.loads_after_stop[sequence]
                    if sequence < len(solver.loads_after_stop)
                    else None
                ),
            }
            for sequence, bin_id in enumerate(solver.stops)
        ]
    if (
        result.status.value == "feasible"
        and result.solver_result is not None
        and result.solver_result.status.value == "feasible"
    ):
        if road_costs is None or artifact is None:
            raise RouteExportError("feasible exports require G3 road costs and a loaded graph")
        geometry = build_route_geometry(result, road_costs, artifact)
        payload["positions"] = [
            {
                "location_id": position.location_id,
                "role": "depot" if position.location_id == request.config.start_node_id else "bin",
                "original": {
                    "longitude": position.original.longitude,
                    "latitude": position.original.latitude,
                },
                "snapped": (
                    {
                        "longitude": position.snapped.longitude,
                        "latitude": position.snapped.latitude,
                    }
                    if position.snapped is not None
                    else None
                ),
            }
            for position in geometry.positions
        ]
        payload["road_route"] = {
            "crs": "EPSG:4326",
            "geometry": _geometry_payload(geometry),
            "legs": [
                {
                    "source_id": leg.source_id,
                    "target_id": leg.target_id,
                    "distance_meters": leg.distance_meters,
                    "duration_seconds": leg.duration_seconds,
                }
                for leg in geometry.legs
            ],
            "physical_distance": {"value": geometry.distance_meters, "unit": "m"},
            "estimated_driving_time": {"value": geometry.duration_seconds, "unit": "s"},
        }
        if artifact.provenance is not None:
            payload["provenance"]["graph"] = {
                "schema_version": artifact.provenance.schema_version,
                "graph_sha256": artifact.provenance.graph_sha256,
                "acquired_at": artifact.provenance.acquired_at.isoformat(),
                "area": artifact.provenance.area,
                "settings": artifact.provenance.settings,
                "versions": artifact.provenance.versions,
            }
    return _json_value(payload)


def encode_collection_plan(*args: Any, **kwargs: Any) -> str:
    """Encode a collection plan, rejecting NaN and infinity."""

    return json.dumps(serialize_collection_plan(*args, **kwargs), allow_nan=False, sort_keys=True)
