"""Real street distances for Basel (one-way streets included).

Step 1 (needs internet, run once, ~2-5 min):
    uv run python -m smartbins.streets
-> downloads Basel's drivable streets from OpenStreetMap with OSMnx,
   snaps the Werkhof and every bin to the nearest street,
   and saves a driving-distance matrix to data/street_matrix.npz

The matrix is NOT symmetric: A->B can be longer than B->A because of one-way streets.
Index 0 = Werkhof, index i (1..n) = bins[i-1] in bins_locations.json.
"""
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
MATRIX_FILE = ROOT / "data" / "street_matrix.npz"
GRAPH_FILE = ROOT / "data" / "basel_drive.graphml"
ON_FOOT_M = 150   # bin further than this from a drivable street = crew walks


def build_matrix() -> None:
    import networkx as nx
    import osmnx as ox

    data = json.loads((ROOT / "data" / "bins_locations.json").read_text(encoding="utf-8"))
    bins, depot = data["bins"], data["depot"]

    if GRAPH_FILE.exists():
        G = ox.load_graphml(GRAPH_FILE)
    else:
        print("Downloading Basel street network from OpenStreetMap ...")
        G = ox.graph_from_place("Basel, Switzerland", network_type="drive")
        # keep only streets you can drive to AND back from (removes dead one-way ends)
        G = ox.truncate.largest_component(G, strongly=True)
        ox.save_graphml(G, GRAPH_FILE)
    print(f"Street graph: {len(G.nodes)} junctions, {len(G.edges)} street segments")

    lats = [depot["lat"]] + [b["lat"] for b in bins]
    lons = [depot["lon"]] + [b["lon"] for b in bins]
    nodes, snap_m = ox.distance.nearest_nodes(G, X=lons, Y=lats, return_dist=True)
    nodes, snap_m = list(nodes), np.asarray(snap_m, dtype=float)

    n = len(nodes)
    M = np.full((n, n), np.inf)
    for i, src in enumerate(nodes):
        dist = nx.single_source_dijkstra_path_length(G, src, weight="length")
        M[i] = [dist.get(dst, np.inf) for dst in nodes]
        if i % 50 == 0:
            print(f"  distances {i}/{n}")
    M = M / 1000.0                                  # metres -> km
    np.fill_diagonal(M, 0.0)

    unreachable = int(np.isinf(M).sum())
    on_foot = [bins[i - 1]["id"] for i in range(1, n) if snap_m[i] > ON_FOOT_M]
    np.savez_compressed(MATRIX_FILE, M=M, snap_m=snap_m,
                        ids=np.array(["DEPOT"] + [b["id"] for b in bins]))
    print(f"Saved {MATRIX_FILE.name}: {n}x{n}, unreachable pairs: {unreachable}")
    print(f"Werkhof is {snap_m[0]:.0f} m from the nearest drivable street"
          + ("  <-- check the Werkhof position!" if snap_m[0] > 300 else ""))
    print(f"Bins more than {ON_FOOT_M} m from a drivable street (crew walks): {len(on_foot)}")


def load_matrix() -> np.ndarray:
    return np.load(MATRIX_FILE)["M"]


def straight_line_matrix() -> np.ndarray:
    """Fallback without internet: straight-line km (what the earlier test used)."""
    data = json.loads((ROOT / "data" / "bins_locations.json").read_text(encoding="utf-8"))
    pts = [data["depot"]] + data["bins"]
    XY = np.array([[p["lat"] * 111.0, p["lon"] * 75.0] for p in pts])
    return np.hypot(*(XY[:, None, :] - XY[None, :, :]).transpose(2, 0, 1))


def tour_length(M: np.ndarray, stops: list[int], improve_up_to: int = 70) -> float:
    return tour(M, stops, improve_up_to)[1]


def tour(M: np.ndarray, stops: list[int], improve_up_to: int = 70) -> tuple[list[int], float]:
    """Werkhof (0) -> stops -> Werkhof. Nearest neighbour + 2-opt.
    Works with one-way (asymmetric) distances: reversing a segment
    uses the real reverse-direction costs.
    Returns (stop order without the Werkhof, length in km)."""
    if not stops:
        return [], 0.0
    left = set(stops)
    order = [0]
    while left:
        nxt = min(left, key=lambda j: M[order[-1], j])
        order.append(nxt)
        left.remove(nxt)
    order.append(0)

    if len(stops) <= improve_up_to:
        improved = True
        while improved:
            improved = False
            o = np.array(order)
            fwd = np.concatenate([[0], np.cumsum(M[o[:-1], o[1:]])])   # cost along the tour
            bwd = np.concatenate([[0], np.cumsum(M[o[1:], o[:-1]])])   # same edges driven backwards
            for i in range(1, len(order) - 2):
                for j in range(i + 1, len(order) - 1):
                    a, b, c, d = order[i - 1], order[i], order[j], order[j + 1]
                    old = M[a, b] + (fwd[j] - fwd[i]) + M[c, d]
                    new = M[a, c] + (bwd[j] - bwd[i]) + M[b, d]
                    if new < old - 1e-9:
                        order[i:j + 1] = order[i:j + 1][::-1]
                        improved = True
                        break
                if improved:
                    break
    return order[1:-1], float(sum(M[order[k], order[k + 1]] for k in range(len(order) - 1)))


def get_snap_m(n_points: int) -> np.ndarray:
    """Distance (m) from each point to the nearest drivable street. 0 without the real matrix."""
    if MATRIX_FILE.exists():
        return np.load(MATRIX_FILE)["snap_m"]
    return np.zeros(n_points)


def get_matrix() -> tuple[np.ndarray, str]:
    """Real streets if street_matrix.npz exists, otherwise straight lines."""
    if MATRIX_FILE.exists():
        return load_matrix(), "real streets"
    return straight_line_matrix(), "straight lines"


if __name__ == "__main__":
    build_matrix()
