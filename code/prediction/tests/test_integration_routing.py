"""Integration: prediction output -> team routing package (smart_bin_routing) -> tours."""

from datetime import datetime

from smartbins import config, routing


def _bins():
    base = datetime(2026, 11, 1, 5, 30)
    out = []
    for i, (lat, lon, fill) in enumerate(
        [
            (47.5596, 7.5886, 95),
            (47.5610, 7.5900, 92),
            (47.5580, 7.5850, 88),
            (47.5550, 7.5950, 91),
        ]
    ):
        out.append(
            {
                "id": f"T-{i}",
                "lat": lat,
                "lon": lon,
                "fill_percent": fill,
                "observed_at": base.isoformat(),
                "volume_l": 110,
                "osm_id": f"node/{i}",
            }
        )
    return out


def test_every_selected_bin_is_routed_once(monkeypatch):
    monkeypatch.setattr(routing, "GRAPH_DIR", "/nonexistent")
    bins = _bins()
    routes, _ = routing.plan_routes(bins, bins, datetime(2026, 11, 1, 6, 0))
    stops = [s for r in routes for s in r["stops"]]
    assert sorted(stops) == sorted(b["id"] for b in bins)
    assert all(r["status"] == "feasible" and r["within_limits"] for r in routes)
    assert all(
        r["driving_duration_h"] == round(r["distance_km"] / config.AVG_SPEED_KMH, 2)
        for r in routes
    )
    assert all(
        r["service_duration_h"] == round(len(r["stops"]) * 2 / 60, 2) for r in routes
    )


def test_forecast_selected_low_fill_bin_is_routed(monkeypatch):
    monkeypatch.setattr(routing, "GRAPH_DIR", "/nonexistent")
    bins = _bins()[:1]
    bins[0]["fill_percent"] = 60
    routes, _ = routing.plan_routes(bins, bins, datetime(2026, 11, 1, 6, 0))

    assert [stop for route in routes for stop in route["stops"]] == ["T-0"]
    assert routes[0]["status"] == "feasible"


def test_green_bin_is_excluded_from_route(monkeypatch):
    monkeypatch.setattr(routing, "GRAPH_DIR", "/nonexistent")
    bins = _bins()[:1]
    bins[0]["fill_percent"] = 54
    routes, _ = routing.plan_routes(bins, bins, datetime(2026, 11, 1, 6, 0))

    assert routes[0]["stops"] == []
    assert routes[0]["status"] == "no_routing_ready_candidates"


def test_green_flagged_bin_never_enters_route_partition(monkeypatch):
    monkeypatch.setattr(routing, "GRAPH_DIR", "/nonexistent")
    bins = _bins()[:1]
    bins[0]["fill_percent"] = 70
    bins[0]["fill_band"] = "green"

    routes, _ = routing.plan_routes(bins, bins, datetime(2026, 11, 1, 6, 0))

    assert routes == []


def test_capacity_forces_more_trucks(monkeypatch):
    monkeypatch.setattr(routing, "GRAPH_DIR", "/nonexistent")
    monkeypatch.setattr(config, "TRUCK_CAPACITY_L", 250)  # ~2 bins per truck
    bins = _bins()
    routes, _ = routing.plan_routes(bins, bins, datetime(2026, 11, 1, 6, 0))
    assert len(routes) >= 2
    assert all(r["load_l"] <= 250 for r in routes)


def test_nothing_to_empty_gives_no_routes(monkeypatch):
    monkeypatch.setattr(routing, "GRAPH_DIR", "/nonexistent")
    routes, _ = routing.plan_routes([], _bins(), datetime(2026, 11, 1, 6, 0))
    assert routes == []
