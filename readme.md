# Smart Trash: Empty When Full

**Predict · Detect · Optimize.** Fill-level sensors and software that tell a city which public bins are full, which sensors are faulty, and which bins to empty today.

BaselHack 2026 · pilot city: Lucerne (about 960 public bins)

<p>
  <img src="assets/screenshots/crew-login.png" width="200" alt="Sign in as a team">
  <img src="assets/screenshots/crew-tour.png" width="200" alt="Tour with live sensor status">
  <img src="assets/screenshots/crew-done.png" width="200" alt="End of tour report">
  <img src="assets/screenshots/crew-menu.png" width="200" alt="Menu">
</p>

## The problem

Swiss cities empty public bins on a **fixed schedule**. Half-empty bins get emptied, while bins at lakesides, parks and events overflow on hot weekends. Lucerne spends around 16,100 working hours a year emptying its bins.

Sensors alone don't solve this. False readings made Bern stop two sensor pilots (2012, 2018).

## Our solution

1. **Predict** when each bin will be full (weekday, weather, events).
2. **Detect** faulty sensors. A bin whose fill level doesn't drop after a visit is flagged for maintenance.
3. **Optimize** which bins to empty today, and in which order.

Every decision is explained ("full ~13:00 · shopping Saturday"). A bin without valid data goes back on the fixed schedule, and the app shows this.

## What we built at the hack: the crew app

A mobile web app for the street-cleaning crew:

- **Start collecting**, then just work. The sensor sees the fill drop and checks off the stop with no tap.
- **Only problems need a tap**: not reachable, unsafe, bin damaged. Bins without a sensor need one tap.
- **Status bar** with one segment per bin, stops done and km left.
- **End-of-tour report** about the bins, never about the worker.
- **Menu**: today's report, problems, legend, privacy, call the depot, sync status, DE / FR / IT / EN.
- **Team sign-in**: no personal accounts, no tracking, no ranking of workers. Location is read only while the app is open, and only on the phone.

## User stories

All for the crew member (street-cleaning worker, gloves, phone in the pocket). Details and acceptance criteria: [documentation/user-stories.md](documentation/user-stories.md)

1. See which bins need me today and why
2. Zero taps: the sensor detects emptying, I only answer when a sensor looks broken
3. Stay in control: skip a stop or add a bin
4. Start collecting, sensors check off bins, tour report
5. Always see how far along the route I am
6. Menu: report, problems, help, language, sign in / out

## How a tour works

The phone stays in the pocket. The app only asks the crew when a sensor looks broken, or when the crew taps Stop.

```mermaid
flowchart LR
    A["▶ Start collecting"] --> B["Empty the bin<br/>and walk on"]
    B --> C{"Fill level<br/>dropped?"}
    C -->|yes| D["✓ Checked off<br/>by the sensor"]
    C -->|no| E["Phone buzzes:<br/>Defect? Yes / No / Help"]
    E --> D
    D --> F{"More stops?"}
    F -->|yes| B
    F -->|no| G["Tour report"]
    B -.->|any time| S["■ Stop: resume, report,<br/>call depot, end early"]
```

## Design decisions

| Decision | Why |
|---|---|
| Zero taps on a normal stop | The crew works with gloves and both hands full; the app must add no work |
| The app asks only on a suspected fault | Turns a guess into ground truth that trains the fault detector, and answers "how do you know the sensor is broken?" |
| One defect list everywhere | The same three choices in the alert and after Stop: learned once |
| Yes / No / Help, auto-confirm after 6 s | Like a navigation alert: never blocks the crew when nobody answers |
| Correct in the report, not in pop-ups | Mistakes with gloves happen; every bin can be corrected in today's report (pencil), also after Done, without pop-ups covering the screen |
| Team sign-in, reports per bin | No tracking, no times per person, no ranking: the crew must not feel monitored |
| Location only when the app is open | Opening the app next to a suspect bin brings up the Defect alert; the position stays on the phone, is never sent or stored, and needs no new hardware |
| Bins without valid data show "fixed schedule" | The fallback is visible, never hidden |

## Try it

```bash
cd code
python3 -m http.server 5050
```

- <http://localhost:5050/crew-app/>: sign in as a truck and see its real route from the prediction pipeline.
- <http://localhost:5050/crew-app/?demo>: the pitch demo. Tap **▶ Start collecting**. The demo tour has four bins, one for each case (sensor OK, sensor fault, no sensor, bin damaged), and ends with the report after about 20 seconds. The phone stays in the pocket: it only asks the crew when a sensor looks broken.

Details: [documentation/crew-app.md](documentation/crew-app.md)

## Status

| | |
|---|---|
| **Built** | Crew app: tour, live sensor events, defect alert, Stop / pause, editable report, menu, team sign-in, DE / FR / IT / EN |
| **Next** | Connect the backend ([architecture PoC](documentation/Proof_of_Concept_for_the_system_architecture.md)); city administration view; maintenance view |
| **Later** | Real sensors on real bins; forecast model on real data; route optimisation with several vehicles |

## Honest data

- All fill levels, forecasts and sensor events in the demo are **SIMULATED**, and the app says so.
- Real open data for Basel is in `assets/geojson/` (litter reports and the street cleanliness index). It is not bin fill-level data.
- We compare only against the city's real fixed schedule.

## Repository

| Folder | Content |
|---|---|
| [`code/crew-app/`](code/crew-app/) | Crew mobile web app (HTML, CSS, JS, Leaflet) |
| [`documentation/`](documentation/) | [Crew app](documentation/crew-app.md) · [User stories](documentation/user-stories.md) · [Architecture PoC](documentation/Proof_of_Concept_for_the_system_architecture.md) · [Tasks and roles](documentation/tasks.md) |
| [`assets/`](assets/) | Screenshots, open data (GeoJSON), photos |

Work is tracked on the [project board](https://github.com/orgs/Basel-Hackthon-Smart-Trash/projects/1).

## Team

| Name | Role |
|---|---|
| Abbas | Development, project lead |
| Rai | UI/UX |
| Andy | Data science |
| Dennis | Backend |
| Maria | Brand identity |

## Credits

- Brand: logo by Maria; fonts [Jost](https://fonts.google.com/specimen/Jost) and [JetBrains Mono](https://fonts.google.com/specimen/JetBrains+Mono) (SIL Open Font License), self-hosted in `code/crew-app/fonts/`
- Map: [Leaflet](https://leafletjs.com) and © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors
- Open data: [Open Data Basel-Stadt](https://data.bs.ch) (datasets 100070 and 100288)
- AI tooling (allowed by the hackathon rules) helped write code and documentation; all code was written during the hack

## License

[MIT](license.txt)
