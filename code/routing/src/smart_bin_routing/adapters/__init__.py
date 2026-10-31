"""External-source adapters for the routing package."""

from .bin_geojson import BinGeoJSONError, load_bin_geojson
from .osmnx_graph import (
    GraphArea,
    GraphArtifact,
    GraphError,
    GraphProvenance,
    GraphSettings,
    acquire_graph,
    add_edge_travel_times,
    load_graph,
    save_graph,
)

__all__ = [
    "AcceptedDepotLocation",
    "BinGeoJSONError",
    "DepotAddress",
    "GraphArea",
    "GraphArtifact",
    "GraphError",
    "GraphProvenance",
    "GraphSettings",
    "GeocodingCandidate",
    "GeocodingError",
    "NominatimClient",
    "acquire_graph",
    "add_edge_travel_times",
    "accept_candidate",
    "load_bin_geojson",
    "load_depot_location",
    "load_graph",
    "save_depot_location",
    "save_graph",
    "search_depot_candidates",
]
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
