import json
from datetime import UTC, datetime
from pathlib import Path

import networkx as nx
import pytest
from pyproj import Transformer
from shapely.geometry import LineString

from smart_bin_routing import (
    BinMetadata,
    CollectionDemand,
    CollectionPlanRequest,
    CollectionPlanResult,
    CollectionPlanStatus,
    FillObservation,
    GeoLocation,
    GraphArtifact,
    GraphProvenance,
    MatchingConfig,
    PlanningConfig,
    PlanningResult,
    PlanningSnapshot,
    PlanningStatus,
    RoadCostMetric,
    RoadLocation,
    build_road_costs,
    build_route_geometry,
    encode_collection_plan,
    serialize_collection_plan,
)

NOW = datetime(2026, 10, 31, 12, 0, tzinfo=UTC)


def _artifact() -> GraphArtifact:
    graph = nx.MultiDiGraph()
    graph.graph["crs"] = "EPSG:4326"
    graph.add_nodes_from(
        (
            ("depot-node", {"x": 7.58, "y": 47.55}),
            ("bin-node", {"x": 7.59, "y": 47.55}),
            ("last-node", {"x": 7.60, "y": 47.55}),
        )
    )
    graph.add_edge(
        "depot-node",
        "bin-node",
        key="z",
        length=10,
        travel_time=1,
        geometry=LineString([(7.58, 47.55), (7.585, 47.55), (7.59, 47.55)]),
    )
    graph.add_edge(
        "depot-node",
        "bin-node",
        key="a",
        length=10,
        travel_time=1,
        geometry=LineString([(7.59, 47.55), (7.585, 47.55), (7.58, 47.55)]),
    )
    graph.add_edge("bin-node", "last-node", key="plain", length=20, travel_time=2)
    graph.add_edge("bin-node", "depot-node", key="reverse", length=11, travel_time=1.1)
    graph.add_edge(
        "last-node",
        "depot-node",
        key="back",
        length=30,
        travel_time=3,
        geometry=LineString([(7.60, 47.55), (7.58, 47.55)]),
    )
    return GraphArtifact(
        graph,
        GraphProvenance(1, "a" * 64, NOW, {"test": "synthetic"}, {"test": "synthetic"}, {}),
        Path("synthetic.graphml"),
    )


def _road_costs(artifact: GraphArtifact, locations: tuple[RoadLocation, ...]):
    return build_road_costs(
        artifact,
        locations,
        depot_id="depot",
        matching=MatchingConfig(1),
        objective=RoadCostMetric.DISTANCE,
    )


def _request(costs, bins: tuple[BinMetadata, ...]) -> CollectionPlanRequest:
    config = PlanningConfig("depot", "depot", 10, "kg", 0.5, 0.8, 3600)
    return CollectionPlanRequest(
        PlanningSnapshot(
            bins,
            tuple(FillObservation(item.bin_id, 0.9, NOW) for item in bins),
            tuple(CollectionDemand(item.bin_id, 1, "kg") for item in bins),
        ),
        config,
        NOW,
        costs,
    )


def test_geometry_reverses_shapes_uses_missing_shape_fallback_and_reconciles_totals():
    artifact = _artifact()
    locations = (
        RoadLocation("depot", GeoLocation(7.58, 47.55)),
        RoadLocation("bin-a", GeoLocation(7.59, 47.55)),
        RoadLocation("bin-b", GeoLocation(7.60, 47.55)),
    )
    costs = _road_costs(artifact, locations)
    plan = CollectionPlanResult(
        CollectionPlanStatus.FEASIBLE,
        solver_result=PlanningResult(
            PlanningStatus.FEASIBLE,
            stops=("bin-a", "bin-b"),
            route_nodes=("depot", "bin-a", "bin-b", "depot"),
        ),
    )

    geometry = build_route_geometry(plan, costs, artifact)

    assert geometry.legs[0].geometry[0] == pytest.approx((7.58, 47.55))
    assert geometry.legs[1].geometry[0] == pytest.approx((7.59, 47.55))
    assert geometry.legs[1].geometry[1] == pytest.approx((7.60, 47.55))
    assert geometry.distance_meters == sum(leg.distance_meters for leg in geometry.legs)
    assert geometry.duration_seconds == sum(leg.duration_seconds for leg in geometry.legs)
    assert geometry.legs[0].keyed_edges == (("depot-node", "bin-node", "a"),)


def test_same_node_consecutive_stops_keep_identity_without_empty_linestring():
    artifact = _artifact()
    locations = (
        RoadLocation("depot", GeoLocation(7.58, 47.55)),
        RoadLocation("bin-a", GeoLocation(7.59, 47.55)),
        RoadLocation("bin-b", GeoLocation(7.59, 47.55)),
    )
    costs = _road_costs(artifact, locations)
    plan = CollectionPlanResult(
        CollectionPlanStatus.FEASIBLE,
        solver_result=PlanningResult(
            PlanningStatus.FEASIBLE,
            stops=("bin-a", "bin-b"),
            route_nodes=("depot", "bin-a", "bin-b", "depot"),
        ),
    )

    geometry = build_route_geometry(plan, costs, artifact)

    assert geometry.route_nodes[1:3] == ("bin-a", "bin-b")
    assert geometry.legs[1].geometry is None
    assert geometry.legs[1].distance_meters == 0


def test_projected_graph_geometry_is_exported_as_wgs84():
    source = _artifact()
    projected = nx.MultiDiGraph()
    projected.graph["crs"] = "EPSG:3857"
    to_projected = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
    for node, data in source.graph.nodes(data=True):
        x, y = to_projected.transform(data["x"], data["y"])
        projected.add_node(node, x=x, y=y)
    for source_node, target_node, key, data in source.graph.edges(keys=True, data=True):
        values = dict(data)
        if values.get("geometry") is not None:
            values["geometry"] = LineString(
                [to_projected.transform(x, y) for x, y in values["geometry"].coords]
            )
        projected.add_edge(source_node, target_node, key=key, **values)
    artifact = GraphArtifact(projected, source.provenance, source.graph_path)
    costs = _road_costs(
        artifact,
        (
            RoadLocation("depot", GeoLocation(7.58, 47.55)),
            RoadLocation("bin-a", GeoLocation(7.59, 47.55)),
        ),
    )
    plan = CollectionPlanResult(
        CollectionPlanStatus.FEASIBLE,
        solver_result=PlanningResult(
            PlanningStatus.FEASIBLE,
            stops=("bin-a",),
            route_nodes=("depot", "bin-a", "depot"),
        ),
    )

    geometry = build_route_geometry(plan, costs, artifact)

    assert geometry.positions[0].snapped.longitude == pytest.approx(7.58, abs=1e-6)
    assert geometry.legs[0].geometry[0] == pytest.approx((7.58, 47.55), abs=1e-6)


@pytest.mark.parametrize(
    "status",
    [
        CollectionPlanStatus.NO_ACTIONABLE_BINS,
        CollectionPlanStatus.NO_ROUTING_READY_CANDIDATES,
        CollectionPlanStatus.INVALID_REQUEST,
        CollectionPlanStatus.INFEASIBLE,
        CollectionPlanStatus.SOLVER_ERROR,
    ],
)
def test_non_feasible_statuses_serialize_without_route(status):
    artifact = _artifact()
    bins = (BinMetadata("bin-a", location=GeoLocation(7.59, 47.55)),)
    locations = (
        RoadLocation("depot", GeoLocation(7.58, 47.55)),
        RoadLocation("bin-a", GeoLocation(7.59, 47.55)),
    )
    costs = _road_costs(artifact, locations)
    request = _request(costs.costs, bins)
    solver_result = (
        PlanningResult(PlanningStatus.SOLVER_ERROR, diagnostics=("controlled",))
        if status == CollectionPlanStatus.SOLVER_ERROR
        else None
    )
    result = CollectionPlanResult(status, solver_result=solver_result)

    payload = serialize_collection_plan(request, result)

    assert payload["status"] == status.value
    assert "road_route" not in payload
    assert payload["stops"] == []
    json.dumps(payload, allow_nan=False)


def test_feasible_export_has_wgs84_positions_route_and_provenance():
    artifact = _artifact()
    bins = (BinMetadata("bin-a", location=GeoLocation(7.59, 47.55)),)
    locations = (
        RoadLocation("depot", GeoLocation(7.58, 47.55)),
        RoadLocation("bin-a", GeoLocation(7.59, 47.55)),
    )
    costs = _road_costs(artifact, locations)
    request = _request(costs.costs, bins)
    result = CollectionPlanResult(
        CollectionPlanStatus.FEASIBLE,
        solver_result=PlanningResult(
            PlanningStatus.FEASIBLE,
            stops=("bin-a",),
            route_nodes=("depot", "bin-a", "depot"),
            loads_after_stop=(1,),
        ),
    )

    payload = json.loads(
        encode_collection_plan(request, result, road_costs=costs, artifact=artifact)
    )

    assert payload["road_route"]["crs"] == "EPSG:4326"
    assert payload["positions"][0]["original"] == {"longitude": 7.58, "latitude": 47.55}
    assert payload["road_route"]["physical_distance"]["unit"] == "m"
    assert payload["provenance"]["road"]["objective"] == "distance"


def test_export_rejects_non_finite_values():
    artifact = _artifact()
    bins = (BinMetadata("bin-a", location=GeoLocation(7.59, 47.55)),)
    costs = _road_costs(
        artifact,
        (
            RoadLocation("depot", GeoLocation(7.58, 47.55)),
            RoadLocation("bin-a", GeoLocation(7.59, 47.55)),
        ),
    )
    request = _request(costs.costs, bins)
    result = CollectionPlanResult(
        CollectionPlanStatus.FEASIBLE,
        solver_result=PlanningResult(
            PlanningStatus.FEASIBLE,
            route_nodes=("depot", "bin-a", "depot"),
            stops=("bin-a",),
            objective_value=float("nan"),
        ),
    )

    with pytest.raises(ValueError, match="non-finite"):
        serialize_collection_plan(request, result, road_costs=costs, artifact=artifact)
