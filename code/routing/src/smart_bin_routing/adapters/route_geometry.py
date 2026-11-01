"""Reconstruct route geometry from the exact paths selected by G3."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from ..models import GeoLocation, PlanningStatus
from ..orchestration import CollectionPlanResult
from .osmnx_graph import GraphArtifact
from .road_costs import DirectedPath, RoadCostResult


class RouteGeometryError(ValueError):
    """A selected route cannot be represented with the supplied graph."""


@dataclass(frozen=True, slots=True)
class RoutePosition:
    location_id: str
    original: GeoLocation
    snapped: GeoLocation | None


@dataclass(frozen=True, slots=True)
class RouteLeg:
    source_id: str
    target_id: str
    distance_meters: float
    duration_seconds: float
    geometry: tuple[tuple[float, float], ...] | None
    keyed_edges: tuple[tuple[Any, Any, Any], ...]


@dataclass(frozen=True, slots=True)
class RouteGeometry:
    route_nodes: tuple[str, ...]
    positions: tuple[RoutePosition, ...]
    legs: tuple[RouteLeg, ...]
    distance_meters: float
    duration_seconds: float


def _node_xy(graph: Any, node: Any) -> tuple[float, float]:
    try:
        x = float(graph.nodes[node]["x"])
        y = float(graph.nodes[node]["y"])
    except (KeyError, TypeError, ValueError) as error:
        raise RouteGeometryError(f"graph node {node!r} lacks finite x/y coordinates") from error
    if not math.isfinite(x) or not math.isfinite(y):
        raise RouteGeometryError(f"graph node {node!r} lacks finite x/y coordinates")
    return x, y


def _edge_coordinates(data: Any) -> list[tuple[float, float]] | None:
    geometry = data.get("geometry")
    if geometry is None:
        return None
    try:
        coordinates = [(float(x), float(y)) for x, y in geometry.coords]
    except (AttributeError, TypeError, ValueError) as error:
        raise RouteGeometryError("edge geometry must expose finite coordinate pairs") from error
    if len(coordinates) < 2 or any(
        not math.isfinite(value) for point in coordinates for value in point
    ):
        raise RouteGeometryError("edge geometry must contain at least two finite coordinates")
    return coordinates


def _oriented_edge_coordinates(
    graph: Any, source: Any, target: Any, data: Any
) -> list[tuple[float, float]]:
    coordinates = _edge_coordinates(data)
    if coordinates is None:
        return [_node_xy(graph, source), _node_xy(graph, target)]
    source_xy = _node_xy(graph, source)
    target_xy = _node_xy(graph, target)

    def squared_distance(point: tuple[float, float], other: tuple[float, float]) -> float:
        return (point[0] - other[0]) ** 2 + (point[1] - other[1]) ** 2

    forward = squared_distance(coordinates[0], source_xy) + squared_distance(
        coordinates[-1], target_xy
    )
    reverse = squared_distance(coordinates[-1], source_xy) + squared_distance(
        coordinates[0], target_xy
    )
    return list(reversed(coordinates)) if reverse < forward else coordinates


def _transformer(graph: Any):
    try:
        from pyproj import CRS, Transformer

        crs = CRS.from_user_input(graph.graph["crs"])
        return Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    except (KeyError, TypeError, ValueError) as error:
        raise RouteGeometryError("graph must declare a valid CRS") from error


def _line_for_path(
    graph: Any, path: DirectedPath, transformer: Any
) -> tuple[tuple[float, float], ...] | None:
    if not path.keyed_edges:
        return None
    graph_coordinates: list[tuple[float, float]] = []
    for source, target, key in path.keyed_edges:
        try:
            data = graph[source][target][key]
        except (KeyError, TypeError) as error:
            raise RouteGeometryError(
                f"selected edge {source!r}->{target!r}/{key!r} is absent"
            ) from error
        edge_coordinates = _oriented_edge_coordinates(graph, source, target, data)
        if graph_coordinates and graph_coordinates[-1] == edge_coordinates[0]:
            graph_coordinates.extend(edge_coordinates[1:])
        else:
            graph_coordinates.extend(edge_coordinates)
    if len(graph_coordinates) < 2:
        return None
    return tuple(transformer.transform(x, y) for x, y in graph_coordinates)


def build_route_geometry(
    plan: CollectionPlanResult,
    road_costs: RoadCostResult,
    artifact: GraphArtifact,
) -> RouteGeometry:
    """Build geometry from ``plan`` without rematching or rerouting."""

    if plan.solver_result is None or plan.solver_result.status != PlanningStatus.FEASIBLE:
        raise RouteGeometryError("geometry is available only for a feasible solver result")
    route_nodes = plan.route_nodes
    if len(route_nodes) < 2:
        raise RouteGeometryError("feasible route must contain at least two route nodes")
    if not isinstance(artifact, GraphArtifact):
        raise RouteGeometryError("a loaded GraphArtifact is required")
    transformer = _transformer(artifact.graph)
    matches = {match.location_id: match for match in road_costs.matching.matches}
    positions = []
    for location_id in route_nodes:
        match = matches.get(location_id)
        if match is None or not match.usable:
            raise RouteGeometryError(f"route location {location_id!r} has no usable match")
        snapped_x, snapped_y = match.snapped.x, match.snapped.y
        snapped_lon, snapped_lat = transformer.transform(snapped_x, snapped_y)
        positions.append(
            RoutePosition(
                location_id,
                match.original,
                GeoLocation(snapped_lon, snapped_lat),
            )
        )

    legs = []
    for source_id, target_id in zip(route_nodes, route_nodes[1:]):
        path = road_costs.path_for(source_id, target_id)
        if path is None:
            raise RouteGeometryError(
                f"selected route leg {source_id!r}->{target_id!r} is unavailable"
            )
        legs.append(
            RouteLeg(
                source_id,
                target_id,
                path.distance_meters,
                path.duration_seconds,
                _line_for_path(artifact.graph, path, transformer),
                path.keyed_edges,
            )
        )
    distance = sum(leg.distance_meters for leg in legs)
    duration = sum(leg.duration_seconds for leg in legs)
    return RouteGeometry(tuple(route_nodes), tuple(positions), tuple(legs), distance, duration)
