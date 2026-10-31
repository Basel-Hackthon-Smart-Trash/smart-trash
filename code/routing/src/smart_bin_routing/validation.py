"""Structural validation for normalized planning inputs."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .models import DemandPolicy, PlanningConfig, PlanningSnapshot


class DiagnosticSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True, slots=True)
class Diagnostic:
    code: str
    message: str
    severity: DiagnosticSeverity
    bin_id: str | None = None


@dataclass(frozen=True, slots=True)
class ValidationReport:
    diagnostics: tuple[Diagnostic, ...]

    @property
    def valid(self) -> bool:
        return not any(item.severity == DiagnosticSeverity.ERROR for item in self.diagnostics)


def validate_snapshot(snapshot: PlanningSnapshot, config: PlanningConfig) -> ValidationReport:
    """Check cross-object references without classifying or planning.

    Model constructors enforce local field shape. This function checks that
    normalized records refer to known bins and that demand units match the
    configured planning unit.
    """

    diagnostics: list[Diagnostic] = []
    bin_ids = [item.bin_id for item in snapshot.bins]
    known_bins = set(bin_ids)

    for bin_id in sorted({item for item in bin_ids if bin_ids.count(item) > 1}):
        diagnostics.append(
            Diagnostic(
                "duplicate_bin_id",
                "bin_id occurs more than once",
                DiagnosticSeverity.ERROR,
                bin_id,
            )
        )

    for observation in snapshot.observations:
        if observation.bin_id not in known_bins:
            diagnostics.append(
                Diagnostic(
                    "unknown_observation_bin",
                    "observation refers to a bin absent from metadata",
                    DiagnosticSeverity.ERROR,
                    observation.bin_id,
                )
            )

    for demand in snapshot.demands:
        if demand.bin_id not in known_bins:
            diagnostics.append(
                Diagnostic(
                    "unknown_demand_bin",
                    "demand refers to a bin absent from metadata",
                    DiagnosticSeverity.ERROR,
                    demand.bin_id,
                )
            )
        if demand.unit != config.demand_unit:
            diagnostics.append(
                Diagnostic(
                    "demand_unit_mismatch",
                    (
                        f"demand unit {demand.unit!r} does not match "
                        f"configured unit {config.demand_unit!r}"
                    ),
                    DiagnosticSeverity.ERROR,
                    demand.bin_id,
                )
            )
        if demand.estimated and config.demand_policy == DemandPolicy.EXPLICIT_ONLY:
            diagnostics.append(
                Diagnostic(
                    "estimated_demand_not_allowed",
                    "estimated demand requires an explicitly enabled demand policy",
                    DiagnosticSeverity.ERROR,
                    demand.bin_id,
                )
            )

    if config.start_node_id == config.end_node_id:
        diagnostics.append(
            Diagnostic(
                "same_start_end_node",
                "start and end use the same modeled node",
                DiagnosticSeverity.WARNING,
            )
        )

    return ValidationReport(tuple(diagnostics))
