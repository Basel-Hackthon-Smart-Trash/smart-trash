"""Run the offline Stage 4 synthetic route example.

From code/routing/: ``uv run python examples/stage4_basic_route.py``
"""

from datetime import UTC, datetime

from smart_bin_routing import (
    BinMetadata,
    CollectionDemand,
    FillObservation,
    PlanningConfig,
    PlanningSnapshot,
    SolverConfig,
    assemble_planning_input,
    classify_snapshot,
    optimize_route,
)
from smart_bin_routing.contracts import TravelCostMatrix

planning_time = datetime(2026, 10, 31, 12, 0, tzinfo=UTC)
config = PlanningConfig("synthetic-depot", "synthetic-depot", 10, "kg", 0.5, 0.8, 3600)
snapshot = PlanningSnapshot(
    bins=(BinMetadata("synthetic-bin-a"), BinMetadata("synthetic-bin-b")),
    observations=(
        FillObservation("synthetic-bin-a", 0.9, planning_time),
        FillObservation("synthetic-bin-b", 0.9, planning_time),
    ),
    demands=(
        CollectionDemand("synthetic-bin-a", 2, "kg"),
        CollectionDemand("synthetic-bin-b", 3, "kg"),
    ),
)
classified = classify_snapshot(snapshot, config, planning_time)
assembly = assemble_planning_input(
    classified,
    TravelCostMatrix(
        ("synthetic-bin-b", "synthetic-depot", "synthetic-bin-a"),
        ((0, 4, 1), (2, 0, 3), (5, 1, 0)),
        distance_unit="km",
    ),
)
result = optimize_route(assembly.planning_input, SolverConfig()) if assembly.valid else None

print("status:", result.status.value if result else "invalid_input")
print("visits:", result.stops if result else ())
print("demand:", result.collected_demand if result else None, "kg")
print("travel cost:", result.total_travel_cost if result else None, "km")
print(
    "diagnostics:",
    result.diagnostics if result else tuple(item.code for item in assembly.diagnostics),
)
