from smart_bin_routing.models import BinMetadata, CollectionDemand, PlanningSnapshot
from smart_bin_routing.validation import DiagnosticSeverity, validate_snapshot


def test_valid_snapshot_has_only_same_node_warning(synthetic_snapshot, synthetic_config):
    report = validate_snapshot(synthetic_snapshot, synthetic_config)

    assert report.valid
    assert [item.code for item in report.diagnostics] == ["same_start_end_node"]
    assert report.diagnostics[0].severity == DiagnosticSeverity.WARNING


def test_unknown_observation_and_demand_bins_are_errors(synthetic_config):
    snapshot = PlanningSnapshot(
        bins=(BinMetadata("known"),),
        observations=(),
        demands=(CollectionDemand("unknown", 1, "kg"),),
    )

    report = validate_snapshot(snapshot, synthetic_config)

    assert not report.valid
    assert "unknown_demand_bin" in {item.code for item in report.diagnostics}


def test_demand_unit_mismatch_is_an_error(synthetic_bin, synthetic_observation, synthetic_config):
    snapshot = PlanningSnapshot(
        bins=(synthetic_bin,),
        observations=(synthetic_observation,),
        demands=(CollectionDemand(synthetic_bin.bin_id, 1, "liters"),),
    )

    report = validate_snapshot(snapshot, synthetic_config)

    assert not report.valid
    assert any(item.code == "demand_unit_mismatch" for item in report.diagnostics)


def test_estimated_demand_requires_explicit_policy(synthetic_bin, synthetic_config):
    snapshot = PlanningSnapshot(
        bins=(synthetic_bin,),
        demands=(CollectionDemand(synthetic_bin.bin_id, 1, "kg", estimated=True),),
    )

    report = validate_snapshot(snapshot, synthetic_config)

    assert not report.valid
    assert any(item.code == "estimated_demand_not_allowed" for item in report.diagnostics)
