import pytest

from smart_bin_routing.contracts import TravelCostMatrix
from smart_bin_routing.models import PlanningStatus
from smart_bin_routing.prototype_config import KVA_BASEL, prototype_configuration


def test_travel_cost_matrix_preserves_explicit_order():
    matrix = TravelCostMatrix(
        node_ids=("kva-basel", "bin-1"),
        distances=((0.0, 2.5), (None, 0.0)),
        distance_unit="km",
    )

    assert matrix.node_ids == ("kva-basel", "bin-1")
    assert matrix.distances[1][0] is None


def test_travel_cost_matrix_requires_square_values():
    with pytest.raises(ValueError, match="square"):
        TravelCostMatrix(
            node_ids=("a", "b"),
            distances=((0.0,),),
            distance_unit="m",
        )


def test_travel_cost_matrix_rejects_non_numeric_values():
    with pytest.raises(ValueError, match="finite"):
        TravelCostMatrix(
            node_ids=("a",),
            distances=(("unknown",),),
            distance_unit="m",
        )


def test_prototype_configuration_is_kva_round_trip():
    config = prototype_configuration(
        truck_capacity=100,
        demand_unit="kg",
        yellow_threshold=0.5,
        red_threshold=0.8,
    )

    assert KVA_BASEL.node_id == "kva-basel"
    assert KVA_BASEL.vehicle_access_confirmed is False
    assert config.start_node_id == config.end_node_id == "kva-basel"


def test_planning_status_has_no_claim_of_optimality():
    assert PlanningStatus.NOT_RUN.value == "not_run"
