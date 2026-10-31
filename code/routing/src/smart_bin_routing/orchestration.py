"""Application-level composition of the routing stages.

This module accepts an already coherent planning snapshot. Transport, snapshot
storage, and planning triggers remain responsibilities of the caller.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from .classification import ClassifiedSnapshot, FillClassification, classify_snapshot
from .contracts import TravelCostMatrix
from .models import (
    PlanningConfig,
    PlanningDiagnostic,
    PlanningResult,
    PlanningSnapshot,
    PlanningStatus,
)
from .planning import PlanningInputAssembly, assemble_planning_input
from .solver import SolverBackend, SolverConfig, optimize_route


class CollectionPlanStatus(StrEnum):
    """Outcome of the complete application workflow."""

    INVALID_REQUEST = "invalid_request"
    NO_ACTIONABLE_BINS = "no_actionable_bins"
    NO_ROUTING_READY_CANDIDATES = "no_routing_ready_candidates"
    FEASIBLE = "feasible"
    INFEASIBLE = "infeasible"
    SEARCH_EXHAUSTED = "search_exhausted"
    TIME_LIMIT = "time_limit"
    DEPENDENCY_FAILURE = "dependency_failure"
    SOLVER_ERROR = "solver_error"


@dataclass(frozen=True, slots=True)
class CollectionPlanRequest:
    """All inputs for one explicit planning attempt.

    ``snapshot`` must represent one coherent observation state. This package
    does not accumulate observations or decide when a snapshot is complete.
    """

    snapshot: PlanningSnapshot
    config: PlanningConfig
    planning_time: datetime
    travel_costs: TravelCostMatrix
    solver_config: SolverConfig | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.snapshot, PlanningSnapshot):
            raise ValueError("snapshot must be a PlanningSnapshot")
        if not isinstance(self.config, PlanningConfig):
            raise ValueError("config must be a PlanningConfig")
        if not isinstance(self.planning_time, datetime):
            raise ValueError("planning_time must be a datetime")
        if self.planning_time.tzinfo is None or self.planning_time.utcoffset() is None:
            raise ValueError("planning_time must be timezone-aware")
        if not isinstance(self.travel_costs, TravelCostMatrix):
            raise ValueError("travel_costs must be a TravelCostMatrix")


@dataclass(frozen=True, slots=True)
class BinPlanAssessment:
    """Classification and route-readiness information for one bin."""

    bin_id: str
    classification: FillClassification
    routing_ready: bool
    included_in_route: bool
    diagnostics: tuple[PlanningDiagnostic, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.classification, FillClassification):
            raise ValueError("classification must be a FillClassification")
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))


@dataclass(frozen=True, slots=True)
class CollectionPlanResult:
    """Structured result combining preprocessing and solver outcomes."""

    status: CollectionPlanStatus
    bins: tuple[BinPlanAssessment, ...] = ()
    solver_result: PlanningResult | None = None
    diagnostics: tuple[PlanningDiagnostic, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.status, CollectionPlanStatus):
            raise ValueError("status must be a CollectionPlanStatus")
        object.__setattr__(self, "bins", tuple(self.bins))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))

    @property
    def route_nodes(self) -> tuple[str, ...]:
        """Return the solver route, or no route when planning did not run."""

        return self.solver_result.route_nodes if self.solver_result else ()

    @property
    def stops(self) -> tuple[str, ...]:
        """Return collected bin IDs in route order."""

        return self.solver_result.stops if self.solver_result else ()


def _planning_diagnostic(item) -> PlanningDiagnostic:
    return PlanningDiagnostic(
        item.code,
        item.message,
        item.severity.value,
        item.bin_id,
    )


def _assembly_diagnostics(assembly: PlanningInputAssembly) -> tuple[PlanningDiagnostic, ...]:
    return tuple(_planning_diagnostic(item) for item in assembly.diagnostics)


def _status_for_solver(result: PlanningResult) -> CollectionPlanStatus:
    return {
        PlanningStatus.FEASIBLE: CollectionPlanStatus.FEASIBLE,
        PlanningStatus.INFEASIBLE: CollectionPlanStatus.INFEASIBLE,
        PlanningStatus.INVALID_INPUT: CollectionPlanStatus.INVALID_REQUEST,
        PlanningStatus.SEARCH_EXHAUSTED: CollectionPlanStatus.SEARCH_EXHAUSTED,
        PlanningStatus.TIME_LIMIT: CollectionPlanStatus.TIME_LIMIT,
        PlanningStatus.SOLVER_ERROR: CollectionPlanStatus.SOLVER_ERROR,
    }.get(result.status, CollectionPlanStatus.SOLVER_ERROR)


def _bin_assessments(
    classified: ClassifiedSnapshot,
    assembly: PlanningInputAssembly,
    solver_result: PlanningResult | None,
) -> tuple[BinPlanAssessment, ...]:
    candidates = assembly.planning_input.candidates if assembly.planning_input else ()
    ready_ids = {candidate.bin_id for candidate in candidates}
    included_ids = set(solver_result.stops) if solver_result else set()
    diagnostics_by_bin: dict[str, list[PlanningDiagnostic]] = {
        entry.bin_id: [_planning_diagnostic(item) for item in entry.diagnostics]
        for entry in classified.entries
    }
    for item in assembly.diagnostics:
        if item.bin_id is not None:
            diagnostics_by_bin.setdefault(item.bin_id, []).append(_planning_diagnostic(item))
    return tuple(
        BinPlanAssessment(
            entry.bin_id,
            entry.classification,
            entry.bin_id in ready_ids,
            entry.bin_id in included_ids,
            tuple(diagnostics_by_bin.get(entry.bin_id, ())),
        )
        for entry in classified.entries
    )


def _solver_diagnostics(result: PlanningResult) -> tuple[PlanningDiagnostic, ...]:
    details = list(result.diagnostic_details)
    known_codes = {item.code for item in details}
    details.extend(
        PlanningDiagnostic(code, code, "error")
        for code in result.diagnostics
        if code not in known_codes
    )
    return tuple(details)


def plan_collection(
    request: CollectionPlanRequest,
    *,
    backend: SolverBackend | None = None,
) -> CollectionPlanResult:
    """Run validation, classification, assembly, and route optimization.

    The optimizer is not called when validation blocks assembly or when no
    routing-ready candidates remain. Unexpected programming errors are allowed
    to propagate; solver adapter failures use the existing structured result.
    """

    classified = classify_snapshot(request.snapshot, request.config, request.planning_time)
    if not classified.valid:
        diagnostics = tuple(
            _planning_diagnostic(item) for item in classified.validation.diagnostics
        )
        return CollectionPlanResult(
            CollectionPlanStatus.INVALID_REQUEST,
            diagnostics=diagnostics,
        )

    assembly = assemble_planning_input(classified, request.travel_costs)
    diagnostics = _assembly_diagnostics(assembly)
    if not assembly.valid:
        return CollectionPlanResult(
            CollectionPlanStatus.INVALID_REQUEST,
            bins=_bin_assessments(classified, assembly, None),
            diagnostics=diagnostics,
        )

    if not classified.entries:
        return CollectionPlanResult(
            CollectionPlanStatus.NO_ACTIONABLE_BINS,
            diagnostics=diagnostics,
        )
    if not assembly.planning_input.candidates:
        return CollectionPlanResult(
            CollectionPlanStatus.NO_ROUTING_READY_CANDIDATES,
            bins=_bin_assessments(classified, assembly, None),
            diagnostics=diagnostics,
        )

    solver_result = optimize_route(
        assembly.planning_input,
        request.solver_config,
        backend=backend,
    )
    return CollectionPlanResult(
        _status_for_solver(solver_result),
        bins=_bin_assessments(classified, assembly, solver_result),
        solver_result=solver_result,
        diagnostics=diagnostics + _solver_diagnostics(solver_result),
    )
