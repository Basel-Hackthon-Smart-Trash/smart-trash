# Routing Component Stage 1

Stage 1 establishes the Python routing foundation in `code/routing/`.
It contains immutable normalized models, structural validation, provider
protocols, and synthetic unit tests.

## Development

The component is managed independently with uv:

```text
cd code/routing
uv sync
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

The package supports Python `>=3.12,<3.16`. It has no runtime dependencies;
pytest and Ruff are development dependencies. Tests use synthetic fixtures and
do not read the repository GeoJSON asset or connect to external services.

## Integration boundary

Future metadata and observation adapters must translate their source-specific
representations into `smart_bin_routing.models`. In particular:

- `BinMetadata.bin_id` is an internal identifier; an OSM identifier is not
  automatically an operational identifier.
- `FillObservation.fill_fraction` is a finite normalized value in `[0, 1]`.
- `FillObservation.observed_at` must be timezone-aware.
- Collection demand must be supplied in the configured unit or produced by a
  later explicitly configured estimation policy.
- Missing values are not converted to zero or to the current timestamp.

Future travel providers must return `TravelCostMatrix` with explicit node
ordering, declared distance units, and `None` for unavailable connections.
The routing core will not consume OSMnx graph objects directly.

## Prototype assumption

The project-specific prototype configuration uses the modeled round trip:

```text
kva-basel -> selected collection stops -> kva-basel
```

`kva-basel` describes KVA Basel, Hagenaustrasse 40, 4056 Basel. The address is
not geocoded, and vehicle access is not confirmed. A later geographic stage
must confirm the vehicle-access point and road-network snapping before real
travel costs are generated.

No capacity, threshold, freshness, or demand-estimation defaults are claimed.

## Deliberately deferred

Classification behavior, demand estimation, OR-Tools optimization, GeoJSON and
OSMnx adapters, route geometry, backend delivery, MQTT, databases, and service
endpoints belong to later stages.
