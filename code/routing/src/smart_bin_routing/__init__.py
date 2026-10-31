"""Contracts, validation, and fill classification for smart-bin routing."""

from .classification import (
    ClassifiedBin,
    ClassifiedSnapshot,
    FillClassification,
    assess_observation,
    classify_fill,
    classify_snapshot,
)
from .models import (
    BinMetadata,
    CollectionDemand,
    DemandPolicy,
    FillObservation,
    GeoLocation,
    PlanningConfig,
    PlanningDiagnostic,
    PlanningResult,
    PlanningSnapshot,
    PlanningStatus,
)
from .planning import (
    PlanningInput,
    PlanningInputAssembly,
    RoutingCandidate,
    assemble_planning_input,
)
from .solver import CostMetric, SolverConfig, optimize_route

__all__ = [
    "BinMetadata",
    "ClassifiedBin",
    "ClassifiedSnapshot",
    "CollectionDemand",
    "DemandPolicy",
    "FillObservation",
    "FillClassification",
    "GeoLocation",
    "PlanningConfig",
    "PlanningDiagnostic",
    "PlanningResult",
    "PlanningSnapshot",
    "PlanningStatus",
    "PlanningInput",
    "PlanningInputAssembly",
    "RoutingCandidate",
    "assemble_planning_input",
    "assess_observation",
    "classify_fill",
    "classify_snapshot",
    "CostMetric",
    "SolverConfig",
    "optimize_route",
]
