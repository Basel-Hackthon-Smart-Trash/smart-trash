"""Explicit OSMnx graph acquisition and offline persistence.

The routing core never receives an OSMnx graph. This adapter owns geographic
acquisition, graph files, and the provenance needed to decide whether a cached
graph is safe to reuse.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import tempfile
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any

from ..models import GeoLocation

SCHEMA_VERSION = 1
GRAPH_FILENAME = "graph.graphml"
METADATA_FILENAME = "graph.json"


class GraphError(ValueError):
    """A graph request, graph artifact, or provenance record is invalid."""


@dataclass(frozen=True, slots=True)
class GraphArea:
    """An explicit WGS84 polygon used as the graph acquisition boundary."""

    polygon_coordinates: tuple[tuple[tuple[float, float], ...], ...]
    margin_meters: float = 0.0

    def __post_init__(self) -> None:
        if not self.polygon_coordinates:
            raise GraphError("area polygon must contain at least one ring")
        if not math.isfinite(self.margin_meters) or self.margin_meters < 0:
            raise GraphError("area margin_meters must be finite and non-negative")
        for ring in self.polygon_coordinates:
            if len(ring) < 4 or ring[0] != ring[-1]:
                raise GraphError("area polygon rings must be closed with at least four points")
            for longitude, latitude in ring:
                if not (-180 <= longitude <= 180 and -90 <= latitude <= 90):
                    raise GraphError("area polygon coordinates must be valid WGS84 values")

    @classmethod
    def from_bbox(
        cls, west: float, south: float, east: float, north: float, *, margin_meters: float
    ) -> GraphArea:
        if not west < east or not south < north:
            raise GraphError("area bbox must have west < east and south < north")
        return cls(
            (((west, south), (east, south), (east, north), (west, north), (west, south)),),
            margin_meters,
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "crs": "EPSG:4326",
            "polygon_coordinates": [
                [[longitude, latitude] for longitude, latitude in ring]
                for ring in self.polygon_coordinates
            ],
            "margin_meters": self.margin_meters,
        }


@dataclass(frozen=True, slots=True)
class GraphSettings:
    """All graph construction and speed assumptions that affect the artifact."""

    network_type: str = "drive"
    custom_filter: str | None = None
    simplify: bool = True
    retain_all: bool = True
    truncate_by_edge: bool = False
    tagged_speeds_kph: tuple[tuple[str, float], ...] = ()
    speed_fallback_kph: float | None = None

    def __post_init__(self) -> None:
        if not self.network_type.strip():
            raise GraphError("network_type must be non-empty")
        for highway, speed in self.tagged_speeds_kph:
            if not highway.strip() or not math.isfinite(speed) or speed <= 0:
                raise GraphError("tagged speeds must contain positive finite values")
        if self.speed_fallback_kph is not None and (
            not math.isfinite(self.speed_fallback_kph) or self.speed_fallback_kph <= 0
        ):
            raise GraphError("speed_fallback_kph must be positive and finite when provided")

    def as_dict(self) -> dict[str, object]:
        values = asdict(self)
        values["tagged_speeds_kph"] = [list(item) for item in self.tagged_speeds_kph]
        return values


@dataclass(frozen=True, slots=True)
class GraphProvenance:
    schema_version: int
    graph_sha256: str
    acquired_at: datetime
    area: dict[str, object]
    settings: dict[str, object]
    versions: dict[str, str]

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise GraphError("unsupported graph provenance schema version")
        if self.acquired_at.tzinfo is None or self.acquired_at.utcoffset() is None:
            raise GraphError("acquired_at must be timezone-aware")
        if len(self.graph_sha256) != 64:
            raise GraphError("graph_sha256 must be a SHA-256 hex digest")


@dataclass(frozen=True, slots=True)
class GraphArtifact:
    graph: Any
    provenance: GraphProvenance
    graph_path: Path


def _geometry(area: GraphArea) -> Any:
    from shapely.geometry import Polygon

    polygon = Polygon(area.polygon_coordinates[0], area.polygon_coordinates[1:])
    if polygon.is_empty or not polygon.is_valid:
        raise GraphError("area polygon is empty or invalid")
    return polygon


def _expanded_geometry(area: GraphArea) -> Any:
    polygon = _geometry(area)
    if not area.margin_meters:
        return polygon
    import osmnx as ox

    projected, crs = ox.projection.project_geometry(polygon, crs="EPSG:4326")
    expanded = projected.buffer(area.margin_meters)
    return ox.projection.project_geometry(expanded, crs=crs, to_crs="EPSG:4326")[0]


def _validate_coverage(area: GraphArea, coverage_points: Sequence[GeoLocation]) -> None:
    from shapely.geometry import Point

    polygon = _expanded_geometry(area)
    outside = [
        point
        for point in coverage_points
        if not polygon.covers(Point(point.longitude, point.latitude))
    ]
    if outside:
        raise GraphError("configured area does not cover every bin and depot coordinate")


def _validate_graph_edges(graph: Any) -> None:
    for source, target, key, data in graph.edges(keys=True, data=True):
        for name in ("length", "speed_kph", "travel_time"):
            value = data.get(name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
            ):
                raise GraphError(f"edge {source!r}->{target!r}/{key!r} lacks valid {name}")
            if value <= 0:
                raise GraphError(f"edge {source!r}->{target!r}/{key!r} has non-positive {name}")


def add_edge_travel_times(graph: Any, settings: GraphSettings) -> Any:
    """Apply explicitly configured speeds and calculate required edge times."""

    import osmnx as ox

    if settings.tagged_speeds_kph:
        ox.add_edge_speeds(graph, hwy_speeds=dict(settings.tagged_speeds_kph))
    elif settings.speed_fallback_kph is not None:
        ox.add_edge_speeds(graph, fallback=settings.speed_fallback_kph)
    else:
        missing = [
            data for _, _, _, data in graph.edges(keys=True, data=True) if "speed_kph" not in data
        ]
        if missing:
            raise GraphError("graph has edges without speeds and no speed imputation is configured")
    try:
        ox.add_edge_travel_times(graph)
    except (KeyError, TypeError, ValueError) as error:
        raise GraphError("graph edge lengths or speeds cannot produce travel times") from error
    _validate_graph_edges(graph)
    return graph


def _versions() -> dict[str, str]:
    return {
        "python": platform.python_version(),
        "osmnx": version("osmnx"),
        "networkx": version("networkx"),
        "smart-bin-routing": version("smart-bin-routing"),
    }


def acquire_graph(
    area: GraphArea,
    coverage_points: Sequence[GeoLocation],
    settings: GraphSettings,
) -> Any:
    """Download one explicitly requested driving graph from OpenStreetMap."""

    _validate_coverage(area, coverage_points)
    import osmnx as ox

    graph = ox.graph_from_polygon(
        _expanded_geometry(area),
        network_type=settings.network_type,
        custom_filter=settings.custom_filter,
        simplify=settings.simplify,
        retain_all=settings.retain_all,
        truncate_by_edge=settings.truncate_by_edge,
    )
    return add_edge_travel_times(graph, settings)


def save_graph(
    graph: Any, directory: str | Path, *, area: GraphArea, settings: GraphSettings
) -> GraphArtifact:
    """Persist a validated graph and its provenance atomically."""

    _validate_graph_edges(graph)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    graph_path = directory / GRAPH_FILENAME
    metadata_path = directory / METADATA_FILENAME
    temporary = Path(tempfile.mktemp(prefix=".graph-", suffix=".graphml", dir=directory))
    try:
        import osmnx as ox

        ox.save_graphml(graph, temporary)
        digest = hashlib.sha256(temporary.read_bytes()).hexdigest()
        provenance = GraphProvenance(
            SCHEMA_VERSION,
            digest,
            datetime.now(UTC),
            area.as_dict(),
            settings.as_dict(),
            _versions(),
        )
        graph_path.unlink(missing_ok=True)
        temporary.replace(graph_path)
        metadata_path.write_text(
            json.dumps(
                {
                    "schema_version": provenance.schema_version,
                    "graph_sha256": provenance.graph_sha256,
                    "acquired_at": provenance.acquired_at.isoformat(),
                    "area": provenance.area,
                    "settings": provenance.settings,
                    "versions": provenance.versions,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        return GraphArtifact(graph, provenance, graph_path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def load_graph(
    directory: str | Path,
    *,
    expected_area: GraphArea | None = None,
    expected_settings: GraphSettings | None = None,
) -> GraphArtifact:
    """Load a graph only from its exact cache and matching provenance."""

    directory = Path(directory)
    graph_path = directory / GRAPH_FILENAME
    metadata_path = directory / METADATA_FILENAME
    if not graph_path.is_file() or not metadata_path.is_file():
        raise GraphError(f"graph cache is incomplete: {directory}")
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        digest = hashlib.sha256(graph_path.read_bytes()).hexdigest()
        if payload.get("graph_sha256") != digest:
            raise GraphError("graph hash does not match provenance")
        provenance = GraphProvenance(
            int(payload["schema_version"]),
            str(payload["graph_sha256"]),
            datetime.fromisoformat(str(payload["acquired_at"])),
            dict(payload["area"]),
            dict(payload["settings"]),
            {str(key): str(value) for key, value in dict(payload["versions"]).items()},
        )
        if expected_area is not None and provenance.area != expected_area.as_dict():
            raise GraphError("graph area does not match the requested area")
        if expected_settings is not None and provenance.settings != expected_settings.as_dict():
            raise GraphError("graph settings do not match the requested settings")
        import osmnx as ox

        graph = ox.load_graphml(graph_path)
        _validate_graph_edges(graph)
        return GraphArtifact(graph, provenance, graph_path)
    except GraphError:
        raise
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        KeyError,
        TypeError,
        ValueError,
    ) as error:
        raise GraphError(
            f"graph cache is corrupt or has invalid provenance: {directory}"
        ) from error


def _parse_point(value: str) -> GeoLocation:
    try:
        longitude, latitude = (float(item) for item in value.split(","))
        return GeoLocation(longitude, latitude)
    except (TypeError, ValueError) as error:
        raise GraphError("points must use longitude,latitude syntax") from error


def _cli() -> int:
    parser = argparse.ArgumentParser(
        description="Explicit OSMnx graph acquisition and offline loading"
    )
    subparsers = parser.add_subparsers(dest="action", required=True)
    acquire = subparsers.add_parser(
        "acquire", help="download a graph; this is the only online action"
    )
    acquire.add_argument("--output", type=Path, required=True)
    acquire.add_argument(
        "--bbox", nargs=4, type=float, metavar=("WEST", "SOUTH", "EAST", "NORTH"), required=True
    )
    acquire.add_argument("--margin-meters", type=float, required=True)
    acquire.add_argument("--coverage-point", action="append", required=True, metavar="LON,LAT")
    acquire.add_argument("--speed-fallback-kph", type=float)
    load = subparsers.add_parser("load", help="load an existing graph without downloading")
    load.add_argument("directory", type=Path)
    args = parser.parse_args()
    try:
        if args.action == "load":
            artifact = load_graph(args.directory)
            print(f"loaded {artifact.graph_path} ({artifact.provenance.graph_sha256})")
            return 0
        area = GraphArea.from_bbox(*args.bbox, margin_meters=args.margin_meters)
        settings = GraphSettings(speed_fallback_kph=args.speed_fallback_kph)
        graph = acquire_graph(
            area, tuple(_parse_point(value) for value in args.coverage_point), settings
        )
        artifact = save_graph(graph, args.output, area=area, settings=settings)
        print(f"saved {artifact.graph_path} ({artifact.provenance.graph_sha256})")
        return 0
    except GraphError as error:
        parser.error(str(error))
        return 2


if __name__ == "__main__":
    raise SystemExit(_cli())
