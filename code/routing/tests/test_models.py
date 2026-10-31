from datetime import UTC, datetime

import pytest

from smart_bin_routing.models import FillObservation, GeoLocation, PlanningConfig


def test_fill_observation_accepts_normalized_fraction_and_aware_timestamp():
    observation = FillObservation(
        bin_id="bin-1",
        fill_fraction=1,
        observed_at=datetime(2026, 10, 31, tzinfo=UTC),
    )

    assert observation.fill_fraction == 1.0


@pytest.mark.parametrize("value", [-0.01, 1.01, float("nan"), float("inf")])
def test_fill_observation_rejects_invalid_fraction(value):
    with pytest.raises(ValueError):
        FillObservation("bin-1", value, datetime(2026, 10, 31, tzinfo=UTC))


def test_fill_observation_rejects_naive_timestamp():
    with pytest.raises(ValueError, match="timezone-aware"):
        FillObservation("bin-1", 0.2, datetime(2026, 10, 31))


def test_location_has_explicit_coordinate_fields():
    location = GeoLocation(longitude=7.6, latitude=47.55)

    assert location.longitude == 7.6
    assert location.latitude == 47.55


def test_planning_config_rejects_reversed_thresholds():
    with pytest.raises(ValueError, match="thresholds"):
        PlanningConfig("start", "end", 10, "kg", 0.8, 0.5, 3600)
