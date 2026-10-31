# Crew App

Mobile web app for the street-cleaning crew. Plain HTML, CSS and JavaScript, with Leaflet for the map. There is no build step.

Code: [`code/crew-app/`](../code/crew-app/) · User stories: [user-stories.md](user-stories.md)

## Run it

```bash
cd code/crew-app
python3 -m http.server 5050 --bind 0.0.0.0
```

Open `http://localhost:5050` on the laptop. To use it on a phone on the same Wi-Fi, open `http://<laptop-ip>:5050`.

The map tiles and Leaflet load from the internet. Everything else works offline.

## Demo script (about 10 seconds)

1. **Sign in** as a team (e.g. Team KB-3).
2. Tap **▶ Start collecting**. A simulated sensor feed checks off one stop every 1.5 s.
3. The four demo bins show one case each:

| # | Bin | Case | What the app shows |
|---|---|---|---|
| 1 | Messeplatz | Sensor sees the fill drop | ✓ detected by sensor |
| 2 | Claraplatz | No fill drop after the visit | ⚠ Sensor fault, sent to maintenance |
| 3 | Mittlere Brücke | No valid sensor: fixed schedule | ✓ emptied · tapped |
| 4 | Barfüsserplatz | Crew reports a problem | skipped · Bin damaged |

4. At the end, the **Well done** screen shows the tour report.
5. Open **☰** to show the report, the problems, the legend, the privacy page, the language switch and the sync status.

The supervisor code for **＋ Add a bin** is `1234`. It is a demo value, the app shows it as a hint, and it is not a secret.

## Files

| File | What it holds |
|---|---|
| `index.html` | Screens: sign in, tour, end of tour; the bottom sheet; the toast |
| `app.js` | All logic: rendering, map, simulated sensor feed, crew actions, menu |
| `data.js` | **SIMULATED** demo data: teams, tour, depot, stops, nearby bins |
| `i18n.js` | UI texts in DE, FR, IT, EN, plus translations of the "why" keywords |
| `styles.css` | Design tokens (colours, radius, touch size) at the top, then the components |

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
| No worker tracking | Team sign-in; reports per bin; privacy page in the menu |

## Known limits

- Fill levels, the sensor feed and the depot phone number are simulated.
- FR and IT texts need a check by a native speaker.
- City administration and maintenance views are not built yet.
