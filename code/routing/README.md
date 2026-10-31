# Smart Bin Routing

Stages 1 and 2 provide source-independent Python contracts, structural
validation, and deterministic contextual fill classification. Stage 3 assembles
validated planning inputs, and Stage 4 provides a bounded OR-Tools optimizer
for one mandatory-visit truck trip. G1 adds an offline GeoJSON adapter for the
approved bin export; it does not use OSMnx or connect to a backend.

Stage 5 adds `plan_collection`, an application-level composition of
classification, planning-input assembly, and route optimization. It accepts
one coherent caller-supplied snapshot and returns classifications, readiness
and exclusion diagnostics, plus the existing solver result. It does not own
MQTT, snapshot state, persistence, scheduling, or result transport. See
`../../documentation/routing-stage-5.md` and
`../../documentation/routing-stage-6.md`.

## Development

From this directory:

```text
uv sync
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

Run the deterministic offline orchestration example with:

```text
uv run python examples/stage5_collection_plan.py
```

The example uses synthetic observations, explicit test demands, and
approximate `synthetic-km` costs. It does not represent verified navigation
or real Stadtreinigung Basel travel distances.

The package supports Python 3.12 through 3.15. OR-Tools is the routing runtime
dependency; Pytest and Ruff are development dependencies.

## Bin GeoJSON adapter

Load the approved export without involving the optimizer:

```python
from smart_bin_routing import load_bin_geojson

bins = load_bin_geojson("../../assets/geojson/bin-locations.geojson")
```

The adapter accepts CRS-omitted WGS84 GeoJSON `Point` features, uses the stable
feature ID as `bin_id`, retains the original position and source ID, and sorts
the result by ID. It rejects unsupported CRS declarations, malformed geometry,
invalid coordinates, missing or duplicate identities, and ID mismatches. It
does not create observations, demand, or snapped network positions. See
`../../documentation/routing-g1-bin-geojson.md` for the verified asset and
handoff.

## Contract boundaries

Adapters translate external metadata and observations into `BinMetadata` and
`FillObservation`. Fill observations contain a finite normalized fraction in
`[0, 1]` and a timezone-aware timestamp. Missing data is not converted to a
default value.

`TravelCostMatrix` uses explicit node ordering and represents unavailable
connections with `None`. It does not expose an OSMnx graph or imply that a
missing connection is zero cost.

## Prototype configuration

The documented prototype models a round trip:

```text
Stadtreinigung (SR) -> selected collection stops -> Stadtreinigung (SR)
```

Both node identifiers are `stadtreinigung-basel`. The modeled address is
Stadtreinigung (SR), Brüssel-Strasse 22, 4053 Basel, Switzerland. This is a
project modeling decision, not proof of a depot entrance or unloading access.
Coordinates are deliberately absent from the runtime configuration. The
explicit geocoding utility in
`smart_bin_routing.adapters.depot_geocoding` can create an accepted local
address-point record for a later geographic provider; it does not verify truck
access or perform road-network snapping.

Capacity, demand units, and threshold values must be supplied explicitly.
No operational defaults are claimed.

## Stage 2 classification

`FillObservation.fill_fraction` is a normalized fraction from `0` through `1`.
Classification requires an explicit timezone-aware `planning_time` and a
`PlanningConfig` with a positive `observation_max_age_seconds`. The exact
boundaries are:

```text
green  = fill < yellow_threshold
yellow = yellow_threshold <= fill < red_threshold
red    = fill >= red_threshold
```

For example:

```python
from datetime import UTC, datetime

from smart_bin_routing import (
    BinMetadata,
    FillObservation,
    PlanningConfig,
    PlanningSnapshot,
    classify_snapshot,
)

config = PlanningConfig(
    start_node_id="stadtreinigung-basel",
    end_node_id="stadtreinigung-basel",
    truck_capacity=100,
    demand_unit="kg",
    yellow_threshold=0.6,
    red_threshold=0.8,
    observation_max_age_seconds=3600,
    allowed_future_skew_seconds=0,
)
snapshot = PlanningSnapshot(
    bins=(BinMetadata("synthetic-bin-1"),),
    observations=(
        FillObservation(
            "synthetic-bin-1",
            0.8,
            datetime(2026, 10, 31, 12, 0, tzinfo=UTC),
        ),
    ),
)
result = classify_snapshot(snapshot, config, datetime(2026, 10, 31, 12, 0, tzinfo=UTC))
assert result.entries[0].classification.value == "red"
```

An observation exactly as old as `observation_max_age_seconds` is valid. An
observation older than that is `unknown` with reason code
`stale_observation`. An observation later than the planning time plus
`allowed_future_skew_seconds` is `unknown` with reason code
`future_observation`; the exact future boundary is valid. Missing observations
remain visible as `unknown` with `missing_observation`. Input timestamps are
never rewritten.

Structural errors are returned in `result.validation` and prevent classified
entries from being produced. A structurally valid snapshot can still contain
per-bin contextual diagnostics and unknown classifications. Color describes
fill level only; it does not create collection demand or select a route. No
sensor quality/status semantics are defined yet, so backend quality fields
remain an unresolved integration requirement.

## Stage 3 planning inputs

`assemble_planning_input` combines a `ClassifiedSnapshot` and a validated,
explicitly ordered `TravelCostMatrix` into immutable `PlanningInput` data for a
future solver. Candidates retain their bin identity, classification, and
explicit collection demand. Unknown classifications are excluded with a sensor
review diagnostic; they are not silently treated as zero demand or declared
faulty. Missing demand and missing travel nodes are visible exclusions.

An oversized demand remains intact and is marked with a diagnostic. `None` in a
travel matrix is explicitly unreachable, while malformed dimensions and missing
required nodes block assembly. Stage 4 optimizes the order of all admitted
candidates with one truck and one trip. See
`../../documentation/routing-stage-4.md` for the solver API and limitations.

## Synthetic test data

Fixtures in `tests/conftest.py` are synthetic and exist only to exercise the
contracts. They are not derived from the repository's real GeoJSON asset.
