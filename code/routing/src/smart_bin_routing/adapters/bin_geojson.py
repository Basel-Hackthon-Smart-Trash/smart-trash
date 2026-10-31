"""Offline adapter for the approved bin-location GeoJSON export."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ..models import BinMetadata, GeoLocation


class BinGeoJSONError(ValueError):
    """The bin export is not supported or does not satisfy its contract."""


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BinGeoJSONError(f"{field_name} must be a non-empty string")
    return value


def _parse_coordinates(value: object, feature_number: int) -> GeoLocation:
    if not isinstance(value, list) or len(value) != 2:
        raise BinGeoJSONError(f"feature {feature_number} geometry must be a 2D point")
    longitude, latitude = value
    try:
        return GeoLocation(longitude=longitude, latitude=latitude)
    except ValueError as error:
        raise BinGeoJSONError(f"feature {feature_number} has invalid coordinates") from error


def _validate_crs(payload: Mapping[str, Any]) -> None:
    # RFC 7946 GeoJSON has WGS84 positions and omits the legacy ``crs`` member.
    if "crs" in payload:
        raise BinGeoJSONError("only GeoJSON with an omitted CRS is supported")


def _parse_feature(
    feature: object,
    feature_number: int,
    *,
    source_path: Path,
    generator: str | None,
) -> BinMetadata:
    if not isinstance(feature, Mapping) or feature.get("type") != "Feature":
        raise BinGeoJSONError(f"feature {feature_number} must be a GeoJSON Feature")
    bin_id = _required_text(feature.get("id"), f"feature {feature_number} id")
    properties = feature.get("properties")
    if not isinstance(properties, Mapping):
        raise BinGeoJSONError(f"feature {feature_number} properties must be an object")
    source_id = _required_text(properties.get("@id"), f"feature {feature_number} properties.@id")
    if source_id != bin_id:
        raise BinGeoJSONError(f"feature {feature_number} id and properties.@id must match")
    geometry = feature.get("geometry")
    if not isinstance(geometry, Mapping) or geometry.get("type") != "Point":
        raise BinGeoJSONError(f"feature {feature_number} geometry must be a Point")
    location = _parse_coordinates(geometry.get("coordinates"), feature_number)
    provenance = [
        ("source_format", "GeoJSON"),
        ("source_path", str(source_path)),
    ]
    if generator is not None:
        provenance.append(("source_generator", generator))
    label = properties.get("description")
    if label is not None and (not isinstance(label, str) or not label.strip()):
        raise BinGeoJSONError(f"feature {feature_number} description must be a non-empty string")
    return BinMetadata(
        bin_id=bin_id,
        source_id=source_id,
        label=label,
        location=location,
        provenance=tuple(provenance),
    )


def load_bin_geojson(path: str | Path) -> tuple[BinMetadata, ...]:
    """Load bins from the approved offline GeoJSON export.

    The returned order is canonicalized by stable ``bin_id``. No observations,
    demand, coordinate transformation, or network access is performed.
    """

    source_path = Path(path)
    try:
        payload = json.loads(source_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BinGeoJSONError(f"unable to read GeoJSON export: {source_path}") from error
    if not isinstance(payload, Mapping) or payload.get("type") != "FeatureCollection":
        raise BinGeoJSONError("GeoJSON root must be a FeatureCollection")
    _validate_crs(payload)
    features = payload.get("features")
    if not isinstance(features, list):
        raise BinGeoJSONError("GeoJSON features must be an array")
    generator = payload.get("generator")
    if generator is not None:
        generator = _required_text(generator, "generator")
    bins = tuple(
        _parse_feature(
            feature,
            number,
            source_path=source_path,
            generator=generator,
        )
        for number, feature in enumerate(features, 1)
    )
    ids = [bin_metadata.bin_id for bin_metadata in bins]
    if len(set(ids)) != len(ids):
        raise BinGeoJSONError("GeoJSON feature IDs must be unique")
    return tuple(sorted(bins, key=lambda bin_metadata: bin_metadata.bin_id))
