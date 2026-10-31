"""Run the offline Stage 5 application orchestration example.

From code/routing/: ``uv run python examples/stage5_collection_plan.py``
All observations and travel costs in this example are synthetic.
"""

from datetime import UTC, datetime

from smart_bin_routing import (
    BinMetadata,
    CollectionDemand,
    CollectionPlanRequest,
    FillObservation,
    PlanningSnapshot,
    plan_collection,
)
from smart_bin_routing.contracts import TravelCostMatrix
from smart_bin_routing.prototype_config import prototype_configuration

planning_time = datetime(2026, 10, 31, 12, 0, tzinfo=UTC)
config = prototype_configuration(
    truck_capacity=10,
    demand_unit="kg",
    yellow_threshold=0.6,
    red_threshold=0.8,
    observation_max_age_seconds=3600,
)
snapshot = PlanningSnapshot(
    bins=(BinMetadata("synthetic-bin-a"), BinMetadata("synthetic-bin-b")),
    observations=(
        FillObservation("synthetic-bin-a", 0.9, planning_time),
        FillObservation("synthetic-bin-b", 0.7, planning_time),
    ),
    demands=(
        CollectionDemand("synthetic-bin-a", 2, "kg"),
        CollectionDemand("synthetic-bin-b", 3, "kg"),
    ),
)
travel_costs = TravelCostMatrix(
    ("synthetic-bin-b", "stadtreinigung-basel", "synthetic-bin-a"),
    distances=((0, 4, 1), (2, 0, 3), (5, 1, 0)),
    distance_unit="synthetic-km",
)

result = plan_collection(CollectionPlanRequest(snapshot, config, planning_time, travel_costs))

print("data: SIMULATED (synthetic observations and approximate test distances)")
print("depot: Stadtreinigung Basel (modeled, vehicle access unconfirmed)")
print("input bins:", len(snapshot.bins))
print("eligible bins:", sum(item.routing_ready for item in result.bins))
print("status:", result.status.value)

print("excluded bins:")
for item in result.bins:
    if not item.routing_ready or not item.included_in_route:
        reasons = ", ".join(diagnostic.code for diagnostic in item.diagnostics) or "not included"
        print(f"  - {item.bin_id}: {reasons}")

print("route stops:")
if result.solver_result and result.solver_result.stops:
    for bin_id, load in zip(result.solver_result.stops, result.solver_result.loads_after_stop):
        print(f"  - {bin_id}: load {load:g} {result.solver_result.demand_unit}")
else:
    print("  - none")
print("route nodes:", result.route_nodes)
print("diagnostics:", [item.code for item in result.diagnostics])
if result.solver_result:
    print(
        "collected:",
        result.solver_result.collected_demand,
        result.solver_result.demand_unit,
    )
    print(
        "distance:",
        result.solver_result.travel_distance,
        result.solver_result.travel_cost_unit,
    )
