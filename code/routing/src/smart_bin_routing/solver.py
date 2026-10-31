"""Capacity-constrained, single-trip route optimization.

Only this module imports OR-Tools. The public API accepts and returns domain
models, so callers do not need to know about solver indices or callbacks.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import ceil, isfinite
from typing import Protocol

from ortools.constraint_solver import pywrapcp, routing_enums_pb2

from .models import PlanningDiagnostic, PlanningResult, PlanningStatus
from .planning import PlanningInput


class CostMetric(StrEnum):
    DISTANCE = "distance"
    DURATION = "duration"


@dataclass(frozen=True, slots=True)
class SolverConfig:
    """Small bounded-search configuration for one vehicle and one trip."""

    time_limit_seconds: float = 5.0
    cost_metric: CostMetric = CostMetric.DISTANCE
    cost_scale: int = 1000
    demand_scale: int = 1000

    def __post_init__(self) -> None:
        if not isinstance(self.cost_metric, CostMetric):
            raise ValueError("cost_metric must be a CostMetric")
        if not isfinite(self.time_limit_seconds) or self.time_limit_seconds <= 0:
            raise ValueError("time_limit_seconds must be greater than zero")
        if not isinstance(self.cost_scale, int) or self.cost_scale <= 0:
            raise ValueError("cost_scale must be a positive integer")
        if not isinstance(self.demand_scale, int) or self.demand_scale <= 0:
            raise ValueError("demand_scale must be a positive integer")


class SolverBackend(Protocol):
    def __call__(self, planning_input: PlanningInput, config: SolverConfig) -> PlanningResult:
        """Run the solver adapter."""


def _diagnostic(code: str, message: str, *, bin_id: str | None = None) -> PlanningDiagnostic:
    return PlanningDiagnostic(code, message, "error", bin_id)


def _invalid(
    planning_input: PlanningInput,
    details: tuple[PlanningDiagnostic, ...],
) -> PlanningResult:
    return PlanningResult(
        PlanningStatus.INVALID_INPUT,
        depot_id=planning_input.depot_id,
        truck_capacity=planning_input.truck_capacity,
        demand_unit=planning_input.demand_unit,
        diagnostic_details=details,
        diagnostics=tuple(item.code for item in details),
    )


def _cost_matrix(planning_input: PlanningInput, config: SolverConfig):
    matrix = (
        planning_input.travel_costs.distances
        if config.cost_metric == CostMetric.DISTANCE
        else planning_input.travel_costs.durations_seconds
    )
    unit = (
        planning_input.travel_costs.distance_unit
        if config.cost_metric == CostMetric.DISTANCE
        else planning_input.travel_costs.duration_unit
    )
    if matrix is None or unit is None:
        return None, None
    return matrix, unit


def _scaled(value: float, scale: int, *, ceiling: bool = False) -> int:
    scaled = value * scale
    if not isfinite(scaled) or scaled > 2**62:
        raise ValueError("scaled value exceeds supported integer range")
    return ceil(scaled) if ceiling else round(scaled)


def _validate_inputs(
    planning_input: PlanningInput, config: SolverConfig, matrix
) -> tuple[PlanningDiagnostic, ...]:
    node_ids = planning_input.travel_costs.node_ids
    details: list[PlanningDiagnostic] = []
    if planning_input.depot_id not in node_ids:
        details.append(_diagnostic("missing_depot_node", "depot is absent from the cost matrix"))
    if planning_input.truck_capacity <= 0 or not isfinite(planning_input.truck_capacity):
        details.append(
            _diagnostic("invalid_truck_capacity", "truck capacity must be finite and positive")
        )
    if matrix is None:
        details.append(
            _diagnostic(
                "unsupported_cost_metric",
                f"the matrix does not provide {config.cost_metric.value} costs",
            )
        )
        return tuple(details)
    known = set(node_ids)
    total = 0.0
    seen: set[str] = set()
    for candidate in planning_input.candidates:
        if candidate.bin_id not in known:
            details.append(
                _diagnostic(
                    "missing_candidate_node",
                    "candidate is absent from the cost matrix",
                    bin_id=candidate.bin_id,
                )
            )
        if candidate.bin_id in seen:
            details.append(
                _diagnostic(
                    "duplicate_candidate",
                    "candidate occurs more than once",
                    bin_id=candidate.bin_id,
                )
            )
        seen.add(candidate.bin_id)
        amount = candidate.demand.amount
        total += amount
        if amount > planning_input.truck_capacity:
            details.append(
                _diagnostic(
                    "demand_exceeds_truck_capacity",
                    "candidate cannot fit in the truck",
                    bin_id=candidate.bin_id,
                )
            )
    if total > planning_input.truck_capacity:
        details.append(
            _diagnostic(
                "total_demand_exceeds_truck_capacity", "mandatory demand exceeds truck capacity"
            )
        )
    if planning_input.depot_id in known:
        depot_index = node_ids.index(planning_input.depot_id)
        reachable_from_depot = _reachable(matrix, depot_index)
        reachable_to_depot = _reverse_reachable(matrix, depot_index)
        for candidate in planning_input.candidates:
            if candidate.bin_id not in known:
                continue
            candidate_index = node_ids.index(candidate.bin_id)
            if (
                candidate_index not in reachable_from_depot
                or candidate_index not in reachable_to_depot
            ):
                details.append(
                    _diagnostic(
                        "unreachable_mandatory_candidate",
                        "candidate has no available directed path to or from the depot",
                        bin_id=candidate.bin_id,
                    )
                )
    try:
        _scaled(planning_input.truck_capacity, config.demand_scale)
        for row in matrix:
            for value in row:
                if value is not None:
                    _scaled(value, config.cost_scale)
        for candidate in planning_input.candidates:
            _scaled(candidate.demand.amount, config.demand_scale, ceiling=True)
    except (TypeError, ValueError):
        details.append(
            _diagnostic("numeric_range_exceeded", "cost or demand cannot be represented safely")
        )
    return tuple(details)


def _reachable(matrix, start: int) -> set[int]:
    reached = {start}
    pending = [start]
    while pending:
        source = pending.pop()
        for target, value in enumerate(matrix[source]):
            if value is not None and target not in reached:
                reached.add(target)
                pending.append(target)
    return reached


def _reverse_reachable(matrix, start: int) -> set[int]:
    reached = {start}
    pending = [start]
    while pending:
        target = pending.pop()
        for source, row in enumerate(matrix):
            if row[target] is not None and source not in reached:
                reached.add(source)
                pending.append(source)
    return reached


def _no_work(planning_input: PlanningInput, config: SolverConfig) -> PlanningResult:
    matrix, unit = _cost_matrix(planning_input, config)
    if matrix is None:
        return _invalid(
            planning_input,
            (
                _diagnostic(
                    "unsupported_cost_metric",
                    f"the matrix does not provide {config.cost_metric.value} costs",
                ),
            ),
        )
    return PlanningResult(
        PlanningStatus.NO_WORK,
        route_nodes=(planning_input.depot_id, planning_input.depot_id),
        depot_id=planning_input.depot_id,
        truck_capacity=planning_input.truck_capacity,
        demand_unit=planning_input.demand_unit,
        total_travel_cost=0.0,
        travel_cost_unit=unit,
        objective_value=0,
        diagnostics=("no_candidates",),
        solver_metadata=(("solver", "not_run"),),
    )


def _run_ortools(planning_input: PlanningInput, config: SolverConfig) -> PlanningResult:
    matrix, unit = _cost_matrix(planning_input, config)
    node_ids = planning_input.travel_costs.node_ids
    indexes = {node_id: index for index, node_id in enumerate(node_ids)}
    depot_index = indexes[planning_input.depot_id]
    manager = pywrapcp.RoutingIndexManager(len(node_ids), 1, depot_index)
    routing = pywrapcp.RoutingModel(manager)

    def transit(from_index: int, to_index: int) -> int:
        source = manager.IndexToNode(from_index)
        target = manager.IndexToNode(to_index)
        value = matrix[source][target]
        return 0 if value is None else _scaled(value, config.cost_scale)

    transit_index = routing.RegisterTransitCallback(transit)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_index)

    demands = {candidate.bin_id: candidate.demand.amount for candidate in planning_input.candidates}

    def demand_callback(index: int) -> int:
        node_id = node_ids[manager.IndexToNode(index)]
        return (
            0
            if node_id == planning_input.depot_id
            else _scaled(demands[node_id], config.demand_scale, ceiling=True)
        )

    demand_index = routing.RegisterUnaryTransitCallback(demand_callback)
    routing.AddDimensionWithVehicleCapacity(
        demand_index,
        0,
        [_scaled(planning_input.truck_capacity, config.demand_scale)],
        True,
        "Capacity",
    )

    # OR-Tools callbacks must return an integer. Explicit solver constraints
    # ensure a None matrix cell remains unavailable rather than zero cost.
    for source, row in enumerate(matrix):
        if node_ids[source] == planning_input.depot_id and source != depot_index:
            continue
        source_index = manager.NodeToIndex(source)
        if source_index < 0:
            continue
        for target, value in enumerate(row):
            if value is None:
                target_index = (
                    routing.End(0) if target == depot_index else manager.NodeToIndex(target)
                )
                routing.solver().Add(routing.NextVar(source_index) != target_index)

    search = pywrapcp.DefaultRoutingSearchParameters()
    search.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    search.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )
    search.time_limit.FromMilliseconds(round(config.time_limit_seconds * 1000))
    solution = routing.SolveWithParameters(search)
    if solution is None:
        elapsed = routing.solver().WallTime() / 1000
        status = (
            PlanningStatus.TIME_LIMIT
            if elapsed >= config.time_limit_seconds
            else PlanningStatus.SEARCH_EXHAUSTED
        )
        return PlanningResult(
            status,
            depot_id=planning_input.depot_id,
            truck_capacity=planning_input.truck_capacity,
            demand_unit=planning_input.demand_unit,
            travel_cost_unit=unit,
            diagnostics=("solver_returned_no_solution",),
            solver_metadata=(("solver", "ortools"), ("wall_time_seconds", str(elapsed))),
        )

    route_indices: list[int] = []
    index = routing.Start(0)
    while not routing.IsEnd(index):
        route_indices.append(manager.IndexToNode(index))
        index = solution.Value(routing.NextVar(index))
    route_indices.append(manager.IndexToNode(index))
    route_nodes = tuple(node_ids[item] for item in route_indices)
    stops = tuple(node for node in route_nodes[1:-1])
    total_cost = sum(
        matrix[source][target]
        for source, target in zip(route_indices, route_indices[1:])
        if matrix[source][target] is not None
    )
    total_demand = sum(demands[stop] for stop in stops)
    loads = []
    load = 0.0
    for stop in stops:
        load += demands[stop]
        loads.append(load)
    return PlanningResult(
        PlanningStatus.FEASIBLE,
        stops=stops,
        collected_demand=total_demand,
        travel_distance=total_cost if config.cost_metric == CostMetric.DISTANCE else None,
        travel_duration_seconds=total_cost if config.cost_metric == CostMetric.DURATION else None,
        route_nodes=route_nodes,
        depot_id=planning_input.depot_id,
        truck_capacity=planning_input.truck_capacity,
        demand_unit=planning_input.demand_unit,
        total_travel_cost=total_cost,
        travel_cost_unit=unit,
        objective_value=solution.ObjectiveValue(),
        loads_after_stop=tuple(loads),
        solver_metadata=(
            ("solver", "ortools"),
            ("search_limit_seconds", str(config.time_limit_seconds)),
        ),
    )


def optimize_route(
    planning_input: PlanningInput,
    config: SolverConfig | None = None,
    *,
    backend: SolverBackend | None = None,
) -> PlanningResult:
    """Optimize one mandatory-visit, capacity-constrained depot round trip."""

    config = config or SolverConfig()
    matrix, _ = _cost_matrix(planning_input, config)
    if not planning_input.candidates:
        return _no_work(planning_input, config)
    details = _validate_inputs(planning_input, config, matrix)
    if details:
        status = (
            PlanningStatus.INFEASIBLE
            if any(
                item.code
                in {
                    "demand_exceeds_truck_capacity",
                    "total_demand_exceeds_truck_capacity",
                    "unreachable_mandatory_candidate",
                }
                for item in details
            )
            else PlanningStatus.INVALID_INPUT
        )
        result = _invalid(planning_input, details)
        return PlanningResult(
            status,
            depot_id=result.depot_id,
            truck_capacity=result.truck_capacity,
            demand_unit=result.demand_unit,
            diagnostics=result.diagnostics,
            diagnostic_details=result.diagnostic_details,
        )
    try:
        result = (backend or _run_ortools)(planning_input, config)
    except Exception as error:
        detail = _diagnostic("solver_exception", f"unexpected solver failure: {error}")
        return PlanningResult(
            PlanningStatus.SOLVER_ERROR,
            depot_id=planning_input.depot_id,
            truck_capacity=planning_input.truck_capacity,
            demand_unit=planning_input.demand_unit,
            diagnostics=(detail.code,),
            diagnostic_details=(detail,),
        )
    if result.status == PlanningStatus.FEASIBLE:
        from .route_validation import validate_route_result

        errors = validate_route_result(planning_input, result, config)
        if errors:
            detail = _diagnostic("route_validation_failed", "; ".join(errors))
            return PlanningResult(
                PlanningStatus.SOLVER_ERROR,
                depot_id=planning_input.depot_id,
                truck_capacity=planning_input.truck_capacity,
                demand_unit=planning_input.demand_unit,
                diagnostics=(detail.code,),
                diagnostic_details=(detail,),
            )
    return result
