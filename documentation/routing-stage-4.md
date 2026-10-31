# Routing Component Stage 4

Stage 4 adds the first working capacity-constrained route optimizer to
`code/routing/`. It consumes the validated `PlanningInput` assembled by Stage
3 and uses OR-Tools internally. No geographic, street-network, backend,
database, or live-data adapter is included.

## API

```python
from smart_bin_routing import CostMetric, SolverConfig, optimize_route

result = optimize_route(
    planning_input,
    SolverConfig(time_limit_seconds=5, cost_metric=CostMetric.DISTANCE),
)
print(result.status)
print(result.route_nodes)       # depot, bins, depot
print(result.stops)             # bin IDs only
print(result.collected_demand)
print(result.total_travel_cost)
print(result.diagnostic_details)
```

`optimize_route` plans one vehicle, one trip, an initially empty truck, and a
single configured depot. The depot is identified by `PlanningInput.depot_id`
and is mapped to the explicit `TravelCostMatrix.node_ids` ordering. It is not
assumed to be matrix index zero.

## Visit Policy

Every candidate admitted by Stage 3 is mandatory. Unknown classifications,
missing demands, and missing matrix nodes remain Stage 3 exclusions and are not
silently added. Stage 4 optimizes visit order only; it does not select which
bins to collect. Optional visits and dropped-bin penalties are not
implemented.

## Capacity and Costs

Collection demand and truck capacity use the `PlanningInput.demand_unit`.
Demand is accumulated after each collection stop. Demand equal to capacity is
valid; an oversized candidate or total mandatory demand above capacity returns
`INFEASIBLE` before solving.

The solver uses either the explicitly selected distance or duration matrix.
The matrix's declared unit is returned as `travel_cost_unit`. Costs are scaled
to integer solver units using `cost_scale=1000` by default. Demands use
`demand_scale=1000`; demand values are rounded upward for the capacity
constraint so conversion cannot make an over-capacity route feasible. Values
outside the signed 64-bit solver range are rejected.

`None` matrix cells remain unavailable. They are constrained out of the
OR-Tools model and the extracted route is independently checked for available
arcs. They are never interpreted as zero cost.

## Statuses

- `FEASIBLE`: a route was returned and passed independent validation. This is a
  feasible bounded-search result, not a claim of global optimality.
- `NO_WORK`: no candidates were admitted; solving was skipped.
- `INFEASIBLE`: mandatory capacity infeasibility was proven or prevalidated.
- `INVALID_INPUT`: required cost data or numeric input is unsupported.
- `SEARCH_EXHAUSTED`: the solver returned without a route before the limit.
- `TIME_LIMIT`: the search limit ended without a route.
- `SOLVER_ERROR`: an unexpected adapter failure occurred.

The default search limit is five seconds and can be overridden through
`SolverConfig`. OR-Tools metadata is returned as strings; solver objects and
internal indices are not exposed.

## Example and Checks

The offline synthetic example is:

```text
cd code/routing
uv run python examples/stage4_basic_route.py
```

Stage 4 tests cover empty and basic routes, asymmetric order, non-zero depot
matrix position, exact capacity, over-capacity mandatory demand, unavailable
arcs, duration costs, controlled solver statuses, and independent result
validation. All data is synthetic.

Run the package checks with:

```text
cd code/routing
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

## Limitations

There is one truck and one trip only. There are no intermediate unloading,
multiple vehicles, time windows, shift limits, route geometry, live replanning,
priority weights, optional visits, or real travel-cost providers. The existing
`PlanningConfig.route_duration_limit_seconds` is not applied by this stage.
