"""Synthetic-only fixtures for isolated contract tests."""

from datetime import UTC, datetime

import pytest

from smart_bin_routing.models import (
    BinMetadata,
    CollectionDemand,
    FillObservation,
    PlanningConfig,
    PlanningSnapshot,
)


@pytest.fixture
def synthetic_bin() -> BinMetadata:
    return BinMetadata(bin_id="synthetic-bin-1", label="Synthetic fixture")


@pytest.fixture
def synthetic_observation(synthetic_bin: BinMetadata) -> FillObservation:
    return FillObservation(
        bin_id=synthetic_bin.bin_id,
        fill_fraction=0.75,
        observed_at=datetime(2026, 10, 31, 12, 0, tzinfo=UTC),
    )


@pytest.fixture
def synthetic_config() -> PlanningConfig:
    return PlanningConfig(
        start_node_id="synthetic-depot",
        end_node_id="synthetic-depot",
        truck_capacity=10.0,
        demand_unit="kg",
        yellow_threshold=0.5,
        red_threshold=0.8,
    )


@pytest.fixture
def synthetic_snapshot(
    synthetic_bin: BinMetadata,
    synthetic_observation: FillObservation,
) -> PlanningSnapshot:
    return PlanningSnapshot(
        bins=(synthetic_bin,),
        observations=(synthetic_observation,),
        demands=(CollectionDemand(synthetic_bin.bin_id, 2.0, "kg"),),
    )
