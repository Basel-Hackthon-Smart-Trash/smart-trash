"""Validated, solver-independent inputs assembled from classified data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .classification import ClassifiedSnapshot, FillClassification
from .contracts import TravelCostMatrix
from .models import CollectionDemand
from .validation import Diagnostic, DiagnosticSeverity


@dataclass(frozen=True, slots=True)
class RoutingCandidate:
    """A bin that has enough information to be considered by a future solver."""

    bin_id: str
    classification: FillClassification
    demand: CollectionDemand
    diagnostics: tuple[Diagnostic, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.classification, FillClassification):
            raise ValueError("classification must be a FillClassification")
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))


@dataclass(frozen=True, slots=True)
class PlanningInput:
    """The complete source-independent boundary consumed by a future solver."""

    planning_time: datetime
    depot_id: str
    candidates: tuple[RoutingCandidate, ...]
    truck_capacity: float
    demand_unit: str
    travel_costs: TravelCostMatrix

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidates", tuple(self.candidates))


@dataclass(frozen=True, slots=True)
class PlanningInputAssembly:
    """Assembly result: ``planning_input`` is absent only for blocking errors."""

    planning_input: PlanningInput | None
    diagnostics: tuple[Diagnostic, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))

    @property
    def valid(self) -> bool:
        return self.planning_input is not None and not any(
            item.severity == DiagnosticSeverity.ERROR for item in self.diagnostics
        )


def _diagnostic(code: str, message: str, *, bin_id: str | None = None) -> Diagnostic:
    return Diagnostic(code, message, DiagnosticSeverity.WARNING, bin_id)


def assemble_planning_input(
    classified: ClassifiedSnapshot,
    travel_costs: TravelCostMatrix,
) -> PlanningInputAssembly:
    """Align classified, demanded bins with an explicitly ordered cost matrix.

    Candidate order follows classified input order. The cost matrix is never
    reordered. Green classifications remain visible but are excluded below the
    collection threshold. Unknown classifications are excluded for sensor
    review, not relabeled or treated as evidence of a faulty sensor.
    """

    diagnostics = list(classified.validation.diagnostics)
    if not classified.validation.valid:
        return PlanningInputAssembly(None, tuple(diagnostics))

    node_ids = set(travel_costs.node_ids)
    config = classified.config
    if config.start_node_id not in node_ids:
        diagnostics.append(
            Diagnostic(
                "missing_depot_node",
                "travel-cost inputs do not contain the configured depot node",
                DiagnosticSeverity.ERROR,
            )
        )
    if config.end_node_id not in node_ids:
        diagnostics.append(
            Diagnostic(
                "missing_end_node",
                "travel-cost inputs do not contain the configured end node",
                DiagnosticSeverity.ERROR,
            )
        )

    demands = {demand.bin_id: demand for demand in classified.demands}
    candidates: list[RoutingCandidate] = []
    for entry in classified.entries:
        if entry.classification == FillClassification.UNKNOWN:
            diagnostics.append(
                _diagnostic(
                    "unknown_classification_sensor_check",
                    "unknown classification is excluded pending sensor review",
                    bin_id=entry.bin_id,
                )
            )
            continue
        if entry.classification == FillClassification.GREEN:
            diagnostics.append(
                _diagnostic(
                    "green_bin_excluded",
                    "green bin is below the collection threshold and is not routed",
                    bin_id=entry.bin_id,
                )
            )
            continue
        demand = demands.get(entry.bin_id)
        if demand is None:
            diagnostics.append(
                _diagnostic(
                    "missing_collection_demand",
                    "classified bin has no collection demand",
                    bin_id=entry.bin_id,
                )
            )
            continue
        if entry.bin_id not in node_ids:
            diagnostics.append(
                _diagnostic(
                    "missing_candidate_node",
                    "classified bin is absent from travel-cost node ordering",
                    bin_id=entry.bin_id,
                )
            )
            continue
        candidate_diagnostics: list[Diagnostic] = []
        if demand.amount > config.truck_capacity:
            candidate_diagnostics.append(
                _diagnostic(
                    "demand_exceeds_truck_capacity",
                    "candidate demand exceeds truck capacity; no split or extra trip is created",
                    bin_id=entry.bin_id,
                )
            )
            diagnostics.extend(candidate_diagnostics)
        candidates.append(
            RoutingCandidate(
                entry.bin_id, entry.classification, demand, tuple(candidate_diagnostics)
            )
        )

    if any(item.severity == DiagnosticSeverity.ERROR for item in diagnostics):
        return PlanningInputAssembly(None, tuple(diagnostics))
    return PlanningInputAssembly(
        PlanningInput(
            classified.planning_time,
            config.start_node_id,
            tuple(candidates),
            config.truck_capacity,
            config.demand_unit,
            travel_costs,
        ),
        tuple(diagnostics),
    )
