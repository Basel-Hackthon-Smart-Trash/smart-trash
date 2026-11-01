"""Generate a standalone, synthetic-data routing demo from real bin positions.

Run from ``code/routing/`` with::

    uv run python examples/real_bin_subset_demo.py

The generated HTML opens without a web server. Locations are real source data;
fill levels, demands, and travel costs are synthetic and do not represent
verified operations or navigation.
"""

from __future__ import annotations

import json
import math
import random
from datetime import UTC, datetime
from pathlib import Path

from smart_bin_routing import (
    CollectionDemand,
    CollectionPlanRequest,
    FillObservation,
    GeoLocation,
    MatchingConfig,
    PlanningConfig,
    PlanningSnapshot,
    RoadCostMetric,
    RoadLocation,
    build_road_costs,
    build_route_geometry,
    load_graph,
    plan_collection,
)
from smart_bin_routing.adapters.bin_geojson import load_bin_geojson
from smart_bin_routing.adapters.depot_geocoding import load_depot_location
from smart_bin_routing.contracts import TravelCostMatrix

SEED = 20261031
SUBSET_SIZE = 12
DEMO_DEMAND = 1.0
DEMO_DEMAND_UNIT = "synthetic-load-units"
DEPOT_ID = "stadtreinigung-basel"
DEPOT_ADDRESS = "Stadtreinigung (SR), Brüssel-Strasse 22, 4053 Basel, Switzerland"
GRAPH_DIRECTORY_NAME = "real-bin-demo-graph"
MAX_SNAP_DISTANCE_METERS = 300.0
PLANNING_TIME = datetime(2026, 10, 31, 12, 0, tzinfo=UTC)


def _synthetic_costs(locations: dict[str, GeoLocation]) -> TravelCostMatrix:
    """Build deterministic straight-line costs from the modeled locations."""

    node_ids = tuple(locations)
    size = len(node_ids)
    matrix = []
    for source in range(size):
        row = []
        for target in range(size):
            if source == target:
                row.append(0.0)
            else:
                first, second = locations[node_ids[source]], locations[node_ids[target]]
                latitude_delta = math.radians(second.latitude - first.latitude)
                longitude_delta = math.radians(second.longitude - first.longitude)
                haversine = (
                    math.sin(latitude_delta / 2) ** 2
                    + math.cos(math.radians(first.latitude))
                    * math.cos(math.radians(second.latitude))
                    * math.sin(longitude_delta / 2) ** 2
                )
                row.append(2 * 6371 * math.asin(math.sqrt(haversine)))
        matrix.append(tuple(row))
    return TravelCostMatrix(
        node_ids,
        distances=tuple(matrix),
        distance_unit="synthetic-km",
        provenance=(
            ("source", "offline-demo"),
            ("data_status", "SIMULATED"),
            ("geography", "straight_line_coordinates"),
        ),
    )


def _html(payload: dict[str, object]) -> str:
    embedded = json.dumps(payload, allow_nan=False, sort_keys=True)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Smart Trash · Routing Demo</title>
  <style>
    :root {{ color-scheme: dark; font-family: system-ui, sans-serif; }}
    body {{ margin: 0; background: #101719; color: #eef4f1; }}
    main {{ max-width: 1180px; margin: auto; padding: 24px; }}
    header {{ display: flex; justify-content: space-between; gap: 16px; align-items: start; }}
    h1, h2, p {{ margin-top: 0; }}
    .warning {{ background: #493b16; border: 1px solid #e0b84b; color: #ffe8a0;
      padding: 12px 14px; border-radius: 10px; margin: 18px 0; }}
    .layout {{ display: grid; grid-template-columns: minmax(0, 1fr) 330px; gap: 18px; }}
    .panel {{ background: #182326; border: 1px solid #2d3d40; border-radius: 14px; padding: 16px; }}
    svg {{ width: 100%; height: 560px; background: #d9e6dc; border-radius: 10px; }}
    .bin {{ stroke: #102022; stroke-width: 1.5; }}
    .depot {{ stroke: #102022; stroke-width: 2; }}
    .route-number {{ fill: #102022; font: 700 11px system-ui; text-anchor: middle; }}
    .legend, .stats {{ display: grid; gap: 8px; }}
    .legend-row, .stop {{ display: flex; justify-content: space-between; gap: 10px; padding: 8px 0;
      border-bottom: 1px solid #2d3d40; }}
    .dot {{ display: inline-block; width: 12px; height: 12px; border-radius: 50%;
      margin-right: 6px; }}
    .green {{ background: #42b883; }} .yellow {{ background: #e8bc4a; }}
    .red {{ background: #ef6b5b; }} .unknown {{ background: #849397; }}
    .muted {{ color: #a9b9b8; font-size: .9rem; }}
    @media (max-width: 780px) {{ header, .layout {{ display: block; }}
      .panel {{ margin-top: 16px; }} }}
  </style>
</head>
<body>
<main>
  <header>
    <div><p class="muted">SMART TRASH · LOCAL DEMO</p><h1>Collection route</h1></div>
    <p class="muted">Seed: <strong id="seed"></strong></p>
  </header>
  <div class="warning"><strong>DEMO</strong> · real bin locations and street background ·
     simulated fill and demand · route mode shown in the plan · no operational navigation</div>
  <div class="layout">
    <section class="panel"><svg id="map" role="img" aria-label="Bin locations"></svg></section>
    <aside>
      <section class="panel"><h2>Plan</h2><div id="stats" class="stats"></div></section>
      <section class="panel"><h2>Visit order</h2><div id="stops"></div></section>
      <section class="panel"><h2>Fill flags</h2><div class="legend">
        <div><span class="dot green"></span>Green · normal</div>
        <div><span class="dot yellow"></span>Yellow · attention</div>
        <div><span class="dot red"></span>Red · urgent</div>
      </div></section>
    </aside>
  </div>
</main>
<script id="payload" type="application/json">{embedded}</script>
<script>
const data = JSON.parse(document.getElementById('payload').textContent);
const bins = data.bins;
const included = new Map(data.stops.map(stop => [stop.bin_id, stop.sequence]));
document.getElementById('seed').textContent = data.demo.seed;
const stats = document.getElementById('stats');
stats.innerHTML = `<div><strong>${{data.plan.status}}</strong></div>
  <div>${{bins.length}} bins · ${{data.plan.included_bins}} routed</div>
  <div>${{data.plan.collected_demand}} ${{data.plan.demand_unit}}</div>
  <div>Route: ${{data.plan.route_mode}}</div>
  <div class="muted">Objective: ${{data.plan.objective_cost}} ${{data.plan.objective_unit}}</div>`;
const depotLabel = `<div class="stop"><span>START · ${{data.depot.address}}</span>` +
  `<span>DEPOT</span></div>`;
const endLabel = `<div class="stop"><span>END · ${{data.depot.address}}</span>` +
  `<span>DEPOT</span></div>`;
document.getElementById('stops').innerHTML = depotLabel +
  (data.stops.length
    ? data.stops.map(stop => `<div class="stop"><span>${{stop.sequence}}. ${{stop.bin_id}}</span>` +
      `<span>${{stop.fill_percent}}%</span></div>`).join('')
    : '<p class="muted">No route stops</p>') + endLabel;
const svg = document.getElementById('map');
const width = 900, height = 560, pad = 42;
const points = data.depot.location ? [...bins, data.depot.location] : bins;
const lons = points.map(point => point.longitude), lats = points.map(point => point.latitude);
const minLon = Math.min(...lons), maxLon = Math.max(...lons);
const minLat = Math.min(...lats), maxLat = Math.max(...lats);
const x = lon => pad + (lon - minLon) / (maxLon - minLon || 1) * (width - pad * 2);
const y = lat => height - pad - (lat - minLat) / (maxLat - minLat || 1) * (height - pad * 2);
svg.setAttribute('viewBox', `0 0 ${{width}} ${{height}}`);
const streets = data.street_network?.features || [];
const streetLines = streets.map(feature => {{
  const coordinates = feature.geometry.coordinates;
  const points = coordinates.map(([lon, lat]) => `${{x(lon)}},${{y(lat)}}`).join(' ');
  return `<polyline points="${{points}}" fill="none" stroke="#809494" ` +
    `stroke-width="1" opacity=".7"/>`;
}}).join('');
const roadFeatures = data.road_route?.geometry?.features || [];
const roadRouteMarkup = roadFeatures.map(feature => {{
  const coordinates = feature.geometry?.coordinates || [];
  const points = coordinates.map(([lon, lat]) => `${{x(lon)}},${{y(lat)}}`).join(' ');
  return points
    ? `<polyline points="${{points}}" fill="none" stroke="#102022" ` +
      `stroke-width="3" stroke-dasharray="8 5" opacity=".95"/>`
    : '';
}}).join('');
const locations = new Map(bins.map(bin => [bin.bin_id, bin]));
if (data.depot.location) locations.set(data.depot.id, data.depot.location);
const routePoints = data.plan.route_nodes
  .map(nodeId => locations.get(nodeId))
  .filter(Boolean)
  .map(point => `${{x(point.longitude)}},${{y(point.latitude)}}`)
  .join(' ');
const routeMarkup = routePoints
  ? `<polyline points="${{routePoints}}" fill="none" stroke="#102022" ` +
    `stroke-width="3" stroke-dasharray="8 5" opacity=".9"/>`
  : '';
const routeDisplay = roadRouteMarkup || routeMarkup;
const depotMarkup = data.depot.location
  ? (() => {{
    const depotX = x(data.depot.location.longitude), depotY = y(data.depot.location.latitude);
    return `<polygon class="depot" points="${{depotX}},${{depotY - 12}} ` +
      `${{depotX + 12}},${{depotY}} ${{depotX}},${{depotY + 12}} ` +
      `${{depotX - 12}},${{depotY}}" fill="#182326">` +
    `<title>START / END · ${{data.depot.address}}</title></polygon>` +
      `<text class="route-number" x="${{depotX}}" y="${{depotY + 4}}">S/E</text>`;
  }})()
  : `<text x="${{pad}}" y="${{height - 18}}" fill="#294044" font-size="13">` +
    `START / END COORDINATE PENDING ACCEPTED GEOCODE</text>`;
svg.innerHTML = `<text x="${{pad}}" y="24" fill="#294044" font-size="14">` +
  (streets.length
    ? `REAL STREET NETWORK · NO VERIFIED ROUTE`
    : `REAL BIN POSITIONS · NO STREET DATA`) +
  `</text>` + streetLines + routeDisplay + depotMarkup +
  bins.map(bin => {{
    const sequence = included.get(bin.bin_id);
    const cx = x(bin.longitude), cy = y(bin.latitude);
    const circle = `<circle class="bin ${{bin.classification}}" cx="${{cx}}" ` +
      `cy="${{cy}}" r="${{sequence ? 13 : 9}}" fill="${{bin.color}}">` +
      `<title>${{bin.bin_id}} · ${{bin.fill_percent}}% · ${{bin.classification}}</title></circle>`;
    return circle + (sequence
      ? `<text class="route-number" x="${{cx}}" y="${{cy + 4}}">${{sequence}}</text>`
      : '');
  }}).join('');
</script>
</body>
</html>
"""


def main() -> None:
    root = Path(__file__).resolve().parents[3]
    output_dir = Path(__file__).resolve().parent
    bins = load_bin_geojson(root / "assets/geojson/bin-locations.geojson")
    selected = tuple(random.Random(SEED).sample(bins, SUBSET_SIZE))
    selected = tuple(sorted(selected, key=lambda item: item.bin_id))
    rng = random.Random(SEED)
    observations = tuple(
        FillObservation(item.bin_id, round(rng.uniform(0.2, 0.98), 2), PLANNING_TIME)
        for item in selected
    )
    demands = tuple(
        CollectionDemand(item.bin_id, DEMO_DEMAND, DEMO_DEMAND_UNIT) for item in selected
    )
    depot_record_path = root / "code/routing/.cache/stadtreinigung-basel.json"
    depot_record = load_depot_location(depot_record_path) if depot_record_path.is_file() else None
    if depot_record is None:
        raise ValueError("accepted depot geocode is required for geographic demo costs")
    locations = {DEPOT_ID: depot_record.location}
    locations.update({item.bin_id: item.location for item in selected if item.location is not None})
    node_ids = (DEPOT_ID, *(item.bin_id for item in selected))
    graph_directory = output_dir.parent / ".cache" / GRAPH_DIRECTORY_NAME
    road_costs = None
    route_geometry = None
    if graph_directory.is_dir():
        graph_artifact = load_graph(graph_directory)
        road_costs = build_road_costs(
            graph_artifact,
            tuple(RoadLocation(node_id, locations[node_id]) for node_id in node_ids),
            depot_id=DEPOT_ID,
            matching=MatchingConfig(MAX_SNAP_DISTANCE_METERS),
            objective=RoadCostMetric.DISTANCE,
        )
        travel_costs = road_costs.costs
    else:
        travel_costs = _synthetic_costs({node_id: locations[node_id] for node_id in node_ids})
    request = CollectionPlanRequest(
        PlanningSnapshot(selected, observations, demands),
        PlanningConfig(DEPOT_ID, DEPOT_ID, 20, DEMO_DEMAND_UNIT, 0.6, 0.8, 3600),
        PLANNING_TIME,
        travel_costs,
    )
    result = plan_collection(request)
    if road_costs is not None and result.status.value == "feasible":
        route_geometry = build_route_geometry(result, road_costs, graph_artifact)
    assessments = {item.bin_id: item for item in result.bins}
    fills = {
        item.bin_id: observation.fill_fraction for item, observation in zip(selected, observations)
    }
    colors = {"green": "#42b883", "yellow": "#e8bc4a", "red": "#ef6b5b", "unknown": "#849397"}
    sequence = {bin_id: index + 1 for index, bin_id in enumerate(result.stops)}
    payload = {
        "demo": {"seed": SEED, "subset_size": SUBSET_SIZE, "data_status": "SIMULATED"},
        "depot": {
            "id": DEPOT_ID,
            "address": DEPOT_ADDRESS,
            "data_status": "REAL_ADDRESS_MODELED",
            "vehicle_access_confirmed": False,
            "coordinate_status": "ACCEPTED_GEOCODE" if depot_record else "NOT_ACCEPTED",
            "location": (
                {
                    "longitude": depot_record.location.longitude,
                    "latitude": depot_record.location.latitude,
                }
                if depot_record
                else None
            ),
        },
        "street_network": None,
        "plan": {
            "status": result.status.value,
            "route_nodes": list(result.route_nodes),
            "included_bins": len(result.stops),
            "collected_demand": (
                result.solver_result.collected_demand if result.solver_result else None
            ),
            "demand_unit": DEMO_DEMAND_UNIT,
            "objective_cost": (
                result.solver_result.total_travel_cost if result.solver_result else None
            ),
            "objective_unit": (
                result.solver_result.travel_cost_unit if result.solver_result else None
            ),
            "route_mode": (
                "REAL_ROAD_NETWORK" if road_costs is not None else "SIMULATED_STRAIGHT_LINE"
            ),
        },
        "bins": [
            {
                "bin_id": item.bin_id,
                "longitude": item.location.longitude,
                "latitude": item.location.latitude,
                "fill_percent": round(fills[item.bin_id] * 100),
                "classification": assessments[item.bin_id].classification.value,
                "color": colors[assessments[item.bin_id].classification.value],
                "routing_ready": assessments[item.bin_id].routing_ready,
                "included_in_route": assessments[item.bin_id].included_in_route,
            }
            for item in selected
        ],
        "stops": [
            {
                "sequence": sequence[item.bin_id],
                "bin_id": item.bin_id,
                "fill_percent": round(fills[item.bin_id] * 100),
            }
            for item in selected
            if item.bin_id in sequence
        ],
        "road_route": (
            {
                "data_status": "REAL_OPENSTREETMAP_GRAPH",
                "geometry": {
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "properties": {
                                "source_id": leg.source_id,
                                "target_id": leg.target_id,
                                "distance_meters": leg.distance_meters,
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
                        for leg in route_geometry.legs
                    ],
                },
                "physical_distance": {"value": route_geometry.distance_meters, "unit": "m"},
            }
            if route_geometry is not None
            else None
        ),
        "diagnostics": [item.code for item in result.diagnostics],
        "limitations": [
            "real bin locations are used",
            "fill levels, demands, and travel costs are simulated",
            "street background is real; fill levels and demands are simulated",
            "road mode uses real OSM geometry with modeled speed assumptions",
            f"location snapping limit is {MAX_SNAP_DISTANCE_METERS:.0f} m",
            "the depot address is not proof of vehicle access or unloading permission",
        ],
    }
    street_path = output_dir / "real-bin-demo-streets.geojson"
    if street_path.is_file():
        payload["street_network"] = json.loads(street_path.read_text(encoding="utf-8"))
    payload_path = output_dir / "real-bin-demo-payload.json"
    html_path = output_dir / "real-bin-demo.html"
    payload_path.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    html_path.write_text(_html(payload), encoding="utf-8")
    print(f"wrote {payload_path}")
    print(f"wrote {html_path}")
    print(f"status: {result.status.value}; route stops: {result.stops}")


if __name__ == "__main__":
    main()
