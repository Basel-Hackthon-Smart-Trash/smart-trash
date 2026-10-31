"""Contracts, validation, and fill classification for smart-bin routing."""

from .adapters.bin_geojson import BinGeoJSONError, load_bin_geojson
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
from .orchestration import (
    BinPlanAssessment,
    CollectionPlanRequest,
    CollectionPlanResult,
    CollectionPlanStatus,
    plan_collection,
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
    "BinGeoJSONError",
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
    "BinPlanAssessment",
    "CollectionPlanRequest",
    "CollectionPlanResult",
    "CollectionPlanStatus",
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
    "plan_collection",
    "load_bin_geojson",
]
