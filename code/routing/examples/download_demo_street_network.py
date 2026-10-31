"""Explicitly download and export a small OSMnx street background for the demo.

Run manually from ``code/routing/``. This is the demo's only network action::

    uv run python examples/download_demo_street_network.py

The downloaded graph is used only as visual background data. It is not passed
through the routing speed contract or used as the demo's route-cost provider,
and the generated route remains explicitly synthetic.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from pyproj import CRS, Transformer
from shapely.geometry import LineString, Polygon, mapping

from smart_bin_routing import GraphArea, load_bin_geojson
from smart_bin_routing.adapters.depot_geocoding import load_depot_location

STREET_FILE_NAME = "real-bin-demo-streets.geojson"
# Keep the graph inside the explicitly covered bin area. The SVG adds visual
# padding itself; no speed fallback is claimed outside this area.
DISPLAY_MARGIN_METERS = 0


def _node_xy(graph: Any, node: Any) -> tuple[float, float]:
    return float(graph.nodes[node]["x"]), float(graph.nodes[node]["y"])


def _edge_geometry(graph: Any, source: Any, target: Any, data: Any) -> LineString:
    geometry = data.get("geometry")
    if geometry is not None and hasattr(geometry, "coords"):
        coordinates = [(float(x), float(y)) for x, y in geometry.coords]
        if len(coordinates) >= 2:
            return LineString(coordinates)
    return LineString((_node_xy(graph, source), _node_xy(graph, target)))


def _as_wgs84(graph: Any, geometry: LineString) -> LineString:
    source_crs = CRS.from_user_input(graph.graph["crs"])
    transformer = Transformer.from_crs(source_crs, "EPSG:4326", always_xy=True)
    return LineString(transformer.itransform(geometry.coords))


def _area_from_bins(bins: tuple[Any, ...], extra_locations: tuple[Any, ...] = ()) -> GraphArea:
    locations = [item.location for item in bins if item.location is not None]
    locations.extend(extra_locations)
    longitudes = [item.longitude for item in locations]
    latitudes = [item.latitude for item in locations]
    if not longitudes or not latitudes:
        raise ValueError("the approved bin asset contains no coordinates")
    west, east = min(longitudes), max(longitudes)
    south, north = min(latitudes), max(latitudes)
    return GraphArea.from_bbox(
        west,
        south,
        east,
        north,
        margin_meters=DISPLAY_MARGIN_METERS,
    )


def _street_payload(graph: Any) -> dict[str, object]:
    features = []
    for source, target, key, data in graph.edges(keys=True, data=True):
        geometry = _as_wgs84(graph, _edge_geometry(graph, source, target, data))
        coordinates = list(geometry.coords)
        if len(coordinates) < 2 or any(
            not math.isfinite(value) for point in coordinates for value in point
        ):
            continue
        features.append(
            {
                "type": "Feature",
                "properties": {"source": str(source), "target": str(target), "key": str(key)},
                "geometry": mapping(geometry),
            }
        )
    return {
        "type": "FeatureCollection",
        "features": features,
        "properties": {
            "data_status": "REAL_OPENSTREETMAP_STREET_NETWORK",
            "crs": "EPSG:4326",
            "route_status": "NOT_USED_FOR_DEMO_COSTS",
            "attribution": "© OpenStreetMap contributors",
        },
    }


def main() -> None:
    root = Path(__file__).resolve().parents[3]
    output_dir = Path(__file__).resolve().parent
    bins = load_bin_geojson(root / "assets/geojson/bin-locations.geojson")
    depot_record_path = root / "code/routing/.cache/stadtreinigung-basel.json"
    if not depot_record_path.is_file():
        raise ValueError("accepted Stadtreinigung depot geocode is required")
    depot_record = load_depot_location(depot_record_path)
    area = _area_from_bins(bins, (depot_record.location,))
    import osmnx as ox

    polygon = Polygon(area.polygon_coordinates[0])
    graph = ox.graph_from_polygon(polygon, network_type="drive", simplify=True, retain_all=True)
    street_path = output_dir / STREET_FILE_NAME
    street_path.write_text(json.dumps(_street_payload(graph), indent=2) + "\n", encoding="utf-8")
    print(f"saved street background: {street_path}")
    print("street data: REAL OpenStreetMap; route costs: SIMULATED")


if __name__ == "__main__":
    main()
