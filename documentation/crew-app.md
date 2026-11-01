# Crew App

Mobile web app for the street-cleaning crew. Plain HTML, CSS and JavaScript, with Leaflet for the map. There is no build step.

Code: [`code/crew-app/`](../code/crew-app/) · User stories: [user-stories.md](user-stories.md)

## Run it

Serve the `code/` folder, so the crew app can read the same data as the city dashboard:

```bash
cd code
python3 -m http.server 5050 --bind 0.0.0.0
```

| URL | What |
|---|---|
| `http://localhost:5050/crew-app/` | Live routes from `code/web/data/bins.json` (one truck per team) |
| `http://localhost:5050/crew-app/?demo` | The pitch demo: four bins, one per case |
| `http://localhost:5050/web/` | City dashboard (all trucks) |

Without `bins.json` the crew app falls back to the demo tour. On a phone on the same Wi-Fi, use the laptop's IP instead of `localhost`.

The map tiles and Leaflet load from the internet. Everything else works offline.

## Demo script (about 20 seconds)

1. **Sign in** as a team (e.g. Team KB-3).
2. Tap **▶ Start collecting**. A simulated sensor feed handles one stop about every 3 s. Each event is animated: the map marker pings, the fill bar drains, and the card glows. Events show in the live line under the status bar.
3. The four demo bins show one case each:

| # | Bin | Case | What the app shows |
|---|---|---|---|
| 1 | Messeplatz | Sensor sees the fill drop | ✓ detected by sensor |
| 2 | Mittlere Brücke | No valid sensor: fixed schedule | ✓ emptied · tapped |
| 3 | Claraplatz | No fill drop after the visit | Alert "Defect?" Yes / No / Help; Yes opens common defects + optional note; confirms itself after 6 s |
| 4 | Barfüsserplatz | Crew reports a problem | skipped · Bin damaged |

4. Optional: tap **■ Stop** in the bottom bar to pause. The pause sheet offers Resume, Report a problem, Call depot and End tour now.
5. At the end, the **Well done** screen shows the tour report. **Edit report** lists every bin; tap one (pencil) to correct its status. The report stays in ☰ → Today's report after Done.
6. Open **☰** to show the report, the problems, the legend, the privacy page, the language switch and the sync status.

The supervisor code for **＋ Add a bin** is `1234`. It is a demo value, the app shows it as a hint, and it is not a secret.

## Files

| File | What it holds |
|---|---|
| `index.html` | Screens: sign in, tour, end of tour; the bottom sheet; the toast |
| `app.js` | All logic: rendering, map, simulated sensor feed, crew actions, menu |
| `data.js` | **SIMULATED** demo data: teams, tour, depot, stops, nearby bins |
| `i18n.js` | UI texts in DE, FR, IT, EN, plus translations of the "why" keywords |
| `styles.css` | Design tokens (colours, radius, touch size) at the top, then the components |

## Live data (prediction + routing)

`live-data.js` first reads `http://127.0.0.1:8000/api/bins`, served from the latest output of the daily run in `code/prediction` (see [prediction-and-integration.md](prediction-and-integration.md)). If the API is unavailable, it falls back to the committed `code/web/data/bins.json` snapshot. The city dashboard reads that snapshot directly.

For local API development, start `code/api/server.py` after generating the snapshot. The crew app then reads `http://127.0.0.1:8000/api/bins`; it falls back to the committed snapshot, then to the pitch demo if neither source is available.

| Crew app | `bins.json` |
|---|---|
| Teams on the sign-in screen | `routes[n]` → "Truck n+1 · stops · km" |
| Stops in order | `routes[n].stops` → `bins[id]` |
| Fill level | `fill_percent` |
| Observed fill band | `fill_band` (`green`, `orange`, `red`) |
| "why" keywords | `predicted_full_at` and the context in `reason`, e.g. "full ~12:00 · weekend" |
| Fixed schedule | `fault: true` |
| Bins the crew may add | Bins on no route, sensor OK, closest to the route |
| SIMULATED / REAL | `simulated` |

**Missing:** street names. The file has `osm_id` but no `name`; the app shows the bin id until a `name` or `street` field is added.

## Data contract (for the backend)

`data.js` sets `window.SMART_TRASH_DATA`. A backend endpoint can return the same shape and replace the file.

```js
{
  dataLabel: "SIMULATED",            // or "REAL": shown next to every number
  supervisorPin: "1234",             // demo only
  teams: ["Team KB-3", ...],         // sign-in choices: teams, never persons
  tour: {
    id, name, date,                  // "2026-10-31"
    depot: { name, lat, lon, phone }
  },
  stops: [{                          // in route order
    binId, name, area, lat, lon,
    fill,                            // predicted %, or null when there is no valid sensor
    source,                          // "sensor" | "fixed-schedule"
    why: ["full ~11:00", "Herbstmesse"],  // max 3 keywords
    suspect,                         // true: sensor reading looks wrong; the app asks when the crew is near
    demo                             // demo script only: "sensor-fault" | "bin-damaged"
  }],
  nearby: [{ binId, name, area, lat, lon, fill }]   // bins the crew can add
}
```

**Live events.** In the real system, the backend pushes a fill-drop event when a bin is emptied. In the demo, `sensorTick()` in `app.js` simulates these events. Replace it with a WebSocket or polling call.

**Crew reports** are written to `localStorage` (`smarttrash.feedback`), one entry per bin: `{ binId, problem | emptied | addedByCrew, at }`. Entries carry no worker ID and no per-person timing.

## How the product rules show up in the app

| Rule | Where in the app |
|---|---|
| Honest data | `SIMULATED` badge on the tour and in the legend; all data in `data.js` is simulated |
| Glanceable UI | Keywords and numbers; the status bar shows stops and km left |
| Explain decisions | Every stop has a "why" line |
| Outdoor-ready | Touch targets of at least 48–60 px, high contrast, offline sync status |
| Fallback visible | Bins without a valid sensor show a "fixed schedule" badge and need one tap |
| No worker tracking | Team sign-in; reports per bin; privacy page in the menu; location only while the app is open, compared on the phone, never sent or stored |

## Known limits

- Fill levels, the sensor feed and the depot phone number are simulated.
- Live mode simulates the sensor events along the real route; real events will come from the MQTT broker.
- The location check (Defect alert near a suspect bin, 40 m) needs HTTPS, e.g. GitHub Pages; on plain http it does nothing and the demo feed triggers the alert instead.
- FR and IT texts need a check by a native speaker.
- City administration and maintenance views are not built yet.
