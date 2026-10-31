# Smart Bin Routing Foundation

Stage 1 provides source-independent Python contracts and structural validation
for the future routing component. It does not classify fill levels, optimize a
route, read GeoJSON, use OSMnx or OR-Tools, or connect to a backend.

## Development

From this directory:

```text
uv sync
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

The package supports Python 3.12 through 3.15. Runtime dependencies are from
the standard library. Pytest and Ruff are development dependencies.

## Contract boundaries

Adapters translate external metadata and observations into `BinMetadata` and
`FillObservation`. Fill observations contain a finite normalized fraction in
`[0, 1]` and a timezone-aware timestamp. Missing data is not converted to a
default value.

`TravelCostMatrix` uses explicit node ordering and represents unavailable
connections with `None`. It does not expose an OSMnx graph or imply that a
missing connection is zero cost.

## Prototype configuration

The documented prototype models a round trip:

```text
KVA Basel -> selected collection stops -> KVA Basel
```

Both node identifiers are `kva-basel`. The descriptive location is KVA Basel,
Hagenaustrasse 40, 4056 Basel, a general-waste incineration plant. This is a
project modeling assumption, not proof of a depot or vehicle entrance. No
coordinates are included; vehicle access and road-network snapping must be
confirmed in a later geographic stage.

Capacity, demand units, and threshold values must be supplied explicitly.
No operational defaults are claimed.

## Synthetic test data

Fixtures in `tests/conftest.py` are synthetic and exist only to exercise the
contracts. They are not derived from the repository's real GeoJSON asset.
