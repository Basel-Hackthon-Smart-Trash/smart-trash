"""External-source adapters for the routing package."""

from .bin_geojson import BinGeoJSONError, load_bin_geojson
from .depot_geocoding import (
    AcceptedDepotLocation,
    DepotAddress,
    GeocodingCandidate,
    GeocodingError,
    NominatimClient,
    accept_candidate,
    load_depot_location,
    save_depot_location,
    search_depot_candidates,
)

__all__ = [
    "AcceptedDepotLocation",
    "DepotAddress",
    "GeocodingCandidate",
    "GeocodingError",
    "NominatimClient",
    "accept_candidate",
    "load_depot_location",
    "save_depot_location",
    "search_depot_candidates",
    "BinGeoJSONError",
    "load_bin_geojson",
]
