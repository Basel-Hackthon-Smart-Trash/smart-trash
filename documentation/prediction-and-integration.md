# Prediction and routing integration

## Folders
| Folder | Owner | What |
| --- | --- | --- |
| `code/routing` | Andy | `smart_bin_routing`: validation, classification, OR-Tools route for one truck, one trip. **Unchanged.** |
| `code/prediction` | Abbas | `smartbins`: simulation, fault detection, fill forecast (hour, weekend, temperature, events), bin selection, truck limits, daily run |
| `code/web` | Abbas / UI | Leaflet dashboard, reads `data/bins.json` |

## Daily flow (`uv run python -m smartbins.run_daily` in `code/prediction`)
1. Readings -> **fault detection** (rules, no labels needed). Faulty bins are not routed (fixed schedule).
2. **Forecast** per bin -> status red / orange / green (rule in `config.py`).
3. Red + orange bins get a `CollectionDemand` (estimated litres, marked `estimated=True`).
   Bins without demand are excluded by `smart_bin_routing` (`missing_collection_demand`).
4. **Truck limits** (load, shift time) split the selected bins into tours.
5. Each tour -> `smart_bin_routing.plan_collection()` -> stop order (OR-Tools).
6. Result -> `data/bins.json` -> copy to `code/web/data/`.

## How the packages are connected
- `code/prediction/pyproject.toml` depends on `smart-bin-routing` via a uv path source (`../routing`).
- Adapter: `code/prediction/src/smartbins/routing.py` builds `PlanningSnapshot`, `PlanningConfig`,
  `TravelCostMatrix` (km, real streets if `data/street_matrix.npz` exists) and calls `plan_collection` per tour.
- `PlanningConfig`: capacity `TRUCK_CAPACITY_L` in litres, `demand_policy=ALLOW_MARKED_ESTIMATES`,
  `observation_max_age_seconds = NO_DATA_HOURS * 3600` (7 h, sensor sends every 3 h).

## Decisions (2026-10-31)
1. **Depot:** Stadtreinigung Werkhof, Brüssel-Strasse 22, Basel (`DEPOT_NODE_ID`, approx. 47.5360, 7.6060).
   `smart_bin_routing.prototype_config` (KVA Basel) is left unchanged and not used by the daily run.
2. **Colours:** the forecast status from `smartbins` (red / orange / green) decides which bins are emptied and is
   the only colour shown in the UI. The fill-only classification of `smart_bin_routing` stays internal (validation).
3. **Multiple trucks:** the split into tours stays in `smartbins`; `smart_bin_routing` plans each tour.
4. **Shift time:** checked in `smartbins` (driving at AVG_SPEED_KMH + stops + walking). No duration matrix is passed.
5. **Pilot city:** Basel (demo data: Basel open data + OpenStreetMap).

## Still open
- Analysis scripts (`zone_test`, `policy_test`) use the simple nearest-neighbour + 2-opt tour for speed.
- Real driving times per street (duration matrix) would allow optimising by time instead of distance.
