"""Integration: prediction output -> team routing package (smart_bin_routing) -> tours."""
from datetime import datetime

from smartbins import config, routing


def _bins():
    base = datetime(2026, 11, 1, 5, 30)
    out = []
    for i, (lat, lon, fill) in enumerate([(47.5596, 7.5886, 95), (47.5610, 7.5900, 92),
                                          (47.5580, 7.5850, 88), (47.5550, 7.5950, 91)]):
        out.append({"id": f"T-{i}", "lat": lat, "lon": lon, "fill_percent": fill,
                    "observed_at": base.isoformat(), "volume_l": 110, "osm_id": f"node/{i}"})
    return out


def test_every_selected_bin_is_routed_once():
    bins = _bins()
    routes, _ = routing.plan_routes(bins, bins, datetime(2026, 11, 1, 6, 0))
    stops = [s for r in routes for s in r["stops"]]
    assert sorted(stops) == sorted(b["id"] for b in bins)
    assert all(r["status"] == "feasible" and r["within_limits"] for r in routes)


def test_capacity_forces_more_trucks(monkeypatch):
    monkeypatch.setattr(config, "TRUCK_CAPACITY_L", 250)      # ~2 bins per truck
    bins = _bins()
    routes, _ = routing.plan_routes(bins, bins, datetime(2026, 11, 1, 6, 0))
    assert len(routes) >= 2
    assert all(r["load_l"] <= 250 for r in routes)


def test_nothing_to_empty_gives_no_routes():
    routes, _ = routing.plan_routes([], _bins(), datetime(2026, 11, 1, 6, 0))
    assert routes == []
