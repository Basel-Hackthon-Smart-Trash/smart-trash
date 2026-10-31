from datetime import UTC, datetime

import pytest

from smart_bin_routing import (
    BinMetadata,
    CollectionDemand,
    CollectionPlanRequest,
    CollectionPlanStatus,
    FillObservation,
    PlanningResult,
    PlanningSnapshot,
    PlanningStatus,
    plan_collection,
)
from smart_bin_routing.contracts import TravelCostMatrix

NOW = datetime(2026, 10, 31, 12, 0, tzinfo=UTC)


def request(config, *, bins, observations, demands, costs=None):
    node_ids = (config.start_node_id, *(item.bin_id for item in bins))
    size = len(node_ids)
    return CollectionPlanRequest(
        PlanningSnapshot(tuple(bins), tuple(observations), tuple(demands)),
        config,
        NOW,
        costs
        or TravelCostMatrix(
            node_ids,
            distances=tuple(tuple(0.0 for _ in range(size)) for _ in range(size)),
            distance_unit="km",
        ),
    )


def test_valid_snapshot_returns_feasible_route(synthetic_config):
    bins = (BinMetadata("bin-a"), BinMetadata("bin-b"))
    result = plan_collection(
        request(
            synthetic_config,
            bins=bins,
            observations=(
                FillObservation("bin-a", 0.9, NOW),
                FillObservation("bin-b", 0.7, NOW),
            ),
            demands=(
                CollectionDemand("bin-a", 2, "kg"),
                CollectionDemand("bin-b", 3, "kg"),
            ),
        )
    )

    assert result.status == CollectionPlanStatus.FEASIBLE
    assert result.route_nodes[0] == result.route_nodes[-1] == synthetic_config.start_node_id
    assert {item.bin_id for item in result.bins if item.included_in_route} == {
        "bin-a",
        "bin-b",
    }
    assert result.solver_result.collected_demand == 5


def test_bin_identity_and_matrix_order_are_preserved(synthetic_config):
    bins = (BinMetadata("bin-a"), BinMetadata("bin-b"))
    result = plan_collection(
        request(
            synthetic_config,
            bins=bins,
            observations=(
                FillObservation("bin-a", 0.9, NOW),
                FillObservation("bin-b", 0.9, NOW),
            ),
            demands=(CollectionDemand("bin-a", 1, "kg"), CollectionDemand("bin-b", 1, "kg")),
            costs=TravelCostMatrix(
                ("bin-b", "synthetic-depot", "bin-a"),
                distances=((0, 4, 1), (2, 0, 3), (5, 1, 0)),
                distance_unit="km",
            ),
        )
    )

    assert result.status == CollectionPlanStatus.FEASIBLE
    assert result.solver_result.route_nodes[0:1] == (synthetic_config.start_node_id,)
    assert set(result.stops) == {"bin-a", "bin-b"}


def test_classification_remains_visible_for_excluded_bin(synthetic_config):
    result = plan_collection(
        request(
            synthetic_config,
            bins=(BinMetadata("bin-1"),),
            observations=(),
            demands=(CollectionDemand("bin-1", 2, "kg"),),
        )
    )

    assert result.status == CollectionPlanStatus.NO_ROUTING_READY_CANDIDATES
    assert result.bins[0].classification.value == "unknown"
    assert not result.bins[0].routing_ready
    assert "unknown_classification_sensor_check" in {
        item.code for item in result.bins[0].diagnostics
    }


def test_mixed_observations_keep_accepted_and_rejected_bins_visible(synthetic_config):
    bins = (BinMetadata("fresh"), BinMetadata("stale"))
    result = plan_collection(
        request(
            synthetic_config,
            bins=bins,
            observations=(
                FillObservation("fresh", 0.9, NOW),
                FillObservation("stale", 0.9, NOW.replace(year=2020)),
            ),
            demands=(
                CollectionDemand("fresh", 2, "kg"),
                CollectionDemand("stale", 2, "kg"),
            ),
        )
    )

    assert result.status == CollectionPlanStatus.FEASIBLE
    assert result.stops == ("fresh",)
    assessments = {item.bin_id: item for item in result.bins}
    assert assessments["fresh"].included_in_route
    assert not assessments["stale"].routing_ready
    assert "stale_observation" in {item.code for item in assessments["stale"].diagnostics}
    assert "unknown_classification_sensor_check" in {
        item.code for item in assessments["stale"].diagnostics
    }


def test_unknown_observation_identifier_is_invalid_request(synthetic_config):
    result = plan_collection(
        request(
            synthetic_config,
            bins=(BinMetadata("known"),),
            observations=(FillObservation("unknown", 0.9, NOW),),
            demands=(),
        )
    )

    assert result.status == CollectionPlanStatus.INVALID_REQUEST
    assert result.solver_result is None
    assert "unknown_observation_bin" in {item.code for item in result.diagnostics}


def test_unknown_demand_identifier_is_invalid_request(synthetic_config):
    result = plan_collection(
        request(
            synthetic_config,
            bins=(BinMetadata("known"),),
            observations=(FillObservation("known", 0.9, NOW),),
            demands=(CollectionDemand("unknown", 2, "kg"),),
        )
    )

    assert result.status == CollectionPlanStatus.INVALID_REQUEST
    assert result.solver_result is None
    assert "unknown_demand_bin" in {item.code for item in result.diagnostics}


def test_individual_demand_over_capacity_is_infeasible(synthetic_config):
    result = plan_collection(
        request(
            synthetic_config,
            bins=(BinMetadata("oversized"),),
            observations=(FillObservation("oversized", 0.9, NOW),),
            demands=(CollectionDemand("oversized", 11, "kg"),),
        )
    )

    assert result.status == CollectionPlanStatus.INFEASIBLE
    assert result.solver_result.status == PlanningStatus.INFEASIBLE
    assert result.stops == ()
    assert "demand_exceeds_truck_capacity" in result.solver_result.diagnostics
    assert not result.bins[0].included_in_route


def test_missing_matrix_depot_is_invalid_request(synthetic_config):
    result = plan_collection(
        request(
            synthetic_config,
            bins=(BinMetadata("bin-1"),),
            observations=(FillObservation("bin-1", 0.9, NOW),),
            demands=(CollectionDemand("bin-1", 1, "kg"),),
            costs=TravelCostMatrix(
                ("bin-1",),
                distances=((0,),),
                distance_unit="km",
            ),
        )
    )

    assert result.status == CollectionPlanStatus.INVALID_REQUEST
    assert result.solver_result is None
    assert "missing_depot_node" in {item.code for item in result.diagnostics}


def test_missing_demand_skips_optimizer(synthetic_config):
    calls = 0

    def backend(_planning_input, _config):
        nonlocal calls
        calls += 1
        return PlanningResult(PlanningStatus.FEASIBLE)

    result = plan_collection(
        request(
            synthetic_config,
            bins=(BinMetadata("bin-1"),),
            observations=(FillObservation("bin-1", 0.9, NOW),),
            demands=(),
        ),
        backend=backend,
    )

    assert result.status == CollectionPlanStatus.NO_ROUTING_READY_CANDIDATES
    assert calls == 0


def test_empty_snapshot_is_no_actionable_work_and_does_not_optimize(synthetic_config):
    calls = 0

    def backend(_planning_input, _config):
        nonlocal calls
        calls += 1
        return PlanningResult(PlanningStatus.FEASIBLE)

    result = plan_collection(
        request(synthetic_config, bins=(), observations=(), demands=()),
        backend=backend,
    )

    assert result.status == CollectionPlanStatus.NO_ACTIONABLE_BINS
    assert result.route_nodes == ()
    assert calls == 0


def test_structural_validation_blocks_optimization(synthetic_config):
    bin_metadata = BinMetadata("bin-1")
    result = plan_collection(
        request(
            synthetic_config,
            bins=(bin_metadata,),
            observations=(
                FillObservation("bin-1", 0.9, NOW),
                FillObservation("bin-1", 0.8, NOW),
            ),
            demands=(CollectionDemand("bin-1", 2, "kg"),),
        )
    )

    assert result.status == CollectionPlanStatus.INVALID_REQUEST
    assert result.solver_result is None
    assert "duplicate_observation_bin" in {item.code for item in result.diagnostics}


def test_capacity_infeasibility_is_preserved(synthetic_config):
    bins = (BinMetadata("bin-a"), BinMetadata("bin-b"))
    result = plan_collection(
        request(
            synthetic_config,
            bins=bins,
            observations=(
                FillObservation("bin-a", 0.9, NOW),
                FillObservation("bin-b", 0.9, NOW),
            ),
            demands=(
                CollectionDemand("bin-a", 6, "kg"),
                CollectionDemand("bin-b", 5, "kg"),
            ),
        )
    )

    assert result.status == CollectionPlanStatus.INFEASIBLE
    assert result.solver_result.status == PlanningStatus.INFEASIBLE
    assert "total_demand_exceeds_truck_capacity" in result.solver_result.diagnostics


def test_unavailable_connection_is_not_replaced_with_zero(synthetic_config):
    result = plan_collection(
        request(
            synthetic_config,
            bins=(BinMetadata("bin-1"),),
            observations=(FillObservation("bin-1", 0.9, NOW),),
            demands=(CollectionDemand("bin-1", 1, "kg"),),
            costs=TravelCostMatrix(
                ("synthetic-depot", "bin-1"),
                distances=((0, 2), (None, 0)),
                distance_unit="km",
            ),
        )
    )

    assert result.status == CollectionPlanStatus.INFEASIBLE
    assert result.solver_result.stops == ()


def test_non_success_solver_status_is_returned(synthetic_config):
    def backend(_planning_input, _config):
        return PlanningResult(PlanningStatus.TIME_LIMIT, diagnostics=("controlled",))

    result = plan_collection(
        request(
            synthetic_config,
            bins=(BinMetadata("bin-1"),),
            observations=(FillObservation("bin-1", 0.9, NOW),),
            demands=(CollectionDemand("bin-1", 1, "kg"),),
        ),
        backend=backend,
    )

    assert result.status == CollectionPlanStatus.TIME_LIMIT
    assert result.solver_result.diagnostics == ("controlled",)


def test_solver_exception_is_reported_as_solver_error(synthetic_config):
    def backend(_planning_input, _config):
        raise RuntimeError("controlled solver failure")

    result = plan_collection(
        request(
            synthetic_config,
            bins=(BinMetadata("bin-1"),),
            observations=(FillObservation("bin-1", 0.9, NOW),),
            demands=(CollectionDemand("bin-1", 1, "kg"),),
        ),
        backend=backend,
    )

    assert result.status == CollectionPlanStatus.SOLVER_ERROR
    assert result.solver_result.status == PlanningStatus.SOLVER_ERROR
    assert "solver_exception" in result.solver_result.diagnostics
    assert not result.bins[0].included_in_route


def test_invalid_observation_shape_is_rejected():
    with pytest.raises(ValueError, match="between 0 and 1"):
        FillObservation("bin-1", 1.1, NOW)
