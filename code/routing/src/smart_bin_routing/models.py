"""Small, source-independent data models used by the routing core.

These models validate structure only. They do not determine whether an
observation is fresh, classify fill levels, or calculate a route.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from math import isfinite
from numbers import Real


def _require_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _require_finite_number(value: Real, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{field_name} must be a finite number")
    converted = float(value)
    if not isfinite(converted):
        raise ValueError(f"{field_name} must be a finite number")
    return converted


@dataclass(frozen=True, slots=True)
class GeoLocation:
    """Optional WGS84-style coordinate fields supplied by a future adapter.

    The core does not infer a coordinate reference system or geocode an
    address. These names are explicit to avoid ambiguous coordinate tuples.
    """

    longitude: float
    latitude: float

    def __post_init__(self) -> None:
        longitude = _require_finite_number(self.longitude, "longitude")
        latitude = _require_finite_number(self.latitude, "latitude")
        if not -180 <= longitude <= 180:
            raise ValueError("longitude must be between -180 and 180")
        if not -90 <= latitude <= 90:
            raise ValueError("latitude must be between -90 and 90")
        object.__setattr__(self, "longitude", longitude)
        object.__setattr__(self, "latitude", latitude)


@dataclass(frozen=True, slots=True)
class BinMetadata:
    """Normalized identity and optional descriptive metadata for one bin."""

    bin_id: str
    source_id: str | None = None
    label: str | None = None
    location: GeoLocation | None = None

    def __post_init__(self) -> None:
        _require_text(self.bin_id, "bin_id")
        if self.source_id is not None:
            _require_text(self.source_id, "source_id")
        if self.label is not None:
            _require_text(self.label, "label")


@dataclass(frozen=True, slots=True)
class FillObservation:
    """A normalized fill fraction observed at a timezone-aware instant."""

    bin_id: str
    fill_fraction: float
    observed_at: datetime

    def __post_init__(self) -> None:
        _require_text(self.bin_id, "bin_id")
        fill_fraction = _require_finite_number(self.fill_fraction, "fill_fraction")
        if not 0 <= fill_fraction <= 1:
            raise ValueError("fill_fraction must be between 0 and 1 inclusive")
        if not isinstance(self.observed_at, datetime) or self.observed_at.tzinfo is None:
            raise ValueError("observed_at must be timezone-aware")
        if self.observed_at.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        object.__setattr__(self, "fill_fraction", fill_fraction)


@dataclass(frozen=True, slots=True)
class CollectionDemand:
    """Explicit collection demand for one bin in a declared unit."""

    bin_id: str
    amount: float
    unit: str
    estimated: bool = False

    def __post_init__(self) -> None:
        _require_text(self.bin_id, "bin_id")
        amount = _require_finite_number(self.amount, "amount")
        if amount < 0:
            raise ValueError("amount must not be negative")
        _require_text(self.unit, "unit")
        if not isinstance(self.estimated, bool):
            raise ValueError("estimated must be a boolean")
        object.__setattr__(self, "amount", amount)


class DemandPolicy(StrEnum):
    """Whether planning accepts only supplied demand or marked estimates."""

    EXPLICIT_ONLY = "explicit_only"
    ALLOW_MARKED_ESTIMATES = "allow_marked_estimates"


@dataclass(frozen=True, slots=True)
class PlanningConfig:
    """Configuration required to validate a future single-truck plan.

    Thresholds are represented here but deliberately not applied. Boundary
    behavior belongs to the classification stage.
    """

    start_node_id: str
    end_node_id: str
    truck_capacity: float
    demand_unit: str
    yellow_threshold: float
    red_threshold: float
    demand_policy: DemandPolicy = DemandPolicy.EXPLICIT_ONLY
    route_duration_limit_seconds: float | None = None
    observation_max_age_seconds: float | None = None

    def __post_init__(self) -> None:
        _require_text(self.start_node_id, "start_node_id")
        _require_text(self.end_node_id, "end_node_id")
        capacity = _require_finite_number(self.truck_capacity, "truck_capacity")
        if capacity <= 0:
            raise ValueError("truck_capacity must be greater than zero")
        _require_text(self.demand_unit, "demand_unit")
        if not isinstance(self.demand_policy, DemandPolicy):
            raise ValueError("demand_policy must be a DemandPolicy")
        yellow = _require_finite_number(self.yellow_threshold, "yellow_threshold")
        red = _require_finite_number(self.red_threshold, "red_threshold")
        if not 0 <= yellow < red <= 1:
            raise ValueError("thresholds must satisfy 0 <= yellow < red <= 1")
        for value, name in (
            (self.route_duration_limit_seconds, "route_duration_limit_seconds"),
            (self.observation_max_age_seconds, "observation_max_age_seconds"),
        ):
            if value is not None and _require_finite_number(value, name) <= 0:
                raise ValueError(f"{name} must be greater than zero when provided")
        object.__setattr__(self, "truck_capacity", capacity)
        object.__setattr__(self, "yellow_threshold", yellow)
        object.__setattr__(self, "red_threshold", red)


@dataclass(frozen=True, slots=True)
class PlanningSnapshot:
    """Immutable normalized inputs for one planning attempt."""

    bins: tuple[BinMetadata, ...]
    observations: tuple[FillObservation, ...] = ()
    demands: tuple[CollectionDemand, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "bins", tuple(self.bins))
        object.__setattr__(self, "observations", tuple(self.observations))
        object.__setattr__(self, "demands", tuple(self.demands))


class PlanningStatus(StrEnum):
    """Status vocabulary reserved for the future planner result."""

    NOT_RUN = "not_run"
    FEASIBLE = "feasible"
    INFEASIBLE = "infeasible"
    INVALID_INPUT = "invalid_input"


@dataclass(frozen=True, slots=True)
class PlanningResult:
    """Result envelope without route-generation behavior in Stage 1."""

    status: PlanningStatus
    stops: tuple[str, ...] = ()
    collected_demand: float | None = None
    travel_distance: float | None = None
    travel_duration_seconds: float | None = None
    skipped_bins: tuple[str, ...] = ()
    diagnostics: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.status, PlanningStatus):
            raise ValueError("status must be a PlanningStatus")
        object.__setattr__(self, "stops", tuple(self.stops))
        object.__setattr__(self, "skipped_bins", tuple(self.skipped_bins))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))
