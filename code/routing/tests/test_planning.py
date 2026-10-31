from datetime import UTC, datetime

import pytest

from smart_bin_routing import (
    BinMetadata,
    CollectionDemand,
    FillObservation,
    PlanningSnapshot,
    assemble_planning_input,
    classify_snapshot,
)
from smart_bin_routing.contracts import TravelCostMatrix

PLANNING_TIME = datetime(2026, 10, 31, 12, 0, tzinfo=UTC)


def classified_snapshot(config, *, bins, observations=(), demands=()):
    return classify_snapshot(
        PlanningSnapshot(tuple(bins), tuple(observations), tuple(demands)),
        config,
        PLANNING_TIME,
    )


def costs(*node_ids, distances=None):
    size = len(node_ids)
    return TravelCostMatrix(
        node_ids=tuple(node_ids),
        distances=distances or tuple(tuple(0.0 for _ in range(size)) for _ in range(size)),
        distance_unit="km",
    )


def test_assembly_reuses_classification_and_builds_solver_input(synthetic_config):
    result = assemble_planning_input(
        classified_snapshot(
            synthetic_config,
            bins=(BinMetadata("synthetic-bin-1"),),
            observations=(FillObservation("synthetic-bin-1", 0.9, PLANNING_TIME),),
            demands=(CollectionDemand("synthetic-bin-1", 2, "kg"),),
        ),
        costs("synthetic-depot", "synthetic-bin-1"),
    )

    assert result.valid
    assert result.planning_input.candidates[0].bin_id == "synthetic-bin-1"
    assert result.planning_input.candidates[0].classification.value == "red"
    assert result.planning_input.candidates[0].demand.unit == "kg"


def test_assembly_preserves_classified_order_and_matrix_identity_order(synthetic_config):
    result = assemble_planning_input(
        classified_snapshot(
            synthetic_config,
            bins=(BinMetadata("bin-2"), BinMetadata("bin-1")),
            observations=(
                FillObservation("bin-2", 0.9, PLANNING_TIME),
                FillObservation("bin-1", 0.7, PLANNING_TIME),
            ),
            demands=(
                CollectionDemand("bin-2", 2, "kg"),
                CollectionDemand("bin-1", 3, "kg"),
            ),
        ),
        costs("synthetic-depot", "bin-1", "bin-2"),
    )

    assert [candidate.bin_id for candidate in result.planning_input.candidates] == [
        "bin-2",
        "bin-1",
    ]
    assert result.planning_input.travel_costs.node_ids == ("synthetic-depot", "bin-1", "bin-2")


def test_missing_demand_is_an_exclusion_not_zero(
    synthetic_config, synthetic_bin, synthetic_observation
):
    result = assemble_planning_input(
        classified_snapshot(
            synthetic_config,
            bins=(synthetic_bin,),
            observations=(synthetic_observation,),
        ),
        costs("synthetic-depot", synthetic_bin.bin_id),
    )

    assert result.valid
    assert result.planning_input.candidates == ()
    assert any(item.code == "missing_collection_demand" for item in result.diagnostics)


def test_incompatible_demand_is_blocking(synthetic_config, synthetic_bin):
    classified = classified_snapshot(
        synthetic_config,
        bins=(synthetic_bin,),
        demands=(CollectionDemand(synthetic_bin.bin_id, 2, "liters"),),
    )

    result = assemble_planning_input(classified, costs("synthetic-depot", synthetic_bin.bin_id))

    assert not result.valid
    assert result.planning_input is None
    assert any(item.code == "demand_unit_mismatch" for item in result.diagnostics)


def test_unknown_classification_is_visible_but_not_route_ready(synthetic_config, synthetic_bin):
    result = assemble_planning_input(
        classified_snapshot(
            synthetic_config,
            bins=(synthetic_bin,),
            demands=(CollectionDemand(synthetic_bin.bin_id, 2, "kg"),),
        ),
        costs("synthetic-depot", synthetic_bin.bin_id),
    )

    assert result.valid
    assert result.planning_input.candidates == ()
    assert any(item.code == "unknown_classification_sensor_check" for item in result.diagnostics)


def test_missing_candidate_node_is_an_exclusion(
    synthetic_config, synthetic_bin, synthetic_observation
):
    result = assemble_planning_input(
        classified_snapshot(
            synthetic_config,
            bins=(synthetic_bin,),
            observations=(synthetic_observation,),
            demands=(CollectionDemand(synthetic_bin.bin_id, 2, "kg"),),
        ),
        costs("synthetic-depot"),
    )

    assert result.valid
    assert result.planning_input.candidates == ()
    assert any(item.code == "missing_candidate_node" for item in result.diagnostics)


def test_oversized_demand_is_preserved_with_diagnostic(
    synthetic_config, synthetic_bin, synthetic_observation
):
    result = assemble_planning_input(
        classified_snapshot(
            synthetic_config,
            bins=(synthetic_bin,),
            observations=(synthetic_observation,),
            demands=(CollectionDemand(synthetic_bin.bin_id, 11, "kg"),),
        ),
        costs("synthetic-depot", synthetic_bin.bin_id),
    )

    candidate = result.planning_input.candidates[0]
    assert candidate.demand.amount == 11
    assert any(item.code == "demand_exceeds_truck_capacity" for item in candidate.diagnostics)


def test_asymmetric_and_unreachable_costs_are_preserved(
    synthetic_config, synthetic_bin, synthetic_observation
):
    matrix = costs(
        "synthetic-depot",
        synthetic_bin.bin_id,
        distances=((0.0, 4.0), (None, 0.0)),
    )
    result = assemble_planning_input(
        classified_snapshot(
            synthetic_config,
            bins=(synthetic_bin,),
            observations=(synthetic_observation,),
            demands=(CollectionDemand(synthetic_bin.bin_id, 2, "kg"),),
        ),
        matrix,
    )

    assert result.valid
    assert result.planning_input.travel_costs.distances == ((0.0, 4.0), (None, 0.0))


def test_missing_depot_is_blocking(synthetic_config, synthetic_bin):
    classified = classified_snapshot(
        synthetic_config,
        bins=(synthetic_bin,),
        demands=(CollectionDemand(synthetic_bin.bin_id, 2, "kg"),),
    )

    result = assemble_planning_input(classified, costs(synthetic_bin.bin_id))

    assert not result.valid
    assert result.planning_input is None
    assert any(item.code == "missing_depot_node" for item in result.diagnostics)


def test_travel_cost_matrix_rejects_duplicate_ids_and_malformed_dimensions():
    with pytest.raises(ValueError, match="unique"):
        costs("a", "a")
    with pytest.raises(ValueError, match="square"):
        TravelCostMatrix(node_ids=("a", "b"), distances=((0.0,),), distance_unit="km")


def test_duration_matrix_requires_explicit_unit():
    with pytest.raises(ValueError, match="duration_unit"):
        TravelCostMatrix(node_ids=("a",), durations_seconds=((0.0,),))
