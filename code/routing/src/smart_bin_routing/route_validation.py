"""Independent checks for extracted solver routes."""

from __future__ import annotations

from math import isclose

from .models import PlanningResult
from .planning import PlanningInput
from .solver import CostMetric, SolverConfig


def validate_route_result(
    planning_input: PlanningInput, result: PlanningResult, config: SolverConfig
) -> tuple[str, ...]:
    """Return errors instead of trusting solver extraction or index mapping."""

    errors: list[str] = []
    route = result.route_nodes
    if not route or route[0] != planning_input.depot_id or route[-1] != planning_input.depot_id:
        errors.append("route must start and finish at the configured depot")
        return tuple(errors)
    candidate_ids = {candidate.bin_id for candidate in planning_input.candidates}
    stops = route[1:-1]
    if any(stop not in candidate_ids for stop in stops):
        errors.append("route contains a node that is not an admitted candidate")
    if len(stops) != len(set(stops)):
        errors.append("route collects a candidate more than once")
    if set(stops) != candidate_ids:
        errors.append("route does not visit every mandatory candidate")

    matrix = (
        planning_input.travel_costs.distances
        if config.cost_metric == CostMetric.DISTANCE
        else planning_input.travel_costs.durations_seconds
    )
    positions = {
        node_id: index for index, node_id in enumerate(planning_input.travel_costs.node_ids)
    }
    total_cost = 0.0
    for source, target in zip(route, route[1:]):
        if source not in positions or target not in positions:
            errors.append("route contains a node absent from the matrix")
            continue
        value = matrix[positions[source]][positions[target]]
        if value is None:
            errors.append(f"route uses unavailable arc {source!r} -> {target!r}")
        else:
            total_cost += value

    demands = {candidate.bin_id: candidate.demand.amount for candidate in planning_input.candidates}
    collected = sum(demands.get(stop, 0.0) for stop in stops)
    if result.collected_demand is None or not isclose(
        result.collected_demand, collected, rel_tol=0, abs_tol=1e-9
    ):
        errors.append("reported demand does not match visited candidates")
    if collected > planning_input.truck_capacity + 1e-9:
        errors.append("route exceeds truck capacity")
    if result.total_travel_cost is None or not isclose(
        result.total_travel_cost, total_cost, rel_tol=0, abs_tol=1e-9
    ):
        errors.append("reported travel cost does not match the ordered route")
    return tuple(errors)
