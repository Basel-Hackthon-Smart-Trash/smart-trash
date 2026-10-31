# Local Routing Demo

The offline demo uses the approved real bin-location asset together with
explicitly synthetic planning data.

## Run

From `code/routing/`:

```text
uv run python examples/real_bin_subset_demo.py
open examples/real-bin-demo.html
```

The generator writes:

- `examples/real-bin-demo-payload.json`
- `examples/real-bin-demo.html`

The HTML is standalone and does not need a web server, map tiles, or network
access. It renders a simple SVG coordinate view.

## Optional Real Street Background

The visual street background can be downloaded explicitly from OpenStreetMap:

```text
uv run python examples/download_demo_street_network.py
uv run python examples/real_bin_subset_demo.py
open examples/real-bin-demo.html
```

The downloader is the only demo command that uses the network. It saves a
local `real-bin-demo-streets.geojson` background and a validated GraphML cache
under `code/routing/.cache/real-bin-demo-graph/`. The graph cache is ignored
and must be regenerated locally when needed.

The demo accepts location snaps up to 300 m from a drivable graph node. This is
an explicit prototype matching limit, not confirmation that a collection
vehicle can access the bin or depot.

## What The Demo Shows

- Real bin coordinates from `assets/geojson/bin-locations.geojson`.
- A deterministic subset of 12 bins selected with seed `20261031`.
- Simulated fill percentages and green/yellow/red classifications.
- Synthetic explicit demand for every demo bin.
- The existing `plan_collection` optimizer's visit order.
- Route sequence numbers for admitted yellow and red bins, not only red bins.
- Directed road-network objective cost and diagnostics when the graph cache is
  available; otherwise a clearly-labelled synthetic straight-line fallback.
- Exact selected road geometry when the graph cache is available.
- Optional real OpenStreetMap street background rendered locally.
- The provided Stadtreinigung address as both the route start and end.

The demo deliberately shows the fill flag and route order separately. Green
bins remain visible but are excluded below the collection threshold. Every
admitted yellow or red candidate is mandatory, and the optimizer determines
their order; it does not select only red bins.

## Data Labels And Limits

The locations, street background, accepted address point, and cached road
geometry are real source data. Fill levels and demands are simulated. In road
mode, the graph uses OSM edge lengths and explicit speed assumptions; the route
is still a prototype result, not verified Basel navigation. Without the graph
cache, the cost matrix and dashed route line use a deterministic straight-line
coordinate model.

A future real-Basel demo can replace the synthetic cost matrix after explicit
approval of a graph, depot coordinate, snapping limit, and speed policy.
