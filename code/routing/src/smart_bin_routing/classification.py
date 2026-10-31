"""Deterministic fill classification and contextual observation validation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from math import isfinite

from .models import FillObservation, PlanningConfig, PlanningSnapshot
from .validation import Diagnostic, DiagnosticSeverity, ValidationReport, validate_snapshot


class FillClassification(StrEnum):
    """Fill-level color, or unknown when the observation is unusable."""

    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class ClassifiedBin:
    """Classification and diagnostics for one known bin."""

    bin_id: str
    classification: FillClassification
    observation: FillObservation | None = None
    diagnostics: tuple[Diagnostic, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.classification, FillClassification):
            raise ValueError("classification must be a FillClassification")
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))


@dataclass(frozen=True, slots=True)
class ClassifiedSnapshot:
    """Immutable result of classifying a structurally valid snapshot."""

    planning_time: datetime
    entries: tuple[ClassifiedBin, ...]
    config: PlanningConfig
    validation: ValidationReport

    def __post_init__(self) -> None:
        if self.planning_time.tzinfo is None or self.planning_time.utcoffset() is None:
            raise ValueError("planning_time must be timezone-aware")
        object.__setattr__(self, "entries", tuple(self.entries))

    @property
    def valid(self) -> bool:
        """Whether the input passed Stage 1 structural validation."""

        return self.validation.valid


def classify_fill(fill_fraction: float, config: PlanningConfig) -> FillClassification:
    """Classify a validated normalized fill fraction using exact boundaries."""

    if isinstance(fill_fraction, bool) or not isinstance(fill_fraction, (int, float)):
        raise ValueError("fill_fraction must be a finite number")
    if not isfinite(fill_fraction) or not 0 <= fill_fraction <= 1:
        raise ValueError("fill_fraction must be between 0 and 1 inclusive")
    if fill_fraction < config.yellow_threshold:
        return FillClassification.GREEN
    if fill_fraction < config.red_threshold:
        return FillClassification.YELLOW
    return FillClassification.RED


def _context_diagnostic(code: str, message: str, bin_id: str) -> Diagnostic:
    return Diagnostic(code, message, DiagnosticSeverity.WARNING, bin_id)


def assess_observation(
    observation: FillObservation | None,
    *,
    planning_time: datetime,
    config: PlanningConfig,
    bin_id: str,
) -> tuple[FillClassification, tuple[Diagnostic, ...]]:
    """Assess freshness and classify one observation without reading the clock."""

    if observation is None:
        return (
            FillClassification.UNKNOWN,
            (_context_diagnostic("missing_observation", "no observation was supplied", bin_id),),
        )

    age_seconds = (planning_time - observation.observed_at).total_seconds()
    if age_seconds > config.observation_max_age_seconds:
        return (
            FillClassification.UNKNOWN,
            (
                _context_diagnostic(
                    "stale_observation",
                    "observation is older than the configured maximum age",
                    bin_id,
                ),
            ),
        )
    if age_seconds < -config.allowed_future_skew_seconds:
        return (
            FillClassification.UNKNOWN,
            (
                _context_diagnostic(
                    "future_observation",
                    "observation is later than the allowed future skew",
                    bin_id,
                ),
            ),
        )
    return classify_fill(observation.fill_fraction, config), ()


def classify_snapshot(
    snapshot: PlanningSnapshot,
    config: PlanningConfig,
    planning_time: datetime,
) -> ClassifiedSnapshot:
    """Validate and classify a planning snapshot at an explicit instant.

    Structural errors are returned in ``validation`` and produce no entries;
    contextual observation problems remain visible as unknown per-bin entries.
    """

    if planning_time.tzinfo is None or planning_time.utcoffset() is None:
        raise ValueError("planning_time must be timezone-aware")

    validation = validate_snapshot(snapshot, config)
    if not validation.valid:
        return ClassifiedSnapshot(planning_time, (), config, validation)

    observations_by_bin = {observation.bin_id: observation for observation in snapshot.observations}
    entries = []
    for bin_metadata in snapshot.bins:
        observation = observations_by_bin.get(bin_metadata.bin_id)
        classification, diagnostics = assess_observation(
            observation,
            planning_time=planning_time,
            config=config,
            bin_id=bin_metadata.bin_id,
        )
        entries.append(
            ClassifiedBin(
                bin_id=bin_metadata.bin_id,
                classification=classification,
                observation=observation,
                diagnostics=diagnostics,
            )
        )
    return ClassifiedSnapshot(planning_time, tuple(entries), config, validation)
