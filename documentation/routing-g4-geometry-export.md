# Routing G4: Route Geometry And Frontend Payload

## Session Handoff

G4 is implemented on branch `feat/routing-algo`. The worktree context and
existing G3 changes were preserved. No graph was downloaded and no network
operation is performed by the geometry or export adapters.

## Changed Files And Public Symbols

- `code/routing/src/smart_bin_routing/adapters/route_geometry.py`: adds
  `RoutePosition`, `RouteLeg`, `RouteGeometry`, `RouteGeometryError`, and
  `build_route_geometry`.
- `code/routing/src/smart_bin_routing/adapters/route_export.py`: adds
  `EXPORT_SCHEMA_VERSION`, `RouteExportError`, `serialize_collection_plan`,
  and `encode_collection_plan`.
- `code/routing/src/smart_bin_routing/__init__.py` and
  `adapters/__init__.py`: export the G4 symbols.
- `code/routing/tests/test_route_geometry_export.py`: synthetic geometry and
  serialization acceptance tests.

## Verified Call Flow And Contracts

The caller first invokes the existing `plan_collection` boundary. For a
feasible result, it supplies the same loaded `GraphArtifact` and
`RoadCostResult` that were used to create the request's costs:

```text
CollectionPlanRequest + plan_collection
  -> CollectionPlanResult
  -> build_route_geometry(plan, road_costs, graph_artifact)
  -> serialize_collection_plan(request, result, road_costs, graph_artifact)
  -> encode_collection_plan(...)
```

`build_route_geometry` uses only `PlanningResult.route_nodes` and the matching
G3 `DirectedPath.keyed_edges`. It does not rematch locations, recalculate a
shortest path, or add straight-line connectors. Stored edge shapes are oriented
to the selected directed edge. Edges without a shape use their graph node
coordinates. Same-node legs retain their source and target identities but have
`geometry: null` rather than an invalid one-coordinate LineString.

Graph coordinates are transformed from the graph's declared CRS to WGS84
(`EPSG:4326`) with longitude first. Original caller positions and snapped road
positions are separate fields. Original positions are not replaced by snapped
positions and no off-network connector is emitted.

Physical distance and duration are summed from the selected keyed paths. They
are distinct from the solver objective cost. No service time, unloading total,
skip reason, operational identity, demand, speed, or depot coordinate is
invented.

## Payload Schema Version 1

`serialize_collection_plan` returns only standard JSON-compatible values.
`encode_collection_plan` uses `json.dumps(..., allow_nan=False)` and rejects
non-finite values.

Top-level fields:

- `schema_version`, `request_id`, `plan_id`, and application `status`.
- `diagnostics` and per-bin `assessments`, including classification,
  routing-readiness, inclusion, and diagnostics.
- `stops`, when a solver result supplies ordered collection stops. Each stop
  has sequence, identity, supplied demand when available, and load after stop
  when available.
- `metrics`, containing supplied demand records and configured capacity/unit.
- `solver`, when optimization ran, including solver status, route nodes,
  objective cost/unit, collected demand, loads, diagnostics, and metadata.
- `positions`, only for a feasible route, with separate original and snapped
  WGS84 positions.
- `road_route`, only for a feasible route. Its GeoJSON FeatureCollection uses
  WGS84 LineStrings for non-empty legs and `null` geometry for same-node legs.
  It includes leg distances/durations and total physical distance/time with
  units.
- `provenance`, including supplied cost-matrix provenance and, when provided,
  graph hash/metadata, graph CRS, path objective, matching policy, snapping
  limit, node order, and declared units.

Non-feasible outcomes serialize their actual status and diagnostics without a
fabricated route. Feasible export requires both the exact G3 road-cost result
and the loaded graph artifact.

## Data And Limitations

Tests use synthetic in-memory graphs and values only. The approved real asset
remains `assets/geojson/bin-locations.geojson`; it is not a fill-level,
demand, depot, or route result. No frontend, server, persistence, MQTT, graph
download, optional visit, multiple vehicle, or duration-limit behavior was
added.

## Verification

Executed from `code/routing/`:

- `uv run pytest tests/test_route_geometry_export.py`: passed, 10 tests.
- `uv run pytest`: passed, 139 tests; 3 pre-existing Python/OR-Tools
  deprecation warnings were emitted.
- `uv run ruff check .`: passed.
- `uv run ruff format --check .`: passed.

## Next Session: G5

Run the explicit real-Basel integration only after approving the graph,
depot coordinate, coverage, snapping limit, and speed policy. Read this
handoff, `route_geometry.py`, `route_export.py`, `road_costs.py`,
`orchestration.py`, and current Git status first. Do not treat the synthetic
tests or the bin GeoJSON asset as operational routing input.
