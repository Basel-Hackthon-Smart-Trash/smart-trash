# Smart Trash – Prediction, Fault Detection & Daily Plan

Predicts when each public bin will be full, flags sensors that send wrong data,
decides which bins are emptied today, and splits them into truck tours.
The stop order of each tour comes from the team routing package `../routing`
(`smart_bin_routing`, OR-Tools), which is used **unchanged** as a dependency.

**Data:** bin locations are REAL (OpenStreetMap, `assets/geojson/bin-locations.geojson`,
filtered to 309 public outdoor bins in Basel). Fill levels, weather and events are SIMULATED.
Depot: Stadtreinigung Werkhof, Brüssel-Strasse 22 (approx. position).

## Quick start
Needs [uv](https://docs.astral.sh/uv/). Python 3.12 is pinned (`.python-version`), because
OR-Tools does not support Python 3.15 yet.

```
cd code/prediction
uv sync --extra streets                     # installs this package + ../routing
uv run python -m smartbins.simulate         # creates data/readings.csv, weather.csv, events.json
uv run python -m smartbins.streets          # downloads Basel streets, creates data/street_matrix.npz (needs internet, once)
uv run pytest                               # 10 tests
uv run python -m smartbins.run_daily        # whole chain -> data/bins.json
```
Then copy `data/bins.json` to `../web/data/` and open `../web/index.html` with a local server
(e.g. VS Code "Live Server"). Without the street step, routing falls back to straight-line distances.

## Generated files (not in Git)
These are created by the commands above and listed in `.gitignore`:

| File | Created by | Content |
| --- | --- | --- |
| `data/readings.csv` | `simulate` | Simulated sensor readings, 14 days, every 30 min |
| `data/basel_drive.graphml` | `streets` | Basel street network from OpenStreetMap |
| `data/street_matrix.npz` | `streets` | Driving distances Werkhof + all bins (one-way streets included) |
| `data/predictions.json` | `pipeline` | Forecast + fault result without routes |
| `data/evaluation.csv`, `data/*_test_*.csv` | `evaluate`, `zone_test`, `policy_test` | Test results |

Committed on purpose: `data/bins_locations.json`, `data/events.json`, `data/weather.csv`,
`data/bins.json` and `../web/data/bins.json` (so the dashboard demo works without running anything).

## Daily flow (`run_daily`)
1. **Fault detection** (`faults.py`): rule-based, no labels needed. Faulty bins are not routed (fixed schedule).
2. **Forecast** (`predict.py`): when will each bin be full? -> status red / orange / green.
3. **Selection** (`config.py`): red = at least 90 % or full before the next tour (24 h); orange = 70-89 %; both are emptied.
4. **Truck limits** (`routing.py`): split the selected bins into tours that keep load and shift time.
5. **Route order**: each tour -> `smart_bin_routing.plan_collection()` (OR-Tools).
6. Result -> `data/bins.json` for the website.

## Modules
| File | What it does |
| --- | --- |
| `config.py` | All settings and thresholds (tune here, not in the logic) |
| `simulate.py` | Simulated readings, weather and example events for the 309 bins |
| `faults.py` | Fault rules (offline, stuck, jump-and-freeze, out of range, warnings) |
| `features.py` | Day type, weather (`weather.csv`) and events (`events.json`) |
| `predict.py` | Forecast model: hour of day x weekend x temperature x events (learned) |
| `pipeline.py` | Fault detection + forecast for all bins -> `predictions.json` |
| `routing.py` | Truck limits + adapter to the team routing package |
| `streets.py` | Real street distance matrix with OSMnx |
| `run_daily.py` | Whole chain -> `data/bins.json` |
| `evaluate.py` | Backtest of the forecast vs. simple baselines |
| `zone_test.py`, `policy_test.py` | Simulation studies (zones, collection rules over 60 days) |

## Forecast model
fill speed = bin's normal speed at that hour x weekend factor x temperature factor x event factor.
All factors are learned from the data (weekend per bin, temperature for the city, one factor per
event type). Unknown event types use `DEFAULT_EVENT_FACTOR` (1.5, assumption).
Weather and events are SIMULATED examples; later MeteoSwiss / Open-Meteo and the Basel event calendar.

## Fault rules
| Code | Rule | Severity |
| --- | --- | --- |
| offline | No reading for 7 h (two missed 3-hour batches) | fault |
| out_of_range | Value below 0 or above 100 | fault |
| stuck | No change for 8+ daytime hours (not when the bin is 95-100 % full) | fault |
| jump_freeze | +40 points in one reading, then frozen for 3 h | fault |
| partial_drop | Drop of 8-30 points (bins empty fully, not halfway) | warning |
| low_battery | Battery below 15 % | warning |

Known limitation: a sensor stuck at 100 % looks like a full bin. It gets emptied anyway, and crew
feedback ("sensor broken") catches it afterwards.

## Sensor design (option 1)
Measure every 30 min, send a batch every 3 h, send immediately at 90 % full, and send one fresh
batch at 05:30 before planning (06:00). See `config.py`.

## Truck limits (config.py, all assumptions)
`TRUCK_CAPACITY_L`, `SHIFT_HOURS`, `AVG_SPEED_KMH`, `SERVICE_MIN_PER_BIN`, `WALK_SPEED_KMH`,
`BIN_VOLUME_L`, `MAX_TRUCKS`. Trucks are added until every tour keeps the load and time limit.
Bins more than 150 m from a drivable street count as walking stops (needs the street matrix).
Shift time is an estimate with an average speed; real driving times per street come later.

## Tests and studies
```
uv run pytest                                            # fault rules + routing integration
uv run python -m smartbins.evaluate                      # forecast accuracy 3-24 h ahead
uv run python -m smartbins.evaluate --every-h 3 --fresh  # sensor sends every 3 h + fresh batch
uv run python -m smartbins.zone_test --streets real      # fixed zones vs. fill-based zones, 200 days
uv run python -m smartbins.policy_test --streets real    # collection rules over 5 x 60 days
```
The studies use the simple nearest-neighbour + 2-opt tour for speed, not OR-Tools.

## After changing the depot
The depot is point 0 of the street matrix: run `uv run python -m smartbins.streets` again.
