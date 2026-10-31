from datetime import UTC, datetime

from smart_bin_routing import (
    BinMetadata,
    CollectionDemand,
    CostMetric,
    FillObservation,
    PlanningResult,
    PlanningSnapshot,
    PlanningStatus,
    SolverConfig,
    assemble_planning_input,
    classify_snapshot,
    optimize_route,
)
from smart_bin_routing.contracts import TravelCostMatrix

NOW = datetime(2026, 10, 31, 12, 0, tzinfo=UTC)


def planning_input(config, demands, *, node_ids=None, distances=None, durations=None):
    bins = tuple(BinMetadata(bin_id) for bin_id, _ in demands)
    classified = classify_snapshot(
        PlanningSnapshot(
            bins=bins,
            observations=tuple(FillObservation(bin_id, 0.9, NOW) for bin_id, _ in demands),
            demands=tuple(CollectionDemand(bin_id, amount, "kg") for bin_id, amount in demands),
        ),
        config,
        NOW,
    )
    node_ids = node_ids or ("depot", *(bin_id for bin_id, _ in demands))
    size = len(node_ids)
    matrix = TravelCostMatrix(
        node_ids,
        distances=(
            distances
            if distances is not None
            else None
            if durations is not None
            else tuple(tuple(0.0 for _ in range(size)) for _ in range(size))
        ),
        durations_seconds=durations,
        distance_unit="km" if distances is not None or durations is None else None,
        duration_unit="s" if durations is not None else None,
    )
    return assemble_planning_input(classified, matrix).planning_input


def test_empty_input_returns_no_work(synthetic_config):
    config = type(synthetic_config)("depot", "depot", 10, "kg", 0.5, 0.8, 3600)
    result = optimize_route(planning_input(config, []))

    assert result.status == PlanningStatus.NO_WORK
    assert result.route_nodes == ("depot", "depot")


def test_route_visits_all_candidates_and_reports_totals(synthetic_config):
    config = synthetic_config
    config = type(config)("depot", "depot", 10, "kg", 0.5, 0.8, 3600)
    result = optimize_route(
        planning_input(
            config,
            [("bin-a", 2), ("bin-b", 3)],
            node_ids=("bin-b", "depot", "bin-a"),
            distances=((0, 4, 1), (2, 0, 3), (5, 1, 0)),
        )
    )

    assert result.status == PlanningStatus.FEASIBLE
    assert set(result.stops) == {"bin-a", "bin-b"}
    assert result.route_nodes[0] == result.route_nodes[-1] == "depot"
    assert result.collected_demand == 5
    assert result.total_travel_cost == 4
    assert result.loads_after_stop[-1] == 5


def test_asymmetric_order_is_optimized(synthetic_config):
    config = type(synthetic_config)("depot", "depot", 10, "kg", 0.5, 0.8, 3600)
    result = optimize_route(
        planning_input(
            config,
            [("a", 1), ("b", 1)],
            distances=((0, 1, 10), (1, 0, 1), (1, 10, 0)),
        )
    )

    assert result.status == PlanningStatus.FEASIBLE
    assert result.stops == ("a", "b")
    assert result.total_travel_cost == 3


def test_exact_capacity_is_feasible(synthetic_config):
    config = type(synthetic_config)("depot", "depot", 10, "kg", 0.5, 0.8, 3600)
    result = optimize_route(planning_input(config, [("bin", 10)]))

    assert result.status == PlanningStatus.FEASIBLE
    assert result.collected_demand == 10


def test_mandatory_over_capacity_is_not_silently_dropped(synthetic_config):
    config = type(synthetic_config)("depot", "depot", 10, "kg", 0.5, 0.8, 3600)
    result = optimize_route(planning_input(config, [("a", 6), ("b", 5)]))

    assert result.status == PlanningStatus.INFEASIBLE
    assert result.stops == ()
    assert "total_demand_exceeds_truck_capacity" in result.diagnostics


def test_unavailable_arc_is_not_used(synthetic_config):
    config = type(synthetic_config)("depot", "depot", 10, "kg", 0.5, 0.8, 3600)
    result = optimize_route(
        planning_input(
            config,
            [("bin", 1)],
            distances=((0, 2), (None, 0)),
        )
    )

    assert result.status == PlanningStatus.INFEASIBLE
    assert result.stops == ()


def test_duration_metric_uses_declared_duration_matrix(synthetic_config):
    config = type(synthetic_config)("depot", "depot", 10, "kg", 0.5, 0.8, 3600)
    result = optimize_route(
        planning_input(
            config,
            [("bin", 1)],
            distances=None,
            durations=((0, 4), (5, 0)),
        ),
        SolverConfig(cost_metric=CostMetric.DURATION),
    )

    assert result.status == PlanningStatus.FEASIBLE
    assert result.total_travel_cost == 9
    assert result.travel_cost_unit == "s"


def test_backend_status_is_preserved(synthetic_config):
    config = type(synthetic_config)("depot", "depot", 10, "kg", 0.5, 0.8, 3600)
    empty = PlanningResult(PlanningStatus.TIME_LIMIT, diagnostics=("controlled",))
    result = optimize_route(
        planning_input(config, [("bin", 1)]),
        backend=lambda _planning_input, _config: empty,
    )

    assert result.status == PlanningStatus.TIME_LIMIT
    assert result.diagnostics == ("controlled",)


def test_invalid_feasible_backend_result_is_rejected(synthetic_config):
    config = type(synthetic_config)("depot", "depot", 10, "kg", 0.5, 0.8, 3600)
    malformed = PlanningResult(
        PlanningStatus.FEASIBLE,
        stops=("bin",),
        route_nodes=("depot", "depot"),
        collected_demand=0,
        total_travel_cost=0,
    )
    result = optimize_route(
        planning_input(config, [("bin", 1)]),
        backend=lambda _planning_input, _config: malformed,
    )

    assert result.status == PlanningStatus.SOLVER_ERROR
    assert result.diagnostics == ("route_validation_failed",)
