"""Protocols for adapters and normalized travel-cost providers."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import isfinite
from numbers import Real
from typing import Protocol

from .models import BinMetadata, FillObservation, PlanningSnapshot


class MetadataProvider(Protocol):
    """Translate an external source into normalized bin metadata."""

    def load_bins(self) -> Sequence[BinMetadata]:
        """Return normalized bins without assuming a source representation."""


class ObservationProvider(Protocol):
    """Translate an external source into normalized observations."""

    def load_observations(self) -> Sequence[FillObservation]:
        """Return normalized observations; freshness is checked by context."""


@dataclass(frozen=True, slots=True)
class TravelCostMatrix:
    """Directed costs indexed by the explicit order in ``node_ids``.

    A ``None`` entry means the connection is unavailable or was not supplied;
    it is never interpreted as a zero-cost connection.
    """

    node_ids: tuple[str, ...]
    distances: tuple[tuple[float | None, ...], ...] | None = None
    durations_seconds: tuple[tuple[float | None, ...], ...] | None = None
    distance_unit: str | None = None
    duration_unit: str | None = None

    def __post_init__(self) -> None:
        node_ids = tuple(self.node_ids)
        if (
            not node_ids
            or any(not isinstance(node_id, str) or not node_id.strip() for node_id in node_ids)
            or len(set(node_ids)) != len(node_ids)
        ):
            raise ValueError("node_ids must be non-empty, non-blank, unique strings")
        object.__setattr__(self, "node_ids", node_ids)
        size = len(node_ids)
        for matrix, name in (
            (self.distances, "distances"),
            (self.durations_seconds, "durations_seconds"),
        ):
            if matrix is None:
                continue
            normalized = tuple(tuple(row) for row in matrix)
            if len(normalized) != size or any(len(row) != size for row in normalized):
                raise ValueError(f"{name} must be square with one row per node")
            for row in normalized:
                for value in row:
                    if value is None:
                        continue
                    if isinstance(value, bool) or not isinstance(value, Real):
                        raise ValueError(
                            f"{name} values must be finite, non-negative numbers or None"
                        )
                    if not isfinite(float(value)) or value < 0:
                        raise ValueError(
                            f"{name} values must be finite, non-negative numbers or None"
                        )
            object.__setattr__(self, name, normalized)
        if self.distances is None and self.durations_seconds is None:
            raise ValueError("at least one travel-cost matrix is required")
        if self.distances is not None and not self.distance_unit:
            raise ValueError("distance_unit is required when distances are supplied")
        if self.durations_seconds is not None and not self.duration_unit:
            raise ValueError("duration_unit is required when durations are supplied")


class TravelCostProvider(Protocol):
    """Provide normalized costs without exposing graph-library objects.

    Implementations accept a normalized snapshot and requested node order, then
    return costs using that exact order. They must declare units and represent
    explicitly unavailable connections as ``None``; validation of dimensions,
    values, and required identities belongs to the normalized boundary.
    """

    def costs_for(self, snapshot: PlanningSnapshot, node_ids: Sequence[str]) -> TravelCostMatrix:
        """Return costs for the requested node order and planning snapshot."""
