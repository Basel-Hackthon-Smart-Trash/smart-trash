from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))

from seed import (
    GROUP_ORDER,
    Bin,
    SeedError,
    fill_value,
    group_counts,
    load_bins,
    make_plan,
    parse_boundary,
    telemetry_rows,
)


def test_geojson_count_and_unique_ids() -> None:
    path = Path(__file__).parents[3] / "assets/geojson/bin-locations.geojson"
    bins = load_bins(path, 342)
    assert len(bins) == len({item.device_id for item in bins}) == 342
    assert bins == tuple(sorted(bins, key=lambda item: item.device_id))


def test_geojson_count_is_strict(tmp_path: Path) -> None:
    path = tmp_path / "bins.json"
    path.write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")
    with pytest.raises(SeedError, match="expected exactly 342"):
        load_bins(path, 342)


def test_geojson_identifiers_must_be_unique(tmp_path: Path) -> None:
    feature = {
        "type": "Feature",
        "id": "node/1",
        "properties": {"@id": "node/1"},
        "geometry": {"type": "Point", "coordinates": [7.6, 47.55]},
    }
    path = tmp_path / "bins.json"
    path.write_text(json.dumps({"type": "FeatureCollection", "features": [feature, feature]}), encoding="utf-8")
    with pytest.raises(SeedError, match="unique"):
        load_bins(path, 2)


def test_scaled_group_counts_assign_every_bin_once() -> None:
    assert group_counts(342) == {
        "hotspot": 34,
        "very_hot_hotspot": 17,
        "regular": 171,
        "low_traffic": 120,
    }
    bins = tuple(Bin(f"node/{number}") for number in range(342))
    plan = make_plan(bins, datetime(2025, 1, 1, tzinfo=UTC), datetime(2025, 1, 2, tzinfo=UTC), 7)
    assert len(plan.bins) == 342
    assert len({item.bin.device_id for item in plan.bins}) == 342
    assert {item.group for item in plan.bins} == set(GROUP_ORDER)
    assert {group: sum(item.group == group for item in plan.bins) for group in GROUP_ORDER} == group_counts(342)
    assert all(timedelta(0) <= item.start_offset < timedelta(hours=48) for item in plan.bins)


def test_five_minute_spacing_and_expected_count() -> None:
    bins = (Bin("node/1"),)
    start = datetime(2025, 1, 1, tzinfo=UTC)
    end = start + timedelta(hours=72)
    plan = make_plan(bins, start, end, 99)
    rows = list(telemetry_rows(plan.bins[0], plan, 99))
    assert plan.expected_rows == len(rows)
    assert all(b - a == timedelta(minutes=5) for (a, *_), (b, *_) in pairwise(rows))
    assert all(start <= row[0] < end for row in rows)


def test_timezone_boundaries_use_fixed_elapsed_spacing() -> None:
    start = parse_boundary("2026-03-29T00:00:00", "start")
    end = parse_boundary("2026-03-29T05:00:00", "end")
    assert end - start == timedelta(hours=4)
    assert (end - start) / timedelta(minutes=5) == 48


def test_fill_full_then_empty_and_exact_cadence() -> None:
    start = datetime(2025, 1, 1, tzinfo=UTC)
    end = start + timedelta(days=3, minutes=10)
    plan = make_plan((Bin("node/1"),), start, end, 4)
    item = plan.bins[0]
    full = start + item.fill_phase
    assert fill_value(item, full, start) == 100
    assert fill_value(item, full + timedelta(minutes=5), start) == 0
    assert fill_value(item, full + timedelta(minutes=10), start) > 0
    assert fill_value(item, full + item.cycle, start) == 100


def test_battery_is_bounded_and_replacement_is_independent_of_fill() -> None:
    start = datetime(2025, 1, 1, tzinfo=UTC)
    end = start + timedelta(days=400)
    first = make_plan((Bin("node/1"),), start, end, 12)
    second = make_plan((Bin("node/1"),), start, end, 12)
    rows = list(telemetry_rows(first.bins[0], first, 12))
    assert rows == list(telemetry_rows(second.bins[0], second, 12))
    batteries = [row[3] for row in rows]
    assert all(0 <= value <= 100 for value in batteries)
    assert timedelta(days=30) <= first.bins[0].initial_battery_lifetime <= timedelta(days=150)
    assert any(value == 0 for value in batteries)
    assert any(previous == 0 and current == 100 for previous, current in pairwise(batteries))
    assert first.bins[0].fill_phase == second.bins[0].fill_phase
    assert all(len(row) == 4 for row in rows), "weight is absent from generated records"
