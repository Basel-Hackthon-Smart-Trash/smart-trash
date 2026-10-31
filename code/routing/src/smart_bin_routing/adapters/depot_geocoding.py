"""Explicit, one-shot depot geocoding with an offline accepted-record boundary."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
import time
import unicodedata
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from math import isfinite
from pathlib import Path
from typing import Protocol
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from ..models import GeoLocation

SCHEMA_VERSION = 1
DEFAULT_ENDPOINT = "https://nominatim.openstreetmap.org/search"
DEFAULT_DEPOT = "stadtreinigung-basel"


class GeocodingError(ValueError):
    """A geocoding request, candidate, or persisted record is invalid."""


@dataclass(frozen=True, slots=True)
class DepotAddress:
    depot_id: str
    name: str
    street: str
    house_number: str
    postcode: str
    city: str
    country: str = "Switzerland"
    country_code: str = "CH"

    def __post_init__(self) -> None:
        for field_name in (
            "depot_id",
            "name",
            "street",
            "house_number",
            "postcode",
            "city",
            "country",
            "country_code",
        ):
            if (
                not isinstance(getattr(self, field_name), str)
                or not getattr(self, field_name).strip()
            ):
                raise GeocodingError(f"{field_name} must be a non-empty string")
        if self.country_code.upper() != "CH":
            raise GeocodingError("country_code must be CH")


@dataclass(frozen=True, slots=True)
class GeocodingCandidate:
    display_name: str
    location: GeoLocation
    address: tuple[tuple[str, str], ...]
    osm_type: str | None = None
    osm_id: str | None = None
    place_id: str | None = None
    category: str | None = None
    result_type: str | None = None
    licence: str | None = None
    match_diagnostics: tuple[str, ...] = ()
    raw: tuple[tuple[str, str], ...] = ()

    def address_value(self, key: str) -> str | None:
        return dict(self.address).get(key)


@dataclass(frozen=True, slots=True)
class AcceptedDepotLocation:
    schema_version: int
    depot: DepotAddress
    provider: str
    display_name: str
    location: GeoLocation
    provider_address: tuple[tuple[str, str], ...]
    osm_type: str | None
    osm_id: str | None
    place_id: str | None
    fetched_at: datetime
    accepted_at: datetime
    attribution: str
    vehicle_access_confirmed: bool = False

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise GeocodingError("unsupported depot record schema version")
        if self.provider != "Nominatim / OpenStreetMap":
            raise GeocodingError("unsupported depot record provider")
        for value, field_name in (
            (self.fetched_at, "fetched_at"),
            (self.accepted_at, "accepted_at"),
        ):
            if value.tzinfo is None or value.utcoffset() is None:
                raise GeocodingError(f"{field_name} must be timezone-aware")
        if self.vehicle_access_confirmed:
            raise GeocodingError("vehicle access must remain unconfirmed")


class HttpTransport(Protocol):
    def __call__(self, url: str, *, timeout: float, user_agent: str) -> tuple[int, bytes]:
        """Return an HTTP status and response body."""


def _urllib_transport(url: str, *, timeout: float, user_agent: str) -> tuple[int, bytes]:
    request = Request(url, headers={"User-Agent": user_agent, "Accept": "application/json"})
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - configured endpoint
            return response.status, response.read()
    except Exception as error:
        raise GeocodingError(f"Nominatim request failed: {type(error).__name__}") from error


class NominatimClient:
    """One-shot Nominatim client; no requests happen during construction/import."""

    def __init__(
        self,
        *,
        user_agent: str,
        contact: str | None = None,
        endpoint: str = DEFAULT_ENDPOINT,
        timeout: float = 10.0,
        min_interval_seconds: float = 1.0,
        transport: HttpTransport = _urllib_transport,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        identifier = user_agent.strip() if isinstance(user_agent, str) else ""
        if not identifier or identifier.lower() in {"python-urllib", "python", "default"}:
            raise GeocodingError("a descriptive User-Agent is required")
        if timeout <= 0 or not isfinite(timeout):
            raise GeocodingError("timeout must be finite and positive")
        if min_interval_seconds < 0 or not isfinite(min_interval_seconds):
            raise GeocodingError("min_interval_seconds must be finite and non-negative")
        self.user_agent = identifier + (
            f" ({contact.strip()})" if contact and contact.strip() else ""
        )
        self.endpoint = endpoint
        self.timeout = timeout
        self.min_interval_seconds = min_interval_seconds
        self._transport = transport
        self._clock = clock
        self._sleeper = sleeper
        self._last_request: float | None = None

    def search(self, address: DepotAddress) -> tuple[GeocodingCandidate, ...]:
        if self._last_request is not None:
            remaining = self.min_interval_seconds - (self._clock() - self._last_request)
            if remaining > 0:
                self._sleeper(remaining)
        query = urlencode(
            {
                "street": f"{address.house_number} {address.street}",
                "city": address.city,
                "postalcode": address.postcode,
                "country": address.country,
                "countrycodes": address.country_code.lower(),
                "format": "jsonv2",
                "addressdetails": "1",
                "limit": "10",
            }
        )
        self._last_request = self._clock()
        try:
            status, body = self._transport(
                f"{self.endpoint}?{query}", timeout=self.timeout, user_agent=self.user_agent
            )
        except GeocodingError:
            raise
        except Exception as error:
            raise GeocodingError(f"Nominatim request failed: {type(error).__name__}") from error
        if status == 429:
            raise GeocodingError("Nominatim rate limit response")
        if status < 200 or status >= 300:
            raise GeocodingError(f"Nominatim returned HTTP status {status}")
        try:
            payload = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise GeocodingError("Nominatim returned invalid JSON") from error
        if not isinstance(payload, list):
            raise GeocodingError("Nominatim response must be a candidate list")
        return tuple(_parse_candidate(item, address) for item in payload)


def _text(value: object, field_name: str, *, required: bool = False) -> str | None:
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value.strip():
        raise GeocodingError(f"candidate {field_name} must be a non-empty string")
    return value.strip()


def _parse_candidate(payload: object, requested: DepotAddress) -> GeocodingCandidate:
    if not isinstance(payload, Mapping):
        raise GeocodingError("candidate must be an object")
    latitude = _coordinate(payload.get("lat"), "latitude")
    longitude = _coordinate(payload.get("lon"), "longitude")
    raw_address = payload.get("address", {})
    if not isinstance(raw_address, Mapping):
        raise GeocodingError("candidate address must be an object")
    address = tuple(
        (str(key), _text(value, str(key), required=True) or "")
        for key, value in raw_address.items()
    )
    candidate = GeocodingCandidate(
        display_name=_text(payload.get("display_name"), "display_name", required=True) or "",
        location=GeoLocation(longitude=longitude, latitude=latitude),
        address=address,
        osm_type=_text(payload.get("osm_type"), "osm_type"),
        osm_id=_string_identifier(payload.get("osm_id"), "osm_id"),
        place_id=_string_identifier(payload.get("place_id"), "place_id"),
        category=_text(payload.get("category"), "category"),
        result_type=_text(payload.get("type"), "type"),
        licence=_text(payload.get("licence"), "licence"),
        raw=tuple(
            (str(key), json.dumps(value, sort_keys=True))
            for key, value in payload.items()
            if key != "address"
        ),
    )
    diagnostics = _match_diagnostics(candidate, requested)
    return GeocodingCandidate(
        **{
            field: getattr(candidate, field)
            for field in candidate.__dataclass_fields__
            if field != "match_diagnostics"
        },
        match_diagnostics=diagnostics,
    )


def _string_identifier(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise GeocodingError(f"candidate {field_name} must be a string or integer")
    return str(value)


def _coordinate(value: object, field_name: str) -> float:
    if isinstance(value, bool):
        raise GeocodingError(f"candidate {field_name} must be finite")
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise GeocodingError(f"candidate {field_name} must be finite") from error
    if not isfinite(number):
        raise GeocodingError(f"candidate {field_name} must be finite")
    if field_name == "latitude" and not -90 <= number <= 90:
        raise GeocodingError("candidate latitude is out of range")
    if field_name == "longitude" and not -180 <= number <= 180:
        raise GeocodingError("candidate longitude is out of range")
    return number


def _normalise(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold().replace("ß", "ss")
    return " ".join("".join(char if char.isalnum() else " " for char in value).split())


def _match_diagnostics(candidate: GeocodingCandidate, requested: DepotAddress) -> tuple[str, ...]:
    actual = candidate.address_value
    diagnostics = []
    comparisons = (
        ("house_number", requested.house_number, actual("house_number")),
        ("road", requested.street, actual("road")),
        ("postcode", requested.postcode, actual("postcode")),
        ("country_code", requested.country_code, actual("country_code")),
    )
    for field_name, expected, found in comparisons:
        if found is None:
            diagnostics.append(f"missing_{field_name}")
        elif _normalise(found) != _normalise(expected):
            diagnostics.append(f"mismatched_{field_name}")
    city = actual("city") or actual("town") or actual("village")
    if city is None:
        diagnostics.append("missing_city")
    elif _normalise(city) != _normalise(requested.city):
        diagnostics.append("mismatched_city")
    return tuple(diagnostics)


def search_depot_candidates(
    address: DepotAddress, client: NominatimClient
) -> tuple[GeocodingCandidate, ...]:
    """Perform the deliberate online search; candidates are never auto-accepted."""

    return client.search(address)


def accept_candidate(
    candidates: tuple[GeocodingCandidate, ...],
    address: DepotAddress,
    index: int,
    *,
    fetched_at: datetime,
    accepted_at: datetime | None = None,
) -> AcceptedDepotLocation:
    if index < 0 or index >= len(candidates):
        raise GeocodingError("candidate index is out of range")
    candidate = candidates[index]
    if candidate.match_diagnostics:
        raise GeocodingError("candidate does not exactly match the requested address")
    if fetched_at.tzinfo is None or fetched_at.utcoffset() is None:
        raise GeocodingError("fetched_at must be timezone-aware")
    accepted_at = accepted_at or datetime.now(UTC)
    return AcceptedDepotLocation(
        SCHEMA_VERSION,
        address,
        "Nominatim / OpenStreetMap",
        candidate.display_name,
        candidate.location,
        candidate.address,
        candidate.osm_type,
        candidate.osm_id,
        candidate.place_id,
        fetched_at,
        accepted_at,
        candidate.licence or "Data © OpenStreetMap contributors, ODbL",
    )


def _record(location: AcceptedDepotLocation) -> dict[str, object]:
    return {
        "schema_version": location.schema_version,
        "depot": location.depot.__dict__
        if hasattr(location.depot, "__dict__")
        else {
            field: getattr(location.depot, field) for field in location.depot.__dataclass_fields__
        },
        "provider": location.provider,
        "display_name": location.display_name,
        "coordinates": {
            "latitude": location.location.latitude,
            "longitude": location.location.longitude,
            "crs": "WGS84",
        },
        "provider_address": dict(location.provider_address),
        "osm_type": location.osm_type,
        "osm_id": location.osm_id,
        "place_id": location.place_id,
        "fetched_at": location.fetched_at.isoformat(),
        "accepted_at": location.accepted_at.isoformat(),
        "attribution": location.attribution,
        "vehicle_access_confirmed": location.vehicle_access_confirmed,
        "acceptance_status": "accepted",
    }


def save_depot_location(
    location: AcceptedDepotLocation, path: Path, *, overwrite: bool = False
) -> None:
    """Atomically save an accepted record; refuse accidental replacement."""

    path = Path(path)
    if path.exists() and not overwrite:
        raise GeocodingError(f"refusing to overwrite existing depot record: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent, text=True)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as output:
            json.dump(_record(location), output, indent=2, ensure_ascii=False)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    except Exception:
        Path(temporary).unlink(missing_ok=True)
        raise


def load_depot_location(path: Path) -> AcceptedDepotLocation:
    """Load and fully validate an accepted record without network access."""

    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise GeocodingError(f"depot record does not exist: {path}") from error
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise GeocodingError("depot record is unreadable or invalid JSON") from error
    if not isinstance(payload, Mapping) or payload.get("acceptance_status") != "accepted":
        raise GeocodingError("depot record is not an accepted record")
    try:
        depot_data = payload["depot"]
        coordinates = payload["coordinates"]
        if not isinstance(depot_data, Mapping) or not isinstance(coordinates, Mapping):
            raise TypeError
        if coordinates.get("crs") != "WGS84":
            raise GeocodingError("depot coordinates must declare WGS84")
        address = DepotAddress(**depot_data)
        schema_version = payload["schema_version"]
        if isinstance(schema_version, bool) or not isinstance(schema_version, int):
            raise GeocodingError("schema_version must be an integer")
        vehicle_access_confirmed = payload["vehicle_access_confirmed"]
        if not isinstance(vehicle_access_confirmed, bool):
            raise GeocodingError("vehicle_access_confirmed must be boolean")
        return AcceptedDepotLocation(
            schema_version,
            address,
            str(payload["provider"]),
            str(payload["display_name"]),
            GeoLocation(
                _coordinate(coordinates["longitude"], "longitude"),
                _coordinate(coordinates["latitude"], "latitude"),
            ),
            tuple(
                (str(key), str(value)) for key, value in dict(payload["provider_address"]).items()
            ),
            _optional_string(payload.get("osm_type")),
            _optional_string(payload.get("osm_id")),
            _optional_string(payload.get("place_id")),
            datetime.fromisoformat(str(payload["fetched_at"])),
            datetime.fromisoformat(str(payload["accepted_at"])),
            str(payload["attribution"]),
            vehicle_access_confirmed,
        )
    except GeocodingError:
        raise
    except (KeyError, TypeError, ValueError, OverflowError) as error:
        raise GeocodingError("depot record failed schema validation") from error


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise GeocodingError("optional provider identifiers must be strings")
    return value


def _default_address() -> DepotAddress:
    return DepotAddress(
        DEFAULT_DEPOT, "Stadtreinigung (SR)", "Brüssel-Strasse", "22", "4053", "Basel"
    )


def _cli() -> int:
    parser = argparse.ArgumentParser(
        description="Review and persist the Stadtreinigung Basel depot point."
    )
    subparsers = parser.add_subparsers(dest="action", required=True)
    lookup = subparsers.add_parser("lookup", help="perform one explicit Nominatim lookup")
    lookup.add_argument("--output", type=Path, required=True)
    lookup.add_argument("--user-agent", required=True)
    lookup.add_argument("--contact")
    lookup.add_argument("--select", type=int, help="one-based candidate number to accept")
    inspect = subparsers.add_parser("inspect", help="load an accepted record offline")
    inspect.add_argument("path", type=Path)
    args = parser.parse_args()
    try:
        if args.action == "inspect":
            location = load_depot_location(args.path)
            print(
                f"{location.depot.depot_id}: "
                f"{location.location.latitude}, {location.location.longitude}"
            )
            print(f"vehicle_access_confirmed: {location.vehicle_access_confirmed}")
            return 0
        address = _default_address()
        candidates = search_depot_candidates(
            address, NominatimClient(user_agent=args.user_agent, contact=args.contact)
        )
        for number, candidate in enumerate(candidates, 1):
            print(f"{number}. {candidate.display_name}")
            print(f"   coordinates: {candidate.location.latitude}, {candidate.location.longitude}")
            print(f"   OSM: {candidate.osm_type}/{candidate.osm_id}")
            print(f"   match: {', '.join(candidate.match_diagnostics) or 'exact'}")
        selection = args.select
        if selection is None:
            try:
                selection = int(input("Select the reviewed candidate number (or 0 to cancel): "))
            except (EOFError, ValueError) as error:
                raise GeocodingError("an explicit candidate selection is required") from error
        if selection == 0:
            print("No candidate accepted.")
            return 2
        location = accept_candidate(
            candidates, address, selection - 1, fetched_at=datetime.now(UTC)
        )
        save_depot_location(location, args.output)
        print(f"saved accepted address point to {args.output}")
        return 0
    except GeocodingError as error:
        parser.error(str(error))
        return 2


if __name__ == "__main__":
    raise SystemExit(_cli())
