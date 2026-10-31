# Routing Component Stages 1 and 2

Stage 1 establishes the Python routing foundation in `code/routing/`.
Stage 2 adds deterministic fill classification and contextual observation
validation. The component contains immutable normalized models, structural
validation, provider protocols, classification results, and synthetic tests.

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

## Stage 2 classification flow

The public flow is:

```text
PlanningSnapshot + PlanningConfig + explicit planning time
    -> Stage 1 structural validation
    -> contextual observation assessment
    -> one classified entry per known bin
```

Fill values are normalized fractions in `[0, 1]`. Classification uses the
exact boundaries `green < yellow_threshold`, `yellow_threshold <= fill <
red_threshold`, and `red >= red_threshold`. Thresholds, maximum observation
age, and allowed future skew are explicit configuration values, not validated
operational settings.

The maximum-age boundary is inclusive: an observation exactly at the maximum
age is usable, while an older observation is `unknown` with
`stale_observation`. A future observation is usable through the inclusive
`allowed_future_skew_seconds` boundary and becomes `unknown` with
`future_observation` beyond it. Missing observations remain in the output as
`unknown` with `missing_observation`. All contextual comparisons use
timezone-aware timestamps and the supplied planning time; the system clock is
never consulted.

Structural errors are kept in the returned validation report and prevent
classified entries from being generated. Contextual problems in an otherwise
valid snapshot are per-bin diagnostics. Color classification is separate from
collection demand and future route selection; a red bin does not imply a route
stop or fabricated demand.

No observation quality/status semantics exist in the normalized Stage 1 model.
How backend sensor-quality fields should affect usability remains an explicit
integration question for a later stage.

## Deliberately deferred

Demand estimation, OR-Tools optimization, GeoJSON and OSMnx adapters, route
geometry, backend delivery, MQTT, databases, sensor-quality semantics, and
service endpoints belong to later stages.
