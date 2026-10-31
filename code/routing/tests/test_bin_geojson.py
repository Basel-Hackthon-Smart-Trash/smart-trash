import json
from pathlib import Path

import pytest

from smart_bin_routing.adapters.bin_geojson import BinGeoJSONError, load_bin_geojson


def _feature(bin_id: str = "node/1", coordinates: list[object] | None = None) -> dict:
    return {
        "type": "Feature",
        "id": bin_id,
        "properties": {"@id": bin_id, "description": "fixture bin"},
        "geometry": {"type": "Point", "coordinates": coordinates or [7.6, 47.55]},
    }


def _write_export(tmp_path: Path, *features: dict, **extra: object) -> Path:
    payload = {"type": "FeatureCollection", "features": list(features), **extra}
    path = tmp_path / "bins.geojson"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_loads_valid_bins_and_preserves_source_metadata(tmp_path: Path) -> None:
    path = _write_export(
        tmp_path,
        _feature("node/2", [7.61, 47.56]),
        _feature("node/1"),
        generator="test-export",
        timestamp="not-an-observation-time",
    )

    bins = load_bin_geojson(path)

    assert [item.bin_id for item in bins] == ["node/1", "node/2"]
    assert bins[1].source_id == "node/2"
    assert bins[1].location.longitude == 7.61
    assert bins[1].location.latitude == 47.56
    assert dict(bins[1].provenance) == {
        "source_format": "GeoJSON",
        "source_path": str(path),
        "source_generator": "test-export",
    }


def test_loads_actual_asset() -> None:
    path = Path(__file__).parents[3] / "assets/geojson/bin-locations.geojson"

    bins = load_bin_geojson(path)

    assert len(bins) == 342
    assert bins[0].bin_id == "node/10072039086"


@pytest.mark.parametrize(
    ("feature", "message"),
    [
        ({**_feature(), "geometry": {"type": "LineString", "coordinates": []}}, "Point"),
        ({**_feature(), "geometry": {"type": "Point", "coordinates": [7.6]}}, "2D point"),
        ({**_feature(), "geometry": None}, "Point"),
    ],
)
def test_rejects_invalid_geometry(tmp_path: Path, feature: dict, message: str) -> None:
    with pytest.raises(BinGeoJSONError, match=message):
        load_bin_geojson(_write_export(tmp_path, feature))


@pytest.mark.parametrize(
    "coordinates",
    [
        [None, 47.55],
        [float("nan"), 47.55],
        [7.6, float("inf")],
        [181, 47.55],
        [7.6, -91],
    ],
)
def test_rejects_missing_non_finite_and_out_of_range_coordinates(
    tmp_path: Path, coordinates: list[object]
) -> None:
    with pytest.raises(BinGeoJSONError, match="invalid coordinates"):
        load_bin_geojson(_write_export(tmp_path, _feature(coordinates=coordinates)))


def test_rejects_missing_identity_and_mismatched_source_identity(tmp_path: Path) -> None:
    missing = _feature()
    del missing["id"]
    with pytest.raises(BinGeoJSONError, match="id must be"):
        load_bin_geojson(_write_export(tmp_path, missing))

    mismatch = _feature()
    mismatch["properties"]["@id"] = "node/other"
    with pytest.raises(BinGeoJSONError, match="must match"):
        load_bin_geojson(_write_export(tmp_path, mismatch))


def test_rejects_duplicate_identity(tmp_path: Path) -> None:
    with pytest.raises(BinGeoJSONError, match="unique"):
        load_bin_geojson(_write_export(tmp_path, _feature(), _feature()))


def test_rejects_unsupported_crs(tmp_path: Path) -> None:
    with pytest.raises(BinGeoJSONError, match="CRS"):
        load_bin_geojson(_write_export(tmp_path, _feature(), crs={"name": "EPSG:2056"}))


def test_mapping_is_stable_and_independent_of_feature_order(tmp_path: Path) -> None:
    first = load_bin_geojson(_write_export(tmp_path, _feature("node/2"), _feature("node/1")))
    second = load_bin_geojson(_write_export(tmp_path, _feature("node/1"), _feature("node/2")))

    assert [(item.bin_id, item.location) for item in first] == [
        (item.bin_id, item.location) for item in second
    ]
