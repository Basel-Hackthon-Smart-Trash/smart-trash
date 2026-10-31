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

## Stage 3: planning-input assembly

Stage 3 adds `assemble_planning_input` and the immutable
`PlanningInput`/`RoutingCandidate` models. It prepares solver-independent inputs
but does not optimize or generate routes.

The boundary contains the explicit planning timestamp, configured depot identity,
stable bin identities, each bin's `FillClassification`, supplied
`CollectionDemand`, truck capacity and demand unit, and the unchanged
`TravelCostMatrix`. Candidate order follows classified-bin order. The travel
matrix retains its provider-supplied `node_ids` order and is never silently
reordered. Distance and duration matrices require their respective explicit
units; asymmetric values are allowed.

Classification and route readiness remain separate. Unknown classifications are
kept visible through a `unknown_classification_sensor_check` diagnostic and are
excluded from candidates pending sensor review. This does not declare a sensor
fault; sensor-health correlation and quality semantics require later historical
or backend inputs. Missing demand and bins absent from the travel-cost node
ordering are explicit exclusions. Missing demand is never treated as zero, and
fill fraction is never converted into demand.

An oversized candidate is preserved with its supplied demand and a
`demand_exceeds_truck_capacity` diagnostic. No split collection or extra trip is
created. A malformed matrix or missing depot node blocks assembly. A `None`
matrix cell is a valid explicitly unreachable connection and remains distinct
from malformed dimensions or missing node identities; route feasibility through
other nodes is a future solver responsibility.

Synthetic tests use arbitrary `synthetic-*` identities and costs only. They are
test data, not measurements for KVA Basel or actual bins. Real geographic,
backend, sensor-health, and demand-estimation adapters remain deferred.

Example:

```python
classified = classify_snapshot(snapshot, config, planning_time)
assembly = assemble_planning_input(classified, synthetic_costs)
assert assembly.valid
assert assembly.planning_input.candidates[0].bin_id == "synthetic-bin-1"
```

Stage 3 checks:

```text
cd code/routing
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

Before real-data integration, the project still needs confirmed vehicle-access
depot mapping, a travel-cost provider and units, demand semantics, and explicit
sensor-quality/history requirements.

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
