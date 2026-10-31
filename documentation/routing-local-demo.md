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
local `real-bin-demo-streets.geojson` background. The downloaded street graph
is used only for visual shapes; it is not speed-validated or used as an
operational route result.

## What The Demo Shows

- Real bin coordinates from `assets/geojson/bin-locations.geojson`.
- A deterministic subset of 12 bins selected with seed `20261031`.
- Simulated fill percentages and green/yellow/red classifications.
- Synthetic explicit demand for every demo bin.
- The existing `plan_collection` optimizer's visit order.
- Route sequence numbers for admitted yellow and red bins, not only red bins.
- Synthetic straight-line objective cost and diagnostics.
- Optional real OpenStreetMap street background rendered locally.
- The provided Stadtreinigung address as both the route start and end.

The demo deliberately shows the fill flag and route order separately. Green
bins remain visible but are excluded below the collection threshold. Every
admitted yellow or red candidate is mandatory, and the optimizer determines
their order; it does not select only red bins.

## Data Labels And Limits

The locations, optional street background, and accepted address point are real
source data. Fill levels, demands, and travel costs are simulated. The cost
matrix is a deterministic straight-line coordinate model, not road distance or
driving time. The dashed route line is based on that model; it is not verified
Basel navigation.

A future real-Basel demo can replace the synthetic cost matrix after explicit
approval of a graph, depot coordinate, snapping limit, and speed policy.
