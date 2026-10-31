# Routing G2: OSMnx Graph Acquisition and Persistence

## Session Handoff

G2 is implemented on branch `feat/routing-algo`. No live OpenStreetMap graph
download was executed; the online check remains gated on explicit approval and
approved Basel area, depot, coverage, and speed settings.

## Changed Files And Public Symbols

- `code/routing/pyproject.toml`: adds `osmnx>=2.0,<3.0`.
- `code/routing/uv.lock`: resolves OSMnx 2.1.1 and its dependencies.
- `code/routing/src/smart_bin_routing/adapters/osmnx_graph.py`: adds
  `GraphArea`, `GraphSettings`, `GraphProvenance`, `GraphArtifact`,
  `GraphError`, `acquire_graph`, `add_edge_travel_times`, `save_graph`, and
  `load_graph`, plus explicit `acquire` and offline `load` commands.
- `code/routing/src/smart_bin_routing/adapters/__init__.py` and
  `src/smart_bin_routing/__init__.py`: export the G2 symbols.
- `code/routing/tests/test_osmnx_graph.py`: synthetic directed graph and cache
  tests.
- `code/routing/README.md`: exact acquisition and reuse commands.

## Contracts And Policies

`GraphArea` stores a WGS84 polygon and explicit meter margin. `from_bbox` is a
convenience for an explicitly supplied area; the caller must supply a Basel
boundary/bounding box and all bin/depot coordinates. Coverage is checked before
acquisition. A positive margin intentionally permits nearby roads outside the
municipal boundary so border paths are not truncated.

`GraphSettings` makes driving network type, OSMnx filter/construction settings,
tagged speed mappings, and optional speed fallback explicit. The approved demo
policy is to use valid OSM speed tags first, use synthetic `40 km/h` only for
missing speeds inside the base Basel area, and reject missing speeds in the
outer margin. OSMnx's implicit mean-speed imputation is not used. Every
persisted edge must have finite positive `length`, `speed_kph`, and
`travel_time` attributes. Missing or invalid values raise `GraphError`.

`save_graph` writes a GraphML artifact and JSON sidecar. Provenance contains the
schema version, SHA-256 of the GraphML bytes, UTC acquisition time, area,
settings, and Python/OSMnx/NetworkX/package versions. `load_graph` verifies the
files, hash, schema, and optional expected area/settings. It never downloads or
uses an alternate asset. The reusable graph identity is the artifact hash; a
future matching/matrix request identity remains separate and is not created in
G2.

The adapter owns OSMnx objects. The source-independent optimizer still consumes
only normalized contracts and `TravelCostMatrix` through the existing boundary.
G2 does not snap bins, geocode the depot, generate geometry, create demands, or
mark bins emptied.

## Verification

Executed from `code/routing/`:

- `uv add 'osmnx>=2.0,<3.0'`: passed; resolved OSMnx 2.1.1 on Python 3.14.2.
- `uv run python -c ...`: passed; OSMnx 2.1.1 and OR-Tools 9.15.6755 import.
- `uv run pytest tests/test_osmnx_graph.py`: passed, 10 tests including the
  explicit speed-policy coverage.
- `uv run pytest`: passed, 122 tests; 3 pre-existing dependency deprecation
  warnings were emitted.
- `uv run ruff check src/smart_bin_routing/adapters/osmnx_graph.py tests/test_osmnx_graph.py`: passed.
- `uv run ruff format --check src/smart_bin_routing/adapters/osmnx_graph.py tests/test_osmnx_graph.py`: passed.
- `uv run ruff check .`: passed.
- `uv run ruff format --check .`: passed; 28 files were already formatted.

There are no generated graph artifacts. Tests use synthetic data only. The real
bin GeoJSON remains source data, but it was not used to acquire a graph.

## Limitations And Next Session

- A live graph download needs explicit approval plus a real Basel area, accepted
  depot coordinate, bin coverage coordinates, and approved speed policy.
- The CLI takes an explicit bounding box; it does not fetch or infer a Basel
  administrative boundary.
- G2 does not perform node matching or produce directed route cost matrices.

Next session is G3: matching and directed road-cost matrices. Read this handoff,
`osmnx_graph.py`, `contracts.py`, the bin GeoJSON adapter, and Git status first.
