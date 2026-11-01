import importlib.util
from pathlib import Path

from smart_bin_routing import GeoLocation

_DEMO_PATH = Path(__file__).parents[1] / "examples" / "real_bin_subset_demo.py"
_SPEC = importlib.util.spec_from_file_location("real_bin_subset_demo", _DEMO_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_DEMO = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_DEMO)


def test_demo_costs_follow_coordinates_not_node_id_order():
    costs = _DEMO._synthetic_costs(
        {
            "depot": GeoLocation(7.60, 47.53),
            "near": GeoLocation(7.601, 47.53),
            "far": GeoLocation(7.62, 47.53),
        }
    )

    assert costs.node_ids == ("depot", "near", "far")
    assert costs.distances[0][1] < costs.distances[0][2]
    assert costs.distances[1][2] == costs.distances[2][1]
