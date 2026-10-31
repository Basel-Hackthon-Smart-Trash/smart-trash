from datetime import UTC, datetime, timedelta, timezone

import pytest

from smart_bin_routing.classification import (
    FillClassification,
    classify_fill,
    classify_snapshot,
)
from smart_bin_routing.models import (
    BinMetadata,
    FillObservation,
    PlanningConfig,
    PlanningSnapshot,
)

PLANNING_TIME = datetime(2026, 10, 31, 12, 0, tzinfo=UTC)


def config(**overrides) -> PlanningConfig:
    values = {
        "start_node_id": "synthetic-depot",
        "end_node_id": "synthetic-depot",
        "truck_capacity": 10,
        "demand_unit": "kg",
        "yellow_threshold": 0.6,
        "red_threshold": 0.8,
        "observation_max_age_seconds": 3600,
    }
    values.update(overrides)
    return PlanningConfig(**values)


@pytest.mark.parametrize(
    ("fill", "expected"),
    [
        (0.0, FillClassification.GREEN),
        (0.599, FillClassification.GREEN),
        (0.6, FillClassification.YELLOW),
        (0.7, FillClassification.YELLOW),
        (0.8, FillClassification.RED),
        (1.0, FillClassification.RED),
    ],
)
def test_classify_fill_uses_exact_fraction_boundaries(fill, expected):
    assert classify_fill(fill, config()) == expected


@pytest.mark.parametrize(
    "overrides",
    [
        {"yellow_threshold": 0.6, "red_threshold": 0.6},
        {"yellow_threshold": 0.8, "red_threshold": 0.6},
        {"yellow_threshold": -0.1, "red_threshold": 0.8},
        {"yellow_threshold": 0.6, "red_threshold": 1.1},
        {"yellow_threshold": float("nan"), "red_threshold": 0.8},
        {"yellow_threshold": 0.6, "red_threshold": float("inf")},
    ],
)
def test_config_rejects_invalid_classification_thresholds(overrides):
    with pytest.raises(ValueError):
        config(**overrides)


@pytest.mark.parametrize("age", [0, -1, float("nan"), float("inf")])
def test_config_rejects_invalid_observation_age(age):
    with pytest.raises(ValueError):
        config(observation_max_age_seconds=age)


def test_config_rejects_negative_future_skew():
    with pytest.raises(ValueError, match="allowed_future_skew_seconds"):
        config(allowed_future_skew_seconds=-1)


def test_fresh_observation_is_classified():
    snapshot = PlanningSnapshot(
        bins=(BinMetadata("bin-1"),),
        observations=(FillObservation("bin-1", 0.8, PLANNING_TIME),),
    )

    result = classify_snapshot(snapshot, config(), PLANNING_TIME)

    assert result.valid
    assert result.entries[0].classification == FillClassification.RED
    assert result.entries[0].diagnostics == ()


@pytest.mark.parametrize(
    ("observed_at", "expected_code"),
    [
        (PLANNING_TIME - timedelta(seconds=3600), None),
        (PLANNING_TIME - timedelta(seconds=3600, microseconds=1), "stale_observation"),
        (PLANNING_TIME + timedelta(seconds=1), "future_observation"),
    ],
)
def test_observation_context_is_checked(observed_at, expected_code):
    snapshot = PlanningSnapshot(
        bins=(BinMetadata("bin-1"),),
        observations=(FillObservation("bin-1", 0.5, observed_at),),
    )

    result = classify_snapshot(snapshot, config(), PLANNING_TIME)
    entry = result.entries[0]

    if expected_code is None:
        assert entry.classification == FillClassification.GREEN
        assert entry.diagnostics == ()
    else:
        assert entry.classification == FillClassification.UNKNOWN
        assert entry.diagnostics[0].code == expected_code


def test_allowed_future_boundary_is_valid_and_preserves_timestamp():
    observed_at = PLANNING_TIME + timedelta(seconds=30)
    snapshot = PlanningSnapshot(
        bins=(BinMetadata("bin-1"),),
        observations=(FillObservation("bin-1", 0.7, observed_at),),
    )

    result = classify_snapshot(
        snapshot,
        config(allowed_future_skew_seconds=30),
        PLANNING_TIME,
    )

    assert result.entries[0].classification == FillClassification.YELLOW
    assert result.entries[0].observation.observed_at == observed_at


def test_observation_just_beyond_allowed_future_boundary_is_unknown():
    observed_at = PLANNING_TIME + timedelta(seconds=31)
    snapshot = PlanningSnapshot(
        bins=(BinMetadata("bin-1"),),
        observations=(FillObservation("bin-1", 0.7, observed_at),),
    )

    result = classify_snapshot(
        snapshot,
        config(allowed_future_skew_seconds=30),
        PLANNING_TIME,
    )

    assert result.entries[0].classification == FillClassification.UNKNOWN
    assert result.entries[0].diagnostics[0].code == "future_observation"


def test_missing_observation_remains_unknown():
    result = classify_snapshot(
        PlanningSnapshot(bins=(BinMetadata("bin-1"),)),
        config(),
        PLANNING_TIME,
    )

    assert result.entries[0].classification == FillClassification.UNKNOWN
    assert result.entries[0].diagnostics[0].code == "missing_observation"


def test_output_preserves_bin_order_and_is_repeatable():
    bins = (BinMetadata("bin-2"), BinMetadata("bin-1"))
    snapshot = PlanningSnapshot(bins=bins)

    first = classify_snapshot(snapshot, config(), PLANNING_TIME)
    second = classify_snapshot(snapshot, config(), PLANNING_TIME)

    assert [entry.bin_id for entry in first.entries] == ["bin-2", "bin-1"]
    assert first == second
    assert snapshot == PlanningSnapshot(bins=bins)


def test_equivalent_timezone_offsets_have_equivalent_results():
    utc_observation = FillObservation("bin-1", 0.7, PLANNING_TIME - timedelta(minutes=30))
    offset_observation = FillObservation(
        "bin-1",
        0.7,
        datetime(2026, 10, 31, 12, 30, tzinfo=timezone(timedelta(hours=1))),
    )

    utc_result = classify_snapshot(
        PlanningSnapshot(bins=(BinMetadata("bin-1"),), observations=(utc_observation,)),
        config(),
        PLANNING_TIME,
    )
    offset_result = classify_snapshot(
        PlanningSnapshot(bins=(BinMetadata("bin-1"),), observations=(offset_observation,)),
        config(),
        PLANNING_TIME,
    )

    assert utc_result.entries[0].classification == offset_result.entries[0].classification
    assert utc_result.entries[0].diagnostics == offset_result.entries[0].diagnostics


def test_empty_snapshot_has_no_entries():
    result = classify_snapshot(PlanningSnapshot(bins=()), config(), PLANNING_TIME)

    assert result.valid
    assert result.entries == ()


def test_structural_errors_are_not_classified():
    snapshot = PlanningSnapshot(
        bins=(BinMetadata("bin-1"),),
        observations=(
            FillObservation("bin-1", 0.5, PLANNING_TIME),
            FillObservation("bin-1", 0.7, PLANNING_TIME),
        ),
    )

    result = classify_snapshot(snapshot, config(), PLANNING_TIME)

    assert not result.valid
    assert result.entries == ()
    assert result.validation.diagnostics[0].code == "duplicate_observation_bin"


def test_naive_planning_time_is_rejected():
    with pytest.raises(ValueError, match="timezone-aware"):
        classify_snapshot(
            PlanningSnapshot(bins=(BinMetadata("bin-1"),)), config(), datetime(2026, 10, 31, 12)
        )
