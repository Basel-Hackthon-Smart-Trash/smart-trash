import json
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse

import pytest

from smart_bin_routing.adapters.depot_geocoding import (
    DepotAddress,
    GeocodingError,
    NominatimClient,
    accept_candidate,
    load_depot_location,
    save_depot_location,
)

ADDRESS = DepotAddress(
    "stadtreinigung-basel",
    "Stadtreinigung (SR)",
    "Brüssel-Strasse",
    "22",
    "4053",
    "Basel",
)
NOW = datetime(2026, 10, 31, 13, 0, tzinfo=UTC)


def payload(**overrides):
    result = {
        "place_id": 123,
        "osm_type": "way",
        "osm_id": 456,
        "lat": "47.545",
        "lon": "7.59",
        "display_name": "Brüssel-Strasse 22, 4053 Basel, Switzerland",
        "licence": "Data © OpenStreetMap contributors, ODbL",
        "address": {
            "house_number": "22",
            "road": "Brüssel-Strasse",
            "postcode": "4053",
            "city": "Basel",
            "country_code": "ch",
        },
    }
    result.update(overrides)
    return result


def client(response, *, clock=None, sleeper=None):
    def transport(url, *, timeout, user_agent):
        return response

    return NominatimClient(
        user_agent="smart-trash-routing/0.1 (team@example.invalid)",
        transport=transport,
        clock=clock or (lambda: 10.0),
        sleeper=sleeper or (lambda _seconds: None),
    )


def test_structured_request_and_exact_candidate_acceptance():
    requests = []

    def transport(url, *, timeout, user_agent):
        requests.append((url, user_agent))
        return 200, json.dumps([payload()]).encode()

    candidates = NominatimClient(
        user_agent="smart-trash-routing/0.1 (team@example.invalid)", transport=transport
    ).search(ADDRESS)
    query = parse_qs(urlparse(requests[0][0]).query)
    assert "q" not in query
    assert query["street"] == ["22 Brüssel-Strasse"]
    assert query["countrycodes"] == ["ch"]
    accepted = accept_candidate(candidates, ADDRESS, 0, fetched_at=NOW, accepted_at=NOW)
    assert accepted.location.longitude == 7.59
    assert accepted.vehicle_access_confirmed is False


def test_missing_house_number_is_not_accepted():
    candidates = client(
        (200, json.dumps([payload(address={"road": "Brüssel-Strasse"})]).encode())
    ).search(ADDRESS)
    assert "missing_house_number" in candidates[0].match_diagnostics
    with pytest.raises(GeocodingError, match="exactly match"):
        accept_candidate(candidates, ADDRESS, 0, fetched_at=NOW)


def test_unicode_and_street_normalisation():
    candidate = payload(
        address={
            "house_number": "22",
            "road": "Brüssel-Strasse",
            "postcode": "4053",
            "city": "Basel",
            "country_code": "CH",
        }
    )
    result = client((200, json.dumps([candidate]).encode())).search(ADDRESS)
    assert result[0].match_diagnostics == ()


@pytest.mark.parametrize(
    "body",
    [
        b"not-json",
        json.dumps({"unexpected": True}).encode(),
        json.dumps([payload(lat=True)]).encode(),
        json.dumps([payload(lat="nan")]).encode(),
        json.dumps([payload(lat="91")]).encode(),
    ],
)
def test_malformed_responses_fail(body):
    with pytest.raises(GeocodingError):
        client((200, body)).search(ADDRESS)


@pytest.mark.parametrize("status", [429, 500])
def test_http_errors_fail_without_exposing_response(status):
    with pytest.raises(GeocodingError, match="Nominatim"):
        client((status, b"private response details")).search(ADDRESS)


@pytest.mark.parametrize("failure", [TimeoutError(), OSError("network unavailable")])
def test_transport_failures_are_typed(failure):
    def transport(_url, **_kwargs):
        raise failure

    with pytest.raises(GeocodingError, match="request failed"):
        NominatimClient(
            user_agent="smart-trash-routing/0.1 (team@example.invalid)",
            transport=transport,
        ).search(ADDRESS)


def test_rate_limit_pacing_is_enforced():
    now = iter([10.0, 10.0, 10.0])
    sleeps = []
    current = NominatimClient(
        user_agent="smart-trash-routing/0.1 (team@example.invalid)",
        transport=lambda _url, **_kwargs: (200, b"[]"),
        clock=lambda: next(now),
        sleeper=sleeps.append,
    )
    current.search(ADDRESS)
    current.search(ADDRESS)
    assert sleeps == [1.0]


def test_save_load_round_trip_and_overwrite_protection(tmp_path):
    candidates = client((200, json.dumps([payload()]).encode())).search(ADDRESS)
    location = accept_candidate(candidates, ADDRESS, 0, fetched_at=NOW, accepted_at=NOW)
    path = tmp_path / "depot.json"
    save_depot_location(location, path)
    loaded = load_depot_location(path)
    assert loaded == location
    with pytest.raises(GeocodingError, match="overwrite"):
        save_depot_location(location, path)


def test_unaccepted_or_invalid_cache_fails(tmp_path):
    path = tmp_path / "depot.json"
    path.write_text(json.dumps({"acceptance_status": "review"}), encoding="utf-8")
    with pytest.raises(GeocodingError, match="accepted"):
        load_depot_location(path)

    path.write_text(
        json.dumps(
            {
                "acceptance_status": "accepted",
                "schema_version": 1,
                "depot": ADDRESS.__dict__
                if hasattr(ADDRESS, "__dict__")
                else {field: getattr(ADDRESS, field) for field in ADDRESS.__dataclass_fields__},
                "coordinates": {"longitude": True, "latitude": 47.5, "crs": "WGS84"},
                "provider": "Nominatim / OpenStreetMap",
                "display_name": "address",
                "provider_address": {},
                "fetched_at": NOW.isoformat(),
                "accepted_at": NOW.isoformat(),
                "attribution": "OpenStreetMap",
                "vehicle_access_confirmed": False,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(GeocodingError, match="finite"):
        load_depot_location(path)


def test_no_network_on_import_or_offline_load(monkeypatch, tmp_path):
    def fail(*_args, **_kwargs):
        raise AssertionError("network must not be used")

    monkeypatch.setattr("urllib.request.urlopen", fail)
    with pytest.raises(GeocodingError, match="does not exist"):
        load_depot_location(tmp_path / "missing.json")
