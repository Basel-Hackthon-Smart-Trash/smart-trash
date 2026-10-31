from datetime import UTC, datetime
from pathlib import Path

import networkx as nx
import pytest
from pyproj import Geod, Transformer

from smart_bin_routing import (
    GraphArtifact,
    GraphProvenance,
    MatchingConfig,
    RoadCostError,
    RoadCostMetric,
    RoadLocation,
    UnusableMatchPolicy,
    build_road_costs,
    match_locations,
)
from smart_bin_routing.models import GeoLocation


def artifact(graph: nx.MultiDiGraph) -> GraphArtifact:
    provenance = GraphProvenance(
        1,
        "a" * 64,
        datetime(2026, 10, 31, 12, 0, tzinfo=UTC),
        {"crs": "EPSG:4326"},
        {"network_type": "drive"},
        {"test": "synthetic"},
    )
    return GraphArtifact(graph, provenance, Path("synthetic.graphml"))


def graph_with_nodes(*nodes: tuple[str, float, float]) -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph()
    graph.graph["crs"] = "EPSG:4326"
    for node, longitude, latitude in nodes:
        graph.add_node(node, x=longitude, y=latitude)
    return graph


def locations(*items: tuple[str, float, float]) -> tuple[RoadLocation, ...]:
    return tuple(
        RoadLocation(name, GeoLocation(longitude, latitude)) for name, longitude, latitude in items
    )


def add_edge(graph, source, target, key, *, length, travel_time):
    graph.add_edge(source, target, key=key, length=length, travel_time=travel_time)


def test_directed_matrix_preserves_order_and_asymmetry():
    graph = graph_with_nodes(("road-a", 7.58, 47.55), ("road-b", 7.59, 47.55))
    add_edge(graph, "road-a", "road-b", "forward", length=100, travel_time=10)
    add_edge(graph, "road-b", "road-a", "reverse", length=250, travel_time=25)

    result = build_road_costs(
        artifact(graph),
        locations(("bin", 7.59, 47.55), ("depot", 7.58, 47.55)),
        depot_id="depot",
        matching=MatchingConfig(100),
        objective=RoadCostMetric.DISTANCE,
    )

    assert result.costs.node_ids == ("bin", "depot")
    assert result.costs.distances == ((0.0, 250.0), (100.0, 0.0))
    assert result.costs.durations_seconds == ((0.0, 25.0), (10.0, 0.0))
    assert result.provenance.depot_id == "depot"
    assert result.provenance.location_order == ("bin", "depot")


def test_matching_projected_graph_uses_geodesic_meters():
    to_projected = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
    node_x, node_y = to_projected.transform(7.58, 47.55)
    graph = graph_with_nodes(("road", node_x, node_y))
    graph.graph["crs"] = "EPSG:3857"
    longitude, latitude = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True).transform(
        node_x + 10, node_y
    )

    result = match_locations(
        artifact(graph),
        locations(("bin", longitude, latitude)),
        MatchingConfig(20),
    )

    expected = Geod(ellps="WGS84").inv(7.58, 47.55, longitude, latitude)[2]
    assert result.matches[0].distance_meters == pytest.approx(expected, abs=0.001)
    assert result.matches[0].snapped.crs == "EPSG:3857"


def test_disconnected_pair_is_unavailable_not_zero():
    graph = graph_with_nodes(("a", 7.58, 47.55), ("b", 7.59, 47.55))
    result = build_road_costs(
        artifact(graph),
        locations(("depot", 7.58, 47.55), ("bin", 7.59, 47.55)),
        depot_id="depot",
        matching=MatchingConfig(100),
        objective=RoadCostMetric.DISTANCE,
    )

    assert result.costs.distances[0][1] is None
    assert result.costs.distances[1][0] is None


def test_shared_graph_node_has_zero_length_path_and_distinct_location_ids():
    graph = graph_with_nodes(("shared", 7.58, 47.55))
    result = build_road_costs(
        artifact(graph),
        locations(("depot", 7.58, 47.55), ("bin", 7.58, 47.55)),
        depot_id="depot",
        matching=MatchingConfig(0),
        objective=RoadCostMetric.DURATION,
    )

    assert result.costs.node_ids == ("depot", "bin")
    assert result.costs.distances == ((0.0, 0.0), (0.0, 0.0))
    assert result.path_for("depot", "bin").keyed_edges == ()


def test_excessive_snap_is_reported_or_rejected():
    graph = graph_with_nodes(("road", 8.0, 47.55))
    requested = locations(("depot", 7.58, 47.55))
    with pytest.raises(RoadCostError, match="unusable"):
        build_road_costs(
            artifact(graph),
            requested,
            depot_id="depot",
            matching=MatchingConfig(1),
            objective=RoadCostMetric.DISTANCE,
        )

    matching = match_locations(
        artifact(graph),
        requested,
        MatchingConfig(1, UnusableMatchPolicy.REPORT),
    )
    assert matching.matches[0].diagnostics[0].code == "excessive_snap_distance"
    result = build_road_costs(
        artifact(graph),
        requested,
        depot_id="depot",
        matching=MatchingConfig(1, UnusableMatchPolicy.REPORT),
        objective=RoadCostMetric.DISTANCE,
    )
    assert result.costs.distances == ((None,),)


def test_parallel_edges_choose_deterministic_key_for_equal_objective():
    graph = graph_with_nodes(("a", 7.58, 47.55), ("b", 7.59, 47.55))
    add_edge(graph, "a", "b", "z", length=10, travel_time=10)
    add_edge(graph, "a", "b", "a", length=10, travel_time=10)

    result = build_road_costs(
        artifact(graph),
        locations(("depot", 7.58, 47.55), ("bin", 7.59, 47.55)),
        depot_id="depot",
        matching=MatchingConfig(100),
        objective=RoadCostMetric.DISTANCE,
    )

    assert result.path_for("depot", "bin").keyed_edges == (("a", "b", "a"),)


def test_objective_selects_edges_but_both_metrics_measure_that_same_path():
    graph = graph_with_nodes(("a", 7.58, 47.55), ("b", 7.59, 47.55), ("c", 7.60, 47.55))
    add_edge(graph, "a", "b", "short", length=10, travel_time=100)
    add_edge(graph, "b", "c", "short", length=10, travel_time=100)
    add_edge(graph, "a", "c", "slow", length=30, travel_time=10)
    result = build_road_costs(
        artifact(graph),
        locations(("depot", 7.58, 47.55), ("bin", 7.60, 47.55)),
        depot_id="depot",
        matching=MatchingConfig(100),
        objective=RoadCostMetric.DURATION,
    )

    path = result.path_for("depot", "bin")
    assert path.keyed_edges == (("a", "c", "slow"),)
    assert path.distance_meters == result.costs.distances[0][1] == 30
    assert path.duration_seconds == result.costs.durations_seconds[0][1] == 10
