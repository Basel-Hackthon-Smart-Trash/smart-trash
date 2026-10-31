# Routing Component Stage 6

Stage 6 validates the Stage 5 backend-facing planning boundary and provides a
repeatable offline demonstration. The public entry point remains:

```python
from smart_bin_routing import CollectionPlanRequest, plan_collection

result = plan_collection(
    CollectionPlanRequest(snapshot, config, planning_time, travel_costs)
)
```

The caller supplies one coherent `PlanningSnapshot`, a timezone-aware planning
time, `PlanningConfig`, and a validated `TravelCostMatrix`. The routing package
owns validation, fill classification, planning-input preparation, and the
single-truck route optimization. It does not own observation storage,
deduplication, scheduling, demand estimation, MQTT, databases, or result
transport.

## Result Outcomes

`CollectionPlanResult.status` uses the existing application vocabulary:

- `feasible`: a route passed independent validation;
- `no_actionable_bins`: the snapshot contains no bins;
- `no_routing_ready_candidates`: bins exist, but none have usable routing inputs;
- `invalid_request`: structural input or required matrix data is invalid;
- `infeasible`: mandatory demand or directed connectivity cannot fit the route;
- `search_exhausted` or `time_limit`: the bounded solver found no route;
- `solver_error`: the solver adapter failed or returned an invalid route.

Assessments retain every known bin and its classification, route readiness,
route inclusion, and diagnostic codes. Unknown, stale, missing, or future
observations are excluded from routing with reasons. Duplicate observations are
rejected by the existing structural validation policy; snapshot ownership and
deduplication remain upstream responsibilities.

## Offline Demo

From the routing package directory:

```text
cd code/routing
uv run python examples/stage5_collection_plan.py
```

The example uses the modeled `kva-basel` depot, synthetic observations and
demands, and a fixed local `synthetic-km` matrix. Its output includes input and
eligible-bin counts, exclusions, route stops, cumulative loads, distance units,
status, and diagnostics. The route is a fixture-based demonstration, not
verified real-world navigation.

## Verification

Default checks are offline and do not require Docker, Mosquitto, a database, or
network access:

```text
cd code/routing
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

The integration tests use the real OR-Tools solver for successful small plans
and controlled solver backends for failure cases. They check route identity,
duplicate stops, depot handling, capacity, exclusions, empty results, matrix
failures, solver failures, and status distinctions.

There is no serialization utility or serialized backend contract in this
repository. Results are Python domain objects; serialization, request parsing,
and response delivery belong to the backend integration layer and should not be
invented by this component.

## Infrastructure Boundary

No MQTT adapter exists in the routing package. The backend or ingestion service
must own broker connections, topics, payload validation, redelivery and
duplicate policy, snapshot assembly, and planning triggers. Importing
`smart_bin_routing` does not open a broker connection.

Mosquitto is the only Compose service. Optional infrastructure checks, when
Docker is available, are:

```text
docker compose config
docker compose up -d
docker compose ps
docker compose down
```

The current Compose file has pre-existing Mosquitto path inconsistencies and
does not affect the default routing checks. No Stage 6 code depends on the
broker or Docker.

## Limitations

The optimizer still supports one vehicle, one trip, mandatory admitted stops,
explicit caller-supplied demand, and a caller-supplied directed cost matrix.
There is no real demand estimator, road-network provider, route geometry,
multiple-vehicle planning, split collection, sensor-health history, MQTT
contract, persistence, or backend endpoint.
