# Routing G3: Matching and Directed Road Costs

## Session Handoff

G3 is implemented on branch `feat/routing-algo`. The worktree was clean before
the session. No network command, graph acquisition, or generated operational
artifact was used.

## Changed Files And Public Symbols

- `code/routing/src/smart_bin_routing/adapters/road_costs.py`: adds
  `RoadLocation`, `MatchingConfig`, `LocationMatch`, `MatchingResult`,
  `DirectedPath`, `RoadCostProvenance`, `RoadCostResult`, `RoadCostMetric`,
  `UnusableMatchPolicy`, `match_locations`, and `build_road_costs`.
- `code/routing/src/smart_bin_routing/contracts.py`: `TravelCostMatrix` now
  accepts validated provenance key/value pairs.
- `code/routing/src/smart_bin_routing/__init__.py` and
  `adapters/__init__.py`: export the G3 symbols.
- `code/routing/tests/test_road_costs.py`: seven offline synthetic graph tests.

## Verified Contracts And Call Flow

The caller loads a `GraphArtifact` using the existing offline `load_graph`
boundary, creates explicit `RoadLocation` records, supplies a
`MatchingConfig`, and calls `build_road_costs`. The result contains the existing
location-keyed `TravelCostMatrix`, keyed `DirectedPath` records, all matching
records, and `RoadCostProvenance`. The optimizer can consume
`result.costs` without seeing NetworkX or OSMnx objects.

Location IDs are caller identities and remain separate from graph node IDs.
The requested location order is preserved exactly, including a depot at any
matrix index. Multiple locations may map to one graph node and produce valid
zero-length paths. Unavailable directed pairs remain `None`; they are not
replaced by straight-line values or zero.

Input coordinates are WGS84 longitude/latitude, matching the G1 GeoJSON and
accepted depot record contracts. The graph must declare a valid CRS. Matching
transforms coordinates into graph CRS for nearest-node selection and uses WGS84
geodesic distance for physical snap distance in meters. The maximum snap
distance is required from the caller; there is no operational default.

`UnusableMatchPolicy.REJECT` blocks matrix construction when a mandatory match
is excessive or otherwise unusable. `REPORT` preserves the match diagnostic and
leaves affected matrix cells unavailable, so no location is silently dropped.

Paths are directed and contain ordered `(source, target, key)` edges. The
configured `RoadCostMetric` selects the shortest path. Parallel-edge and equal
cost ties use deterministic graph-node/key ordering. Distance and duration are
both summed over that same selected edge sequence. Searches are cached by
unique source/target graph-node pair, so shared graph nodes do not cause
duplicate searches.

Provenance binds graph SHA-256, matching configuration, depot identity, location
ordering, objective, and declared units. The graph hash comes from the persisted G2
`GraphArtifact`; the provider does not download or substitute another graph.

## Verification

Executed from `code/routing/`:

- `uv run pytest tests/test_road_costs.py`: passed, 7 tests.
- `uv run pytest`: passed, 128 tests; 3 pre-existing dependency deprecation
  warnings were emitted.
- `uv run ruff check .`: passed.
- `uv run ruff format --check .`: passed; 30 files were already formatted.

The tests use synthetic in-memory graphs only. The approved real asset remains
`assets/geojson/bin-locations.geojson`; it was not used as operational routing
input and no real fill, demand, speed, depot access, or route result was
fabricated.

## Limitations And Approvals

- A real graph still requires explicit acquisition approval and approved area,
  depot coordinate, coverage points, and speed policy.
- The caller must choose and approve the maximum physical snap distance.
- Matching is nearest-node approximation; it does not model driveway access,
  curb position, service time, traffic, or turn restrictions beyond the loaded
  directed graph.
- `REPORT` mode intentionally produces incomplete matrices; callers must treat
  the diagnostics as part of the request result.
- G3 does not reconstruct geometry, serialize route exports, mark bins emptied,
  add optional stops, or change optimizer collection policy.

## Next Session: G4

Implement geometry reconstruction and frontend export only. Read this handoff,
`adapters/road_costs.py`, `contracts.py`, `adapters/osmnx_graph.py`, and current
Git status first. Reuse `DirectedPath.keyed_edges`; do not re-run matching or
select a different path while generating geometry.
