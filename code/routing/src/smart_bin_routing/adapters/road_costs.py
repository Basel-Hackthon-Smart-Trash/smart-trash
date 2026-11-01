"""Offline graph matching and directed road costs.

This adapter is deliberately separate from the source-independent optimizer.
It accepts a previously loaded graph and emits location-keyed costs; graph node
identifiers never become bin or depot identities.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from enum import StrEnum
from heapq import heappop, heappush
from typing import Any

from ..contracts import TravelCostMatrix
from ..models import GeoLocation
from .osmnx_graph import GraphArtifact


class RoadCostError(ValueError):
    """A graph, match, path, or road-cost request is unusable."""


class UnusableMatchPolicy(StrEnum):
    """How a caller wants unusable location matches handled."""

    REJECT = "reject"
    REPORT = "report"


class RoadCostMetric(StrEnum):
    """Objective used to select one directed path between two locations."""

    DISTANCE = "distance"
    DURATION = "duration"


@dataclass(frozen=True, slots=True)
class GraphCoordinate:
    """A coordinate in the graph's declared CRS."""

    x: float
    y: float
    crs: str


@dataclass(frozen=True, slots=True)
class RoadLocation:
    """A caller-owned location identity and its WGS84 position."""

    location_id: str
    location: GeoLocation

    def __post_init__(self) -> None:
        if not isinstance(self.location_id, str) or not self.location_id.strip():
            raise RoadCostError("location_id must be a non-empty string")


@dataclass(frozen=True, slots=True)
class MatchingConfig:
    """Explicit node-matching policy; no operational snap default exists."""

    max_snap_distance_meters: float
    unusable_policy: UnusableMatchPolicy = UnusableMatchPolicy.REJECT

    def __post_init__(self) -> None:
        if (
            isinstance(self.max_snap_distance_meters, bool)
            or not isinstance(self.max_snap_distance_meters, (int, float))
            or not math.isfinite(self.max_snap_distance_meters)
            or self.max_snap_distance_meters < 0
        ):
            raise RoadCostError("max_snap_distance_meters must be finite and non-negative")
        if not isinstance(self.unusable_policy, UnusableMatchPolicy):
            raise RoadCostError("unusable_policy must be an UnusableMatchPolicy")


@dataclass(frozen=True, slots=True)
class MatchDiagnostic:
    code: str
    message: str
    severity: str = "error"


@dataclass(frozen=True, slots=True)
class LocationMatch:
    """Original and graph-space positions for one location."""

    location_id: str
    original: GeoLocation
    snapped: GraphCoordinate | None
    graph_node_id: Any | None
    distance_meters: float | None
    diagnostics: tuple[MatchDiagnostic, ...] = ()

    @property
    def usable(self) -> bool:
        return self.graph_node_id is not None and not self.diagnostics


@dataclass(frozen=True, slots=True)
class MatchingResult:
    """All requested matches, including unusable ones and diagnostics."""

    matches: tuple[LocationMatch, ...]
    graph_identity: str
    graph_crs: str
    config: MatchingConfig
    diagnostics: tuple[MatchDiagnostic, ...] = ()

    def __post_init__(self) -> None:
        ids = tuple(item.location_id for item in self.matches)
        if len(set(ids)) != len(ids):
            raise RoadCostError("location IDs must be unique")
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))

    @property
    def usable(self) -> bool:
        return all(item.usable for item in self.matches)


@dataclass(frozen=True, slots=True)
class DirectedPath:
    """One selected path and both measurements on those exact keyed edges."""

    source_id: str
    target_id: str
    graph_nodes: tuple[Any, ...]
    keyed_edges: tuple[tuple[Any, Any, Any], ...]
    distance_meters: float
    duration_seconds: float
    objective: RoadCostMetric


@dataclass(frozen=True, slots=True)
class RoadCostProvenance:
    """Identity inputs that make a road-cost result reproducible."""

    graph_identity: str
    matching: MatchingConfig
    depot_id: str
    location_order: tuple[str, ...]
    objective: RoadCostMetric
    distance_unit: str = "m"
    duration_unit: str = "s"


@dataclass(frozen=True, slots=True)
class RoadCostResult:
    """Location-keyed directed costs, paths, matches, and provenance."""

    costs: TravelCostMatrix
    paths: tuple[DirectedPath, ...]
    matching: MatchingResult
    provenance: RoadCostProvenance

    def path_for(self, source_id: str, target_id: str) -> DirectedPath | None:
        return next(
            (
                path
                for path in self.paths
                if path.source_id == source_id and path.target_id == target_id
            ),
            None,
        )


def _stable(value: Any) -> tuple[str, str]:
    return type(value).__name__, repr(value)


def _graph_crs(graph: Any) -> tuple[Any, str]:
    try:
        from pyproj import CRS

        value = graph.graph["crs"]
        crs = CRS.from_user_input(value)
    except (KeyError, TypeError, ValueError) as error:
        raise RoadCostError("graph must declare a valid CRS") from error
    return crs, str(crs)


def _node_coordinates(graph: Any, node: Any) -> tuple[float, float]:
    try:
        x = float(graph.nodes[node]["x"])
        y = float(graph.nodes[node]["y"])
    except (KeyError, TypeError, ValueError) as error:
        raise RoadCostError(f"graph node {node!r} lacks finite x/y coordinates") from error
    if not math.isfinite(x) or not math.isfinite(y):
        raise RoadCostError(f"graph node {node!r} lacks finite x/y coordinates")
    return x, y


def match_locations(
    artifact: GraphArtifact,
    locations: tuple[RoadLocation, ...],
    config: MatchingConfig,
) -> MatchingResult:
    """Snap WGS84 locations to graph nodes using an explicit meter limit."""

    if not isinstance(artifact, GraphArtifact):
        raise RoadCostError("a previously loaded GraphArtifact is required")
    graph = artifact.graph
    graph_crs, graph_crs_text = _graph_crs(graph)
    try:
        from pyproj import Geod, Transformer

        to_graph = Transformer.from_crs("EPSG:4326", graph_crs, always_xy=True)
        to_wgs84 = Transformer.from_crs(graph_crs, "EPSG:4326", always_xy=True)
        geod = Geod(ellps="WGS84")
    except (TypeError, ValueError) as error:
        raise RoadCostError("graph CRS cannot support coordinate transformation") from error

    node_data = []
    for node in sorted(graph.nodes, key=_stable):
        x, y = _node_coordinates(graph, node)
        lon, lat = to_wgs84.transform(x, y)
        node_data.append((node, x, y, lon, lat))
    if not node_data:
        raise RoadCostError("graph has no nodes")

    matches = []
    for item in locations:
        x, y = to_graph.transform(item.location.longitude, item.location.latitude)
        node, nx, ny, lon, lat = min(
            node_data,
            key=lambda candidate: (
                (candidate[1] - x) ** 2 + (candidate[2] - y) ** 2,
                _stable(candidate[0]),
            ),
        )
        _, _, distance = geod.inv(item.location.longitude, item.location.latitude, lon, lat)
        diagnostics = ()
        if not math.isfinite(distance):
            diagnostics = (MatchDiagnostic("invalid_snap_distance", "snap distance is not finite"),)
        elif distance > config.max_snap_distance_meters:
            diagnostics = (
                MatchDiagnostic(
                    "excessive_snap_distance",
                    f"nearest graph node is {distance:.3f} m away, exceeding the approved limit",
                ),
            )
        matches.append(
            LocationMatch(
                item.location_id,
                item.location,
                GraphCoordinate(nx, ny, graph_crs_text),
                node,
                distance,
                diagnostics,
            )
        )
    by_node: dict[Any, list[str]] = {}
    for item in matches:
        if item.graph_node_id is not None:
            by_node.setdefault(item.graph_node_id, []).append(item.location_id)
    diagnostics = tuple(
        MatchDiagnostic(
            "duplicate_graph_node_match",
            f"locations share graph node {node!r}: {', '.join(sorted(location_ids))}",
            "warning",
        )
        for node, location_ids in sorted(by_node.items(), key=lambda item: _stable(item[0]))
        if len(location_ids) > 1
    )
    return MatchingResult(
        tuple(matches), artifact.provenance.graph_sha256, graph_crs_text, config, diagnostics
    )


def _edge_values(data: dict[str, Any]) -> tuple[float, float]:
    try:
        distance = float(data["length"])
        duration = float(data["travel_time"])
    except (KeyError, TypeError, ValueError) as error:
        raise RoadCostError("graph edge lacks length or travel_time") from error
    if not all(math.isfinite(value) and value > 0 for value in (distance, duration)):
        raise RoadCostError("graph edge length and travel_time must be positive and finite")
    return distance, duration


def _shortest_path(
    graph: Any, source: Any, target: Any, objective: RoadCostMetric
) -> DirectedPath | None:
    if source == target:
        return DirectedPath("", "", (source,), (), 0.0, 0.0, objective)
    queue = [(0.0, (), _stable(source), source, (source,), (), 0.0, 0.0)]
    best: dict[Any, tuple[float, tuple[tuple[str, str], ...]]] = {}
    while queue:
        cost, signature, _, node, nodes, edges, distance, duration = heappop(queue)
        previous = best.get(node)
        current_key = (cost, signature)
        if previous is not None and current_key > previous:
            continue
        best[node] = current_key
        if node == target:
            return DirectedPath("", "", nodes, edges, distance, duration, objective)
        for neighbour in sorted(graph.successors(node), key=_stable):
            edge_items = sorted(graph[node][neighbour].items(), key=lambda item: _stable(item[0]))
            for key, data in edge_items:
                edge_distance, edge_duration = _edge_values(data)
                edge_cost = edge_distance if objective == RoadCostMetric.DISTANCE else edge_duration
                next_signature = signature + ((repr(neighbour), repr(key)),)
                next_cost = cost + edge_cost
                next_key = (next_cost, next_signature)
                known = best.get(neighbour)
                if known is None or next_key < known:
                    heappush(
                        queue,
                        (
                            next_cost,
                            next_signature,
                            _stable(neighbour),
                            neighbour,
                            nodes + (neighbour,),
                            edges + ((node, neighbour, key),),
                            distance + edge_distance,
                            duration + edge_duration,
                        ),
                    )
    return None


def build_road_costs(
    artifact: GraphArtifact,
    locations: tuple[RoadLocation, ...],
    *,
    depot_id: str,
    matching: MatchingConfig,
    objective: RoadCostMetric,
) -> RoadCostResult:
    """Match locations and build a directed matrix in the supplied order."""

    if not isinstance(objective, RoadCostMetric):
        raise RoadCostError("objective must be a RoadCostMetric")
    order = tuple(item.location_id for item in locations)
    if depot_id not in order:
        raise RoadCostError("depot_id must be present in location order")
    if len(set(order)) != len(order):
        raise RoadCostError("location IDs must be unique")
    matched = match_locations(artifact, locations, matching)
    if not matched.usable and matching.unusable_policy == UnusableMatchPolicy.REJECT:
        bad = ", ".join(item.location_id for item in matched.matches if not item.usable)
        raise RoadCostError(f"unusable mandatory location matches: {bad}")
    by_id = {item.location_id: item for item in matched.matches}
    graph = artifact.graph
    size = len(order)
    distances: list[list[float | None]] = [[None] * size for _ in range(size)]
    durations: list[list[float | None]] = [[None] * size for _ in range(size)]
    paths: list[DirectedPath] = []
    path_cache: dict[tuple[Any, Any], DirectedPath | None] = {}
    for source_index, source_id in enumerate(order):
        for target_index, target_id in enumerate(order):
            source = by_id[source_id]
            target = by_id[target_id]
            if not source.usable or not target.usable:
                continue
            cache_key = (source.graph_node_id, target.graph_node_id)
            if cache_key not in path_cache:
                path_cache[cache_key] = _shortest_path(
                    graph, source.graph_node_id, target.graph_node_id, objective
                )
            path = path_cache[cache_key]
            if path is None:
                continue
            path = DirectedPath(
                source_id,
                target_id,
                path.graph_nodes,
                path.keyed_edges,
                path.distance_meters,
                path.duration_seconds,
                objective,
            )
            paths.append(path)
            distances[source_index][target_index] = path.distance_meters
            durations[source_index][target_index] = path.duration_seconds
    costs = TravelCostMatrix(
        order,
        tuple(tuple(row) for row in distances),
        tuple(tuple(row) for row in durations),
        "m",
        "s",
        (
            ("graph_sha256", matched.graph_identity),
            ("depot_id", depot_id),
            (
                "matching_config",
                json.dumps({"max_snap_distance_meters": matching.max_snap_distance_meters}),
            ),
            ("objective", objective.value),
        ),
    )
    provenance = RoadCostProvenance(matched.graph_identity, matching, depot_id, order, objective)
    return RoadCostResult(costs, tuple(paths), matched, provenance)
