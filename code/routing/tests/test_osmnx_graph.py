from pathlib import Path

import networkx as nx
import pytest

from smart_bin_routing import (
    GeoLocation,
    GraphArea,
    GraphError,
    GraphSettings,
    add_edge_travel_times,
    load_graph,
    save_graph,
)


def synthetic_graph() -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph()
    graph.graph["crs"] = "EPSG:4326"
    graph.add_node(1, x=7.58, y=47.55)
    graph.add_node(2, x=7.59, y=47.56)
    graph.add_edge(1, 2, key=0, length=100.0, speed_kph=30.0)
    graph.add_edge(2, 1, key=0, length=120.0, speed_kph=20.0)
    return add_edge_travel_times(graph, GraphSettings())


def area() -> GraphArea:
    return GraphArea.from_bbox(7.57, 47.54, 7.60, 47.57, margin_meters=250)


def test_graph_persistence_round_trip(tmp_path: Path):
    artifact = save_graph(synthetic_graph(), tmp_path, area=area(), settings=GraphSettings())

    loaded = load_graph(tmp_path, expected_area=area(), expected_settings=GraphSettings())

    assert loaded.provenance.graph_sha256 == artifact.provenance.graph_sha256
    assert loaded.graph_path.name == "graph.graphml"
    assert loaded.graph.number_of_edges() == 2
    for _, _, data in loaded.graph.edges(data=True):
        assert float(data["length"]) > 0
        assert float(data["speed_kph"]) > 0
        assert float(data["travel_time"]) > 0


def test_graph_area_requires_coverage():
    with pytest.raises(GraphError, match="does not cover"):
        from smart_bin_routing.adapters.osmnx_graph import _validate_coverage

        _validate_coverage(area(), (GeoLocation(8.0, 47.0),))


def test_load_graph_does_not_download_when_cache_is_missing(tmp_path: Path):
    with pytest.raises(GraphError, match="incomplete"):
        load_graph(tmp_path)


def test_load_graph_rejects_changed_graph(tmp_path: Path):
    save_graph(synthetic_graph(), tmp_path, area=area(), settings=GraphSettings())
    graph_path = tmp_path / "graph.graphml"
    graph_path.write_text(graph_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(GraphError, match="hash"):
        load_graph(tmp_path)


def test_load_graph_rejects_mismatched_settings(tmp_path: Path):
    save_graph(synthetic_graph(), tmp_path, area=area(), settings=GraphSettings())

    with pytest.raises(GraphError, match="settings"):
        load_graph(tmp_path, expected_settings=GraphSettings(network_type="walk"))


def test_missing_speed_requires_explicit_imputation():
    graph = nx.MultiDiGraph()
    graph.graph["crs"] = "EPSG:4326"
    graph.add_node(1, x=7.58, y=47.55)
    graph.add_node(2, x=7.59, y=47.56)
    graph.add_edge(1, 2, length=100.0)

    with pytest.raises(GraphError, match="no accepted speed"):
        add_edge_travel_times(graph, GraphSettings())


def test_missing_speed_uses_explicit_urban_fallback():
    graph = nx.MultiDiGraph()
    graph.graph["crs"] = "EPSG:4326"
    graph.add_node(1, x=7.58, y=47.55)
    graph.add_node(2, x=7.59, y=47.56)
    graph.add_edge(1, 2, length=100.0)
    settings = GraphSettings(speed_fallback_kph=40.0, speed_fallback_scope="base_area_only")

    add_edge_travel_times(graph, settings, fallback_area=area())

    assert graph.edges[1, 2, 0]["speed_kph"] == 40.0


def test_missing_speed_outside_urban_fallback_fails():
    graph = nx.MultiDiGraph()
    graph.graph["crs"] = "EPSG:4326"
    graph.add_node(1, x=7.70, y=47.60)
    graph.add_node(2, x=7.71, y=47.61)
    graph.add_edge(1, 2, length=100.0)
    settings = GraphSettings(speed_fallback_kph=40.0, speed_fallback_scope="base_area_only")

    with pytest.raises(GraphError, match="outside the fallback area"):
        add_edge_travel_times(graph, settings, fallback_area=area())


def test_tagged_speed_wins_over_fallback():
    graph = nx.MultiDiGraph()
    graph.graph["crs"] = "EPSG:4326"
    graph.add_node(1, x=7.58, y=47.55)
    graph.add_node(2, x=7.59, y=47.56)
    graph.add_edge(1, 2, length=100.0, maxspeed="30 km/h")
    settings = GraphSettings(speed_fallback_kph=40.0, speed_fallback_scope="base_area_only")

    add_edge_travel_times(graph, settings, fallback_area=area())

    assert graph.edges[1, 2, 0]["speed_kph"] == 30.0


def test_multi_value_tagged_speed_uses_conservative_lowest_value():
    graph = nx.MultiDiGraph()
    graph.graph["crs"] = "EPSG:4326"
    graph.add_node(1, x=7.58, y=47.55)
    graph.add_node(2, x=7.59, y=47.56)
    graph.add_edge(1, 2, length=100.0, maxspeed=["80", "100"])
    settings = GraphSettings(speed_fallback_kph=40.0, speed_fallback_scope="base_area_only")

    add_edge_travel_times(graph, settings, fallback_area=area())

    assert graph.edges[1, 2, 0]["speed_kph"] == 80.0


def test_import_and_default_graph_functions_do_not_acquire():
    import osmnx as ox

    original = ox.graph_from_polygon
    ox.graph_from_polygon = lambda *args, **kwargs: pytest.fail("unexpected download")
    try:
        assert GraphSettings().network_type == "drive"
    finally:
        ox.graph_from_polygon = original
